from __future__ import annotations

import frappe
from frappe import _
from twilio.request_validator import RequestValidator

from twilio_click_to_call.services.settings import get_auth_credentials, get_settings


def request_url() -> str:
    configured = (getattr(get_settings(), "webhook_base_url", "") or "").rstrip("/")
    path = frappe.request.path
    query = frappe.request.query_string.decode("utf-8") if frappe.request.query_string else ""
    if configured:
        return f"{configured}{path}" + (f"?{query}" if query else "")
    return frappe.request.url


def request_params() -> dict[str, str]:
    """Return query-string and form parameters for callback handlers."""
    params: dict[str, str] = {}
    if frappe.request:
        params.update(frappe.request.args.to_dict(flat=True))
        params.update(frappe.request.form.to_dict(flat=True))
    return params


def request_form_params() -> dict[str, str]:
    """Return only POST form parameters used for Twilio signature validation."""
    if frappe.request:
        return frappe.request.form.to_dict(flat=True)
    return {}


def validate_twilio_request() -> dict[str, str]:
    """Validate Twilio's webhook signature and return callback parameters."""
    params = request_params()
    signature_params = request_form_params()
    if frappe.conf.get("twilio_skip_signature_validation") and frappe.conf.get("developer_mode"):
        return params
    auth_token = get_auth_credentials()[1]
    signature = frappe.request.headers.get("X-Twilio-Signature", "") if frappe.request else ""
    if not auth_token or not signature:
        frappe.throw(_("Invalid Twilio webhook signature."), frappe.PermissionError)
    if not RequestValidator(auth_token).validate(request_url(), signature_params, signature):
        frappe.throw(_("Invalid Twilio webhook signature."), frappe.PermissionError)
    return params
