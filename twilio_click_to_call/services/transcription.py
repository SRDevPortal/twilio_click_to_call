from __future__ import annotations

import hashlib
import json
from urllib.parse import urlsplit

import frappe
import requests

from twilio_click_to_call.services.ai import enqueue_ai_disposition
from twilio_click_to_call.services.recording import provider_recording_url
from twilio_click_to_call.services.settings import (
    get_auth_credentials,
    get_openai_api_key,
    get_settings,
)


def transcribe_recording(call_log: str) -> None:
    doc = frappe.get_doc("Twilio Call Log", call_log)
    settings = get_settings()
    if (
        not settings.enabled
        or not settings.enable_recording
        or not settings.enable_transcription
        or not doc.recording_url
    ):
        return
    api_key = get_openai_api_key(settings)
    if not api_key:
        _fail(doc, "OpenAI API key is not configured.")
        return
    audio_url = provider_recording_url(doc, settings)
    host = (urlsplit(audio_url).hostname or "").lower()
    is_twilio_media = host in {"api.twilio.com", "voice.twilio.com"} or host.endswith(".twilio.com")
    is_external_media = host.endswith(".amazonaws.com")
    if not is_twilio_media and not is_external_media:
        _fail(doc, "Recording URL is not hosted by Twilio or an approved external storage host.")
        return

    account_sid, auth_token = get_auth_credentials(settings)
    if not audio_url.endswith((".mp3", ".wav")):
        audio_url += ".mp3"
    try:
        audio = requests.get(
            audio_url,
            auth=(account_sid, auth_token) if is_twilio_media else None,
            timeout=int(settings.http_timeout or 20) * 3,
        )
        audio.raise_for_status()
        model = settings.transcription_model or "gpt-4o-mini-transcribe"
        response = requests.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            data={"model": model, "response_format": "json"},
            files={"file": ("recording.mp3", audio.content, "audio/mpeg")},
            timeout=max(120, int(settings.http_timeout or 20) * 6),
        )
        response.raise_for_status()
        payload = response.json()
        text = str(payload.get("text") or "").strip()
        if not text:
            raise ValueError("OpenAI returned an empty transcript.")
    except Exception as exc:
        _fail(doc, str(exc))
        return

    doc.transcript_text = text
    doc.transcription_text = text
    doc.transcript_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    doc.transcript_json = json.dumps(payload, ensure_ascii=False, indent=2)
    doc.transcript_status = "Completed"
    doc.transcript_received_at = frappe.utils.now()
    doc.transcript_error = ""
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    if (
        frappe.utils.cint(settings.enabled)
        and frappe.utils.cint(settings.enable_ai_disposition)
    ):
        enqueue_ai_disposition(doc.name)


def _fail(doc, message: str) -> None:
    doc.transcript_status = "Failed"
    doc.transcript_error = str(message)[:1000]
    doc.save(ignore_permissions=True)
    frappe.db.commit()
