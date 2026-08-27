from __future__ import annotations

import re

import frappe
from frappe import _
from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import VoiceGrant

from twilio_click_to_call.api.call import get_user_mapping
from twilio_click_to_call.services.settings import get_settings, get_voice_credentials


def identity_for_user(user: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_]", "_", user or "")[:100]
    return f"frappe_{safe}"


@frappe.whitelist()
def get_token() -> dict:
    if frappe.session.user == "Guest":
        frappe.throw(_("Login required."))
    settings = get_settings()
    if not settings.enabled:
        frappe.throw(_("Twilio Click To Call is disabled."))
    if not get_user_mapping(frappe.session.user):
        frappe.throw(_("No active Twilio user mapping found."))

    account_sid, key_sid, key_secret, application_sid = get_voice_credentials(settings)
    if not all((account_sid, key_sid, key_secret, application_sid)):
        frappe.throw(
            _("Twilio Account SID, API Key SID, API Key Secret, and TwiML Application SID are required.")
        )

    identity = identity_for_user(frappe.session.user)
    token = AccessToken(account_sid, key_sid, key_secret, identity=identity, ttl=3600)
    token.add_grant(VoiceGrant(outgoing_application_sid=application_sid, incoming_allow=True))
    jwt = token.to_jwt()
    if isinstance(jwt, bytes):
        jwt = jwt.decode("utf-8")
    return {"token": jwt, "identity": identity, "ttl": 3600}
