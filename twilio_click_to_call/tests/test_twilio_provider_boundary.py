from __future__ import annotations

import json
from pathlib import Path
import unittest


APP = Path(__file__).resolve().parents[1]


class TestTwilioProviderBoundary(unittest.TestCase):
    def test_runtime_has_no_old_app_imports(self):
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in APP.rglob("*.py")
            if "tests" not in path.parts
        )
        self.assertNotIn("from vobiz", source)
        self.assertNotIn("import vobiz", source)
        self.assertNotIn("from twilio_ai", source)
        self.assertNotIn("import twilio_ai", source)

    def test_standard_workspace_exposes_main_operational_surfaces(self):
        path = (
            APP
            / "twilio_click_to_call"
            / "workspace"
            / "twilio_click_to_call"
            / "twilio_click_to_call.json"
        )
        workspace = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(workspace["module"], "Twilio Click To Call")
        self.assertEqual(workspace["public"], 1)
        self.assertEqual(workspace["is_hidden"], 0)

        shortcuts = {
            row["label"]: (row["type"], row["link_to"])
            for row in workspace["shortcuts"]
        }
        self.assertEqual(
            shortcuts,
            {
                "Agent Console": ("Page", "twilio-agent-console"),
                "Agent Analytics": ("Page", "twilio-agent-analytics"),
                "Call Logs": ("DocType", "Twilio Call Log"),
                "Incoming Routing": ("DocType", "Twilio Incoming Mapping"),
                "User Mapping": ("DocType", "Twilio User Mapping"),
                "Blocked Numbers": ("DocType", "Twilio Blocked Number"),
                "Error Logs": ("DocType", "Twilio Error Log"),
                "Settings": ("DocType", "Twilio Settings"),
            },
        )
        content = json.loads(workspace["content"])
        content_shortcuts = {
            row["data"]["shortcut_name"]
            for row in content
            if row["type"] == "shortcut"
        }
        self.assertEqual(content_shortcuts, set(shortcuts))

    def test_settings_define_voice_sdk_credentials_and_opt_in_recording(self):
        path = (
            APP
            / "twilio_click_to_call"
            / "doctype"
            / "twilio_settings"
            / "twilio_settings.json"
        )
        settings = json.loads(path.read_text(encoding="utf-8"))
        fields = {field["fieldname"]: field for field in settings["fields"]}
        for fieldname in (
            "account_sid",
            "auth_token",
            "api_key_sid",
            "api_key_secret",
            "twiml_application_sid",
        ):
            self.assertIn(fieldname, fields)
        self.assertEqual(fields["enable_recording"]["default"], "0")
        self.assertEqual(
            fields["transcription_model"]["default"], "gpt-4o-mini-transcribe"
        )
        self.assertEqual(fields["default_call_flow"]["default"], "Agent First")

    def test_official_twilio_sdk_is_the_provider_boundary(self):
        client = (APP / "services" / "client.py").read_text(encoding="utf-8")
        device = (APP / "api" / "device.py").read_text(encoding="utf-8")
        webhooks = (APP / "services" / "webhooks.py").read_text(encoding="utf-8")
        self.assertIn("from twilio.rest import Client", client)
        self.assertIn("VoiceGrant", device)
        self.assertIn("RequestValidator", webhooks)
        self.assertIn("developer_mode", webhooks)
        self.assertNotIn("X-Auth-ID", client)

    def test_browser_softphone_connects_with_prepared_params(self):
        softphone = (APP / "public" / "js" / "softphone.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("new window.Twilio.Device", softphone)
        self.assertIn("device.register()", softphone)
        self.assertIn("currentDevice.connect({params})", softphone)

    def test_background_token_request_is_silent_for_unmapped_desk_users(self):
        softphone = (APP / "public" / "js" / "softphone.js").read_text(
            encoding="utf-8"
        )
        token_request = softphone[
            softphone.index("function fetchToken()") : softphone.index(
                "async function ensureDevice"
            )
        ]
        self.assertIn(
            'method: "twilio_click_to_call.api.device.get_token"',
            token_request,
        )
        self.assertIn("silent: true", token_request)
        self.assertIn("ensureDevice(true).catch(() =>", softphone)

    def test_public_twiml_callbacks_validate_twilio_signatures(self):
        twiml = (APP / "api" / "twiml.py").read_text(encoding="utf-8")
        inbound = (APP / "api" / "inbound.py").read_text(encoding="utf-8")
        self.assertGreaterEqual(twiml.count("validate_twilio_request()"), 4)
        self.assertIn("validate_twilio_request()", inbound)

    def test_webhook_validator_preserves_translation_function(self):
        webhooks = (APP / "services" / "webhooks.py").read_text(encoding="utf-8")
        self.assertIn("auth_token = get_auth_credentials()[1]", webhooks)
        self.assertNotIn("_, auth_token = get_auth_credentials()", webhooks)

    def test_webhook_signature_does_not_duplicate_query_parameters(self):
        webhooks = (APP / "services" / "webhooks.py").read_text(encoding="utf-8")
        request_params = webhooks[
            webhooks.index("def request_params()") : webhooks.index(
                "def validate_twilio_request()"
            )
        ]
        self.assertIn("frappe.request.form.to_dict(flat=True)", request_params)
        self.assertIn("frappe.request.args.to_dict(flat=True)", request_params)
        self.assertIn("def request_form_params()", webhooks)
        self.assertIn("signature_params = request_form_params()", webhooks)


if __name__ == "__main__":
    unittest.main()
