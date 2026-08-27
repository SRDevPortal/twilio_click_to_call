from __future__ import annotations

from datetime import datetime
from typing import Any

import frappe
from frappe import _
from twilio.rest import Client

from twilio_click_to_call.services.settings import get_auth_credentials, get_settings


class TwilioClient:
    """Small adapter around the official Twilio Python SDK."""

    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self.account_sid, self.auth_token = get_auth_credentials(self.settings)
        if not self.account_sid or not self.auth_token:
            frappe.throw(_("Twilio Account SID and Auth Token are not configured."))
        self.client = Client(self.account_sid, self.auth_token)

    def make_call(self, payload: dict[str, Any]) -> dict[str, Any]:
        call = self.client.calls.create(
            to=payload["to"],
            from_=payload["from"],
            url=payload["answer_url"],
            method=payload.get("answer_method", "POST"),
            fallback_url=payload.get("fallback_url"),
            fallback_method=payload.get("fallback_method", "POST"),
            status_callback=payload.get("hangup_url"),
            status_callback_method=payload.get("hangup_method", "POST"),
            status_callback_event=["initiated", "ringing", "answered", "completed"],
            timeout=int(payload.get("timeout") or getattr(self.settings, "agent_ring_timeout", 30) or 30),
        )
        return _call_dict(call)

    def start_call_recording(self, call_sid: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not call_sid:
            frappe.throw(_("Twilio Call SID is required to start recording."))
        recording = self.client.calls(call_sid).recordings.create(
            recording_status_callback=payload.get("callback_url"),
            recording_status_callback_method=payload.get("callback_method", "POST"),
            recording_channels=(
                "dual"
                if payload.get("record_channel_type") == "stereo"
                else "mono"
            ),
            trim="trim-silence",
        )
        return {
            "recording_id": recording.sid,
            "recording_sid": recording.sid,
            "call_sid": recording.call_sid,
            "status": recording.status,
            "url": recording.uri,
        }

    def hangup_call(self, call_sid: str) -> dict[str, Any]:
        if not call_sid:
            frappe.throw(_("Twilio Call SID is required to cancel a call."))
        call = self.client.calls(call_sid).update(status="completed")
        return _call_dict(call)

    def retrieve_live_call(self, call_sid: str, status: str = "live") -> dict[str, Any]:
        if not call_sid:
            frappe.throw(_("Twilio Call SID is required."))
        return _call_dict(self.client.calls(call_sid).fetch())

    def search_cdrs(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        call_sid = params.get("call_uuid") or params.get("request_uuid")
        if call_sid:
            try:
                return {"objects": [_call_dict(self.client.calls(str(call_sid)).fetch())]}
            except Exception:
                return {"objects": []}

        kwargs: dict[str, Any] = {"limit": min(int(params.get("limit") or 100), 1000)}
        if params.get("from"):
            kwargs["from_"] = params["from"]
        if params.get("to"):
            kwargs["to"] = params["to"]
        start = params.get("start_date") or params.get("date")
        end = params.get("end_date")
        if start:
            kwargs["start_time_after"] = datetime.fromisoformat(str(start))
        if end:
            kwargs["start_time_before"] = datetime.fromisoformat(str(end))
        elif params.get("date"):
            kwargs["start_time_before"] = frappe.utils.add_days(
                datetime.fromisoformat(str(params["date"])), 1
            )
        return {"objects": [_call_dict(call) for call in self.client.calls.list(**kwargs)]}


def _call_dict(call) -> dict[str, Any]:
    direction = str(getattr(call, "direction", "") or "")
    return {
        "sid": getattr(call, "sid", None),
        "uuid": getattr(call, "sid", None),
        "call_uuid": getattr(call, "sid", None),
        "parent_call_sid": getattr(call, "parent_call_sid", None),
        "account_sid": getattr(call, "account_sid", None),
        "from": getattr(call, "from_", None),
        "to": getattr(call, "to", None),
        "caller_id_number": getattr(call, "from_", None),
        "destination_number": getattr(call, "to", None),
        "direction": "inbound" if direction == "inbound" else "outbound",
        "status": getattr(call, "status", None),
        "call_status": getattr(call, "status", None),
        "start_time": getattr(call, "start_time", None),
        "end_time": getattr(call, "end_time", None),
        "duration": getattr(call, "duration", None),
        "billsec": getattr(call, "duration", None),
        "price": getattr(call, "price", None),
        "cost": getattr(call, "price", None),
        "currency": getattr(call, "price_unit", None) or "USD",
        "uri": getattr(call, "uri", None),
    }


def extract_provider_id(payload: dict[str, Any] | None, *keys: str) -> str:
    if not isinstance(payload, dict):
        return ""
    aliases = {
        "call_uuid": ("call_sid", "sid"),
        "CallUUID": ("CallSid", "sid"),
        "uuid": ("sid",),
        "request_uuid": ("call_sid", "sid"),
        "recording_id": ("recording_sid", "sid"),
    }
    for key in keys:
        for candidate in (key, *aliases.get(key, ())):
            value = payload.get(candidate)
            if value:
                return str(value)
    data = payload.get("data")
    return extract_provider_id(data, *keys) if isinstance(data, dict) else ""
