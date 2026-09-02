from __future__ import annotations

import json
import re
import secrets
from typing import Any

import frappe

from twilio_click_to_call.services.numbers import normalize_phone_number


def make_outbound_call_key() -> str:
    return f"TWI-CTC-{secrets.token_urlsafe(18)}"


def last10(value: str | None) -> str:
    digits = re.sub(r"\D+", "", value or "")
    return digits[-10:] if len(digits) >= 10 else digits


def as_json(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False, indent=2, default=str)


def parse_json(value: Any) -> Any:
    if isinstance(value, str):
        return frappe.parse_json(value)
    return value


def find_by_phone(doctype: str, fields: tuple[str, ...], number: str) -> str | None:
    key = last10(number)
    if not key or not frappe.db.exists("DocType", doctype):
        return None
    conditions: list[str] = []
    values: list[str] = []
    for fieldname in fields:
        if not frappe.db.has_column(doctype, fieldname):
            continue
        conditions.append(
            f"REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(`{fieldname}`, '+', ''), ' ', ''), '-', ''), '(', ''), ')', '') LIKE %s"
        )
        values.append(f"%{key}")
    if not conditions:
        return None
    rows = frappe.db.sql(
        f"SELECT name FROM `tab{doctype}` WHERE ({' OR '.join(conditions)}) ORDER BY modified DESC LIMIT 1",
        values,
        as_dict=True,
    )
    return rows[0].name if rows else None


def create_outbound_call_log(
    *,
    reference_doctype: str,
    reference_name: str,
    phone_field: str | None,
    customer_number: str,
    user_mobile: str,
    caller_id: str,
    call_flow: str = "Agent First",
    user: str | None = None,
    callback_token: str | None = None,
):
    doc = frappe.get_doc(
        {
            "doctype": "Twilio Call Log",
            "call_key": make_outbound_call_key(),
            "source_app": "twilio_click_to_call",
            "reference_doctype": reference_doctype,
            "reference_name": reference_name,
            "phone_field": phone_field,
            "user": user or frappe.session.user,
            "user_mobile": user_mobile,
            "agent_number": user_mobile,
            "customer_number": customer_number,
            "normalized_customer_number": normalize_phone_number(customer_number),
            "caller_id": caller_id,
            "did_number": caller_id,
            "normalized_did": normalize_phone_number(caller_id),
            "call_flow": "Agent First",
            "direction": "Outgoing",
            "status": "Queued",
            "start_time": frappe.utils.now(),
            "callback_token": callback_token or secrets.token_urlsafe(24),
            "recording_status": "Not Started",
            "transcript_status": "Not Requested",
            "ai_status": "Pending",
            "ai_disposition_status": "Not Requested",
            "cdr_sync_status": "Not Synced",
            "currency": "USD",
        }
    )
    sync_reference_links(doc)
    doc.insert(ignore_permissions=True)
    return doc


def append_callback(call_log: str, event: str, payload: dict) -> None:
    if not frappe.db.exists("Twilio Call Log", call_log):
        return
    doc = frappe.get_doc("Twilio Call Log", call_log)
    try:
        rows = json.loads(doc.raw_callbacks or "[]")
    except Exception:
        rows = []
    safe_payload = dict(payload or {})
    safe_payload.pop("token", None)
    safe_payload.pop("cmd", None)
    rows.append({"event": event, "received_at": frappe.utils.now(), "payload": safe_payload})
    doc.raw_callbacks = as_json(rows[-50:])
    doc.raw_payload = as_json({"callbacks": rows[-50:]})
    frappe.db.set_value("Twilio Call Log", call_log, {"raw_callbacks": doc.raw_callbacks, "raw_payload": doc.raw_payload}, update_modified=True)


def sync_reference_links(call_log_doc) -> None:
    if call_log_doc.reference_doctype == "CRM Lead":
        call_log_doc.crm_lead = call_log_doc.reference_name
    elif call_log_doc.reference_doctype == "Patient":
        call_log_doc.patient = call_log_doc.reference_name

    if call_log_doc.crm_lead or call_log_doc.patient:
        return
    number = call_log_doc.customer_number or call_log_doc.normalized_customer_number
    if not number:
        return
    call_log_doc.patient = find_by_phone("Patient", ("mobile", "phone"), number)
    call_log_doc.crm_lead = find_by_phone("CRM Lead", ("mobile_no", "phone"), number)
    if call_log_doc.patient:
        call_log_doc.caller_classification = "Patient"
    elif call_log_doc.crm_lead:
        call_log_doc.caller_classification = "Old Lead"


def sync_linked_summaries(call_log_doc) -> None:
    """Refresh optional reference metrics without requiring another telephony app."""
    try:
        from twilio_click_to_call.services.disposition import update_reference_call_metrics

        if call_log_doc.reference_doctype and call_log_doc.reference_name:
            update_reference_call_metrics(call_log_doc.reference_doctype, call_log_doc.reference_name)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Twilio linked summary sync failed")
