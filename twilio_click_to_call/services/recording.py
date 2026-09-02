from __future__ import annotations

import json
from urllib.parse import quote
from typing import Any

import frappe

from twilio_click_to_call.services.client import TwilioClient, extract_provider_id
from twilio_click_to_call.services.settings import (
    build_callback_url,
    get_auth_credentials,
    get_settings,
)


def start_recording_if_needed(call_log: str) -> None:
    settings = get_settings()
    if not settings.enabled or not settings.enable_recording:
        return

    doc = frappe.get_doc("Twilio Call Log", call_log)
    if doc.recording_status in {"Starting", "Started", "Completed"} or doc.recording_id:
        return

    call_uuid = doc.recording_call_uuid or doc.call_uuid or doc.a_leg_uuid
    if not call_uuid:
        frappe.db.set_value(
            "Twilio Call Log",
            call_log,
            {
                "recording_status": "Failed",
                "recording_error": "Could not start recording because Twilio Call UUID is missing.",
            },
            update_modified=False,
        )
        frappe.db.commit()
        return

    token = doc.callback_token
    payload = build_recording_payload(doc.name, token, settings)
    frappe.db.set_value(
        "Twilio Call Log",
        call_log,
        {
            "recording_call_uuid": call_uuid,
            "recording_status": "Starting",
            "recording_started_at": frappe.utils.now(),
            "recording_request_json": json.dumps(redact_callback_tokens(payload), indent=2, default=str),
            "recording_error": "",
            "transcript_status": "Requested" if settings.enable_transcription else "Not Requested",
        },
        update_modified=False,
    )
    frappe.db.commit()

    try:
        response = TwilioClient(settings).start_call_recording(call_uuid, payload)
    except Exception as exc:
        current_status = frappe.db.get_value("Twilio Call Log", call_log, "recording_status")
        if current_status != "Completed":
            frappe.db.set_value(
                "Twilio Call Log",
                call_log,
                {"recording_status": "Failed", "recording_error": str(exc)},
                update_modified=False,
            )
        frappe.db.commit()
        return

    current = frappe.db.get_value(
        "Twilio Call Log",
        call_log,
        ["recording_status", "recording_id", "recording_url"],
        as_dict=True,
    ) or {}
    frappe.db.set_value(
        "Twilio Call Log",
        call_log,
        {
            "recording_status": "Completed" if current.get("recording_status") == "Completed" else "Started",
            "recording_id": extract_provider_id(response, "recording_id", "RecordingID", "id") or current.get("recording_id"),
            "recording_url": extract_provider_id(response, "url", "record_url", "recording_url") or current.get("recording_url"),
            "recording_response_json": json.dumps(response, indent=2, default=str),
            "recording_error": "",
        },
        update_modified=False,
    )
    frappe.db.commit()


def provider_recording_url(doc, settings=None) -> str:
    """Return an authenticated Twilio media URL when a Recording SID is available.

    Twilio callbacks may expose recordings through an S3-backed URL. The
    Recording SID is stable, so fetching through the Twilio API avoids rejecting
    valid provider storage URLs and preserves Twilio authentication.
    """
    settings = settings or get_settings()
    account_sid, _ = get_auth_credentials(settings)
    recording_id = str(doc.get("recording_id") or "").strip()
    stored_url = str(doc.get("recording_url") or "").strip()
    stored_host = stored_url.split("/", 3)[2].lower() if stored_url.startswith("https://") else ""
    # External-storage accounts return the playable media URL (for example an
    # S3 URL). Preserve it; the standard Twilio .mp3 endpoint returns 404 for
    # recordings that are not stored in Twilio.
    if stored_url and stored_host not in {"api.twilio.com", "voice.twilio.com"} and not stored_host.endswith(".twilio.com"):
        return stored_url
    if account_sid and recording_id.startswith("RE"):
        return (
            f"https://api.twilio.com/2010-04-01/Accounts/"
            f"{quote(account_sid, safe='')}/Recordings/{quote(recording_id, safe='')}.mp3"
        )
    return stored_url


def build_recording_payload(call_log: str, token: str, settings) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "time_limit": int(settings.recording_time_limit or settings.max_call_duration or 3600),
        "file_format": settings.recording_format or "mp3",
        "record_channel_type": settings.record_channel_type or "stereo",
        "callback_url": build_callback_url(
            "twilio_click_to_call.api.webhook.recording_callback",
            call_log,
            token,
            settings,
        ),
        "callback_method": "POST",
    }

    if settings.enabled and settings.enable_recording and settings.enable_transcription:
        payload.update(
            {
                "transcription_model": settings.transcription_model or "gpt-4o-mini-transcribe",
                "transcription_url": build_callback_url(
                    "twilio_click_to_call.api.webhook.transcription_callback",
                    call_log,
                    token,
                    settings,
                ),
            }
        )

    return payload


def redact_callback_tokens(payload: dict[str, Any]) -> dict[str, Any]:
    redacted = {}
    for key, value in payload.items():
        if isinstance(value, str) and "token=" in value:
            redacted[key] = value.split("token=", 1)[0] + "token=***"
        else:
            redacted[key] = value
    return redacted
