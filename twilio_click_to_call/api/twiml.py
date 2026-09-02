from __future__ import annotations

import hmac
import json

import frappe
from frappe.rate_limiter import rate_limit
from twilio.twiml.voice_response import VoiceResponse
from werkzeug.wrappers import Response

from twilio_click_to_call.api.call import restore_mapping_after_call
from twilio_click_to_call.services.call_log import append_callback, sync_linked_summaries
from twilio_click_to_call.services.call_log_update import save_doc_latest, snapshot_doc
from twilio_click_to_call.services.settings import build_callback_url, get_settings
from twilio_click_to_call.services.webhooks import validate_twilio_request

TERMINAL = {"completed", "busy", "failed", "no-answer", "canceled", "cancelled"}


def _xml(value: str) -> Response:
    return Response(value, content_type="application/xml; charset=utf-8")


def _plain(value: str = "OK") -> Response:
    return Response(value, content_type="text/plain; charset=utf-8")


def _authorized_doc(call_log: str | None, token: str | None):
    if not call_log or not token or not frappe.db.exists("Twilio Call Log", call_log):
        return None
    doc = frappe.get_doc("Twilio Call Log", call_log)
    if not hmac.compare_digest(str(doc.callback_token or ""), str(token or "")):
        return None
    return doc


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=300, seconds=60)
def outbound():
    params = validate_twilio_request()
    doc = _authorized_doc(params.get("call_log"), params.get("token"))
    response = VoiceResponse()
    if not doc or doc.direction != "Outgoing":
        response.hangup()
        return _xml(str(response))

    settings = get_settings()
    parent_sid = params.get("CallSid", "")
    callback = build_callback_url(
        "twilio_click_to_call.api.twiml.status", doc.name, doc.callback_token, settings
    )
    recording_callback = build_callback_url(
        "twilio_click_to_call.api.twiml.recording_status",
        doc.name,
        doc.callback_token,
        settings,
    )
    dial_kwargs = {
        "caller_id": doc.caller_id,
        "action": build_callback_url(
            "twilio_click_to_call.api.twiml.dial_complete",
            doc.name,
            doc.callback_token,
            settings,
        ),
        "method": "POST",
        "timeout": int(settings.agent_ring_timeout or 30),
        "time_limit": int(settings.max_call_duration or 3600),
    }
    if frappe.utils.cint(settings.enable_recording):
        dial_kwargs.update(
            {
                "record": (
                    "record-from-answer-dual"
                    if settings.record_channel_type == "stereo"
                    else "record-from-answer"
                ),
                "recording_status_callback": recording_callback,
                "recording_status_callback_method": "POST",
                "recording_status_callback_event": "completed",
            }
        )
    dial = response.dial(**dial_kwargs)
    dial.number(
        doc.customer_number,
        status_callback=callback,
        status_callback_method="POST",
        status_callback_event="initiated ringing answered completed",
    )

    doc.a_leg_uuid = parent_sid or doc.a_leg_uuid
    doc.call_uuid = parent_sid or doc.call_uuid
    doc.call_status = params.get("CallStatus") or "initiated"
    doc.status = "Initiated"
    doc.response_json = json.dumps({"browser_leg_sid": parent_sid}, indent=2)
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return _xml(str(response))


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=600, seconds=60)
def status(call_log: str | None = None, token: str | None = None):
    params = validate_twilio_request()
    doc = _authorized_doc(call_log or params.get("call_log"), token or params.get("token"))
    if not doc:
        return _plain("IGNORED")
    _apply_status(doc, params, is_child=True)
    return _plain()


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=600, seconds=60)
def dial_complete(call_log: str | None = None, token: str | None = None):
    params = validate_twilio_request()
    doc = _authorized_doc(call_log or params.get("call_log"), token or params.get("token"))
    if not doc:
        response = VoiceResponse()
        response.hangup()
        return _xml(str(response))
    normalized = dict(params)
    normalized["CallSid"] = params.get("DialCallSid") or params.get("CallSid")
    normalized["CallStatus"] = params.get("DialCallStatus") or params.get("CallStatus")
    normalized["CallDuration"] = params.get("DialCallDuration") or params.get("CallDuration")
    _apply_status(doc, normalized, is_child=True)
    response = VoiceResponse()
    response.hangup()
    return _xml(str(response))


def _apply_status(doc, params: dict, *, is_child: bool = False) -> None:
    before = snapshot_doc(doc)
    provider_status = str(params.get("CallStatus") or "").strip().lower()
    # Do not let an out-of-order ringing/initiated callback regress a record
    # that has already reached a terminal provider outcome.
    late_nonterminal = (
        doc.status in {"Completed", "Failed", "Busy", "No Answer"}
        and provider_status not in TERMINAL
    )
    call_sid = params.get("CallSid") or ""
    if is_child and call_sid:
        doc.b_leg_uuid = call_sid
    elif call_sid:
        doc.a_leg_uuid = call_sid
    doc.call_uuid = doc.call_uuid or call_sid
    if not late_nonterminal:
        doc.call_status = provider_status or doc.call_status
        doc.event = provider_status or doc.event

    duration = frappe.utils.cint(
        params.get("CallDuration")
        or params.get("Duration")
        or params.get("duration")
        or 0
    )
    if duration:
        doc.duration = duration
        doc.billsec = duration

    mapped = {
        "queued": "Queued",
        "initiated": "Initiated",
        "ringing": "Ringing",
        "in-progress": "Connected",
        "completed": "Completed",
        "busy": "Busy",
        "failed": "Failed",
        "no-answer": "No Answer",
        "canceled": "Cancelled",
        "cancelled": "Cancelled",
    }.get(provider_status)
    if mapped and not late_nonterminal:
        doc.status = mapped
    if provider_status == "in-progress" and not late_nonterminal:
        doc.answer_time = doc.answer_time or frappe.utils.now()
        if doc.start_time and not doc.ring_time:
            try:
                doc.ring_time = max(
                    0,
                    int(
                        (
                            frappe.utils.get_datetime(doc.answer_time)
                            - frappe.utils.get_datetime(doc.start_time)
                        ).total_seconds()
                    ),
                )
            except Exception:
                pass
    if provider_status in TERMINAL:
        doc.end_time = doc.end_time or frappe.utils.now()

    # Save the state before append_callback(). append_callback() updates raw
    # callback fields atomically and bumps modified; reloading after it would
    # discard the status/duration changes and re-save stale values.
    doc = save_doc_latest(doc, before)
    append_callback(doc.name, provider_status or "status", params)
    if provider_status in TERMINAL:
        restore_mapping_after_call(doc.name)
        sync_linked_summaries(doc)
    frappe.db.commit()


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=300, seconds=60)
def recording_status(call_log: str | None = None, token: str | None = None):
    params = validate_twilio_request()
    doc = _authorized_doc(call_log or params.get("call_log"), token or params.get("token"))
    settings = get_settings()
    if not doc or not frappe.utils.cint(settings.enabled) or not frappe.utils.cint(settings.enable_recording):
        return _plain("IGNORED")
    recording_sid = params.get("RecordingSid") or ""
    recording_url = params.get("RecordingUrl") or ""
    status_value = str(params.get("RecordingStatus") or "").lower()
    doc.recording_id = recording_sid or doc.recording_id
    doc.recording_call_uuid = params.get("CallSid") or doc.recording_call_uuid
    doc.recording_url = recording_url or doc.recording_url
    doc.recording_duration = frappe.utils.cint(params.get("RecordingDuration") or 0)
    doc.recording_duration_ms = doc.recording_duration
    doc.recording_status = "Completed" if status_value == "completed" else "Started"
    doc.recording_completed_at = frappe.utils.now() if status_value == "completed" else None
    settings = get_settings()
    transcription_enabled = (
        frappe.utils.cint(settings.enabled)
        and frappe.utils.cint(settings.enable_recording)
        and frappe.utils.cint(settings.enable_transcription)
    )
    if status_value == "completed" and transcription_enabled:
        doc.transcript_status = "Requested"
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    if status_value == "completed" and transcription_enabled:
        frappe.enqueue(
            "twilio_click_to_call.services.transcription.transcribe_recording",
            queue="long",
            timeout=900,
            call_log=doc.name,
            enqueue_after_commit=True,
        )
    return _plain()
