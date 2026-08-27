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

    def test_public_twiml_callbacks_validate_twilio_signatures(self):
        twiml = (APP / "api" / "twiml.py").read_text(encoding="utf-8")
        inbound = (APP / "api" / "inbound.py").read_text(encoding="utf-8")
        self.assertGreaterEqual(twiml.count("validate_twilio_request()"), 4)
        self.assertIn("validate_twilio_request()", inbound)


if __name__ == "__main__":
    unittest.main()
