from __future__ import annotations

from urllib.parse import urlparse

import requests

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from werkzeug.wrappers import Response

from twilio_click_to_call.services.recording import provider_recording_url
from twilio_click_to_call.services.settings import get_auth_credentials, get_settings

MAX_RECORDING_BYTES = 100 * 1024 * 1024


@frappe.whitelist()
@rate_limit(limit=30, seconds=60)
def download(call_log: str):
    if frappe.session.user == "Guest":
        frappe.throw(_("Login required."))

    doc = frappe.get_doc("Twilio Call Log", call_log)
    if not _can_access_recording(doc):
        frappe.throw(_("Not permitted."))
    if not doc.recording_url and not doc.recording_id:
        frappe.throw(_("Recording URL is not available yet."))

    settings = get_settings()
    if not frappe.utils.cint(settings.enabled) or not frappe.utils.cint(settings.enable_recording):
        frappe.throw(_("Twilio Recording is disabled."))
    media_url = provider_recording_url(doc, settings)
    if not _is_allowed_recording_url(media_url, doc=doc, settings=settings):
        frappe.throw(_("Recording URL is not trusted."))
    account_sid, auth_token = get_auth_credentials(settings)
    if not account_sid or not auth_token:
        frappe.throw(_("Twilio Account SID and Auth Token are not configured."))

    response = requests.get(
        _media_url(media_url),
        auth=(account_sid, auth_token),
        timeout=int(settings.http_timeout or 20),
        stream=True,
    )
    if response.status_code >= 400:
        reason = response.reason or str(response.status_code)
        response.close()
        frappe.throw(_("Unable to fetch Twilio recording: {0}").format(reason))

    content_length = frappe.utils.cint(response.headers.get("Content-Length"))
    if content_length and content_length > MAX_RECORDING_BYTES:
        response.close()
        frappe.throw(_("Recording is too large to proxy through the application server."))

    extension = _extension_from_url(doc.recording_url)

    def generate():
        received = 0
        try:
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                received += len(chunk)
                if received > MAX_RECORDING_BYTES:
                    raise RuntimeError("Recording exceeded the application proxy size limit.")
                yield chunk
        finally:
            response.close()

    return Response(
        generate(),
        headers={
            "Content-Disposition": f'attachment; filename="{doc.name}{extension}"',
            "Cache-Control": "private, no-store",
        },
        content_type=response.headers.get("Content-Type") or _content_type(extension),
        direct_passthrough=True,
    )


@frappe.whitelist()
@rate_limit(limit=120, seconds=60)
def stream(call_log: str):
    if frappe.session.user == "Guest":
        frappe.throw(_("Login required."))

    doc = frappe.get_doc("Twilio Call Log", call_log)
    if not _can_access_recording(doc):
        frappe.throw(_("Not permitted."))
    if not doc.recording_url and not doc.recording_id:
        frappe.throw(_("Recording URL is not available yet."))

    settings = get_settings()
    if not frappe.utils.cint(settings.enabled) or not frappe.utils.cint(settings.enable_recording):
        frappe.throw(_("Twilio Recording is disabled."))
    media_url = provider_recording_url(doc, settings)
    if not _is_allowed_recording_url(media_url, doc=doc, settings=settings):
        frappe.throw(_("Recording URL is not trusted."))
    account_sid, auth_token = get_auth_credentials(settings)
    if not account_sid or not auth_token:
        frappe.throw(_("Twilio Account SID and Auth Token are not configured."))

    headers = {}
    range_header = (getattr(frappe.request, "headers", {}) or {}).get("Range")
    if range_header:
        headers["Range"] = range_header

    response = requests.get(
        _media_url(media_url),
        auth=(account_sid, auth_token),
        headers=headers,
        timeout=int(settings.http_timeout or 20),
        stream=True,
    )
    if response.status_code >= 400:
        reason = response.reason or str(response.status_code)
        response.close()
        frappe.throw(_("Unable to fetch Twilio recording: {0}").format(reason))
    content_length = frappe.utils.cint(response.headers.get("Content-Length"))
    if content_length and content_length > MAX_RECORDING_BYTES:
        response.close()
        frappe.throw(_("Recording is too large to proxy through the application server."))

    extension = _extension_from_url(doc.recording_url)
    response_headers = {
        "Accept-Ranges": response.headers.get("Accept-Ranges", "bytes"),
        "Cache-Control": "private, max-age=300",
        "Content-Disposition": f'inline; filename="{doc.name}{extension}"',
    }
    for header in ("Content-Range", "Content-Length"):
        if response.headers.get(header):
            response_headers[header] = response.headers[header]

    def generate():
        received = 0
        try:
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if chunk:
                    received += len(chunk)
                    if received > MAX_RECORDING_BYTES:
                        raise RuntimeError("Recording exceeded the application proxy size limit.")
                    yield chunk
        finally:
            response.close()

    return Response(
        generate(),
        status=response.status_code,
        headers=response_headers,
        content_type=response.headers.get("Content-Type") or _content_type(extension),
        direct_passthrough=True,
    )


def recording_proxy_url(call_log: str) -> str:
    return f"/api/method/twilio_click_to_call.api.recording.stream?call_log={frappe.utils.quote(call_log)}"


def recording_download_url(call_log: str) -> str:
    return f"/api/method/twilio_click_to_call.api.recording.download?call_log={frappe.utils.quote(call_log)}"


def _can_access_recording(doc) -> bool:
    if "System Manager" in frappe.get_roles():
        return True

    user = frappe.session.user
    for fieldname in ("user", "owner", "linked_owner"):
        if doc.get(fieldname) == user:
            return True

    if frappe.has_permission(doc=doc, ptype="read"):
        return True

    for doctype, fieldname in (("CRM Lead", "crm_lead"), ("Patient", "patient")):
        linked_name = doc.get(fieldname)
        if linked_name and frappe.has_permission(doctype, "read", doc=linked_name):
            return True

    return False


def _is_allowed_recording_url(url: str, doc=None, settings=None) -> bool:
    parsed = urlparse(url or "")
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https":
        return False
    if host == "twilio.com" or host.endswith(".twilio.com"):
        return True
    # Support Twilio external-storage URLs while preventing arbitrary proxying:
    # the object path must contain this account and recording SID.
    if host.endswith(".amazonaws.com") and doc is not None:
        settings = settings or get_settings()
        account_sid, _ = get_auth_credentials(settings)
        recording_id = str(doc.get("recording_id") or "").strip()
        expected = f"/{account_sid}/{recording_id}"
        return bool(account_sid and recording_id and parsed.path.startswith(expected))
    return False


def _media_url(url: str) -> str:
    return url if url.lower().endswith((".mp3", ".wav")) else f"{url}.mp3"


def _extension_from_url(url: str) -> str:
    path = urlparse(url or "").path.lower()
    for extension in (".mp3", ".wav", ".m4a", ".ogg"):
        if path.endswith(extension):
            return extension
    return ".mp3"


def _content_type(extension: str) -> str:
    return {
        ".wav": "audio/wav",
        ".m4a": "audio/mp4",
        ".ogg": "audio/ogg",
    }.get(extension, "audio/mpeg")
