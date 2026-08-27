from __future__ import annotations

import frappe
from frappe import _
from twilio.rest import Client

from twilio_click_to_call.services.settings import (
    get_auth_credentials,
    get_caller_ids,
    get_webhook_base_url,
)


def _manager_only() -> None:
    if frappe.session.user != "Administrator" and "System Manager" not in frappe.get_roles():
        frappe.throw(_("System Manager role is required."), frappe.PermissionError)


def assert_crm_twilio_disabled() -> None:
    if (
        frappe.db.exists("DocType", "CRM Twilio Settings")
        and frappe.utils.cint(
            frappe.db.get_single_value("CRM Twilio Settings", "enabled") or 0
        )
    ):
        frappe.throw(
            _(
                "CRM's built-in Twilio integration is enabled. Disable it before enabling "
                "Twilio Click To Call so one browser does not register two Twilio devices."
            )
        )


@frappe.whitelist()
def repair_schema_registration() -> dict:
    """Repair module registration when a development bench has a stale module map."""
    _manager_only()
    from frappe.installer import add_module_defs
    from frappe.model.sync import sync_for

    app_name = "twilio_click_to_call"
    module_name = "Twilio Click To Call"
    scrubbed_module = "twilio_click_to_call"
    if not frappe.db.exists("Module Def", module_name):
        add_module_defs(app_name, ignore_if_duplicate=True)
    frappe.local.app_modules = getattr(frappe.local, "app_modules", None) or {}
    frappe.local.app_modules.setdefault(app_name, [])
    if scrubbed_module not in frappe.local.app_modules[app_name]:
        frappe.local.app_modules[app_name].append(scrubbed_module)
    frappe.local.module_app = getattr(frappe.local, "module_app", None) or {}
    frappe.local.module_app[scrubbed_module] = app_name
    sync_for(app_name, force=True, reset_permissions=True)
    from twilio_click_to_call.install import ensure_defaults

    ensure_defaults()
    frappe.get_single("Installed Applications").update_versions()
    frappe.db.commit()
    return {"module": module_name, "synced": True}


@frappe.whitelist()
def get_setup_status() -> dict:
    _manager_only()
    settings = frappe.get_single("Twilio Settings")
    return {
        "enabled": bool(frappe.utils.cint(settings.enabled)),
        "crm_twilio_enabled": bool(
            frappe.db.exists("DocType", "CRM Twilio Settings")
            and frappe.utils.cint(
                frappe.db.get_single_value("CRM Twilio Settings", "enabled") or 0
            )
        ),
        "twiml_application_sid": settings.twiml_application_sid or "",
        "caller_ids": get_caller_ids(settings),
    }

@frappe.whitelist()
def sync_twilio_configuration() -> dict:
    """Create/update the TwiML App and point owned caller IDs at inbound routing."""
    _manager_only()
    assert_crm_twilio_disabled()
    settings = frappe.get_single("Twilio Settings")
    account_sid, auth_token = get_auth_credentials(settings)
    if not account_sid or not auth_token:
        frappe.throw(_("Twilio Account SID and Auth Token are required."))

    base_url = get_webhook_base_url(settings)
    outbound_url = (
        f"{base_url}/api/method/twilio_click_to_call.api.twiml.outbound"
    )
    inbound_url = (
        f"{base_url}/api/method/twilio_click_to_call.api.inbound.route"
    )
    client = Client(account_sid, auth_token)

    app_sid = settings.twiml_application_sid or ""
    if app_sid:
        application = client.applications(app_sid).update(
            friendly_name="Frappe Twilio Click To Call",
            voice_url=outbound_url,
            voice_method="POST",
        )
    else:
        application = client.applications.create(
            friendly_name="Frappe Twilio Click To Call",
            voice_url=outbound_url,
            voice_method="POST",
        )
        settings.twiml_application_sid = application.sid
        settings.save(ignore_permissions=True)

    synced_numbers: list[str] = []
    missing_numbers: list[str] = []
    for number in get_caller_ids(settings):
        matches = client.incoming_phone_numbers.list(phone_number=number, limit=20)
        if not matches:
            missing_numbers.append(number)
            continue
        for incoming in matches:
            client.incoming_phone_numbers(incoming.sid).update(
                voice_url=inbound_url,
                voice_method="POST",
            )
            synced_numbers.append(incoming.phone_number or number)

    frappe.db.commit()
    return {
        "application_sid": application.sid,
        "outbound_voice_url": outbound_url,
        "inbound_voice_url": inbound_url,
        "synced_numbers": synced_numbers,
        "missing_numbers": missing_numbers,
    }
