# Twilio Click To Call

A standalone Frappe v15/ERPNext telephony app using Twilio Programmable Voice. It does not import or require `vobiz_click_to_call` or `vobiz_ai`.

## Features

- Agent-first outbound calls through the Twilio Voice JavaScript SDK.
- Incoming DID routing to the mapped agent's browser Client identity, with the existing assignment, fallback, availability, and working-hours rules.
- Click-to-call buttons, list dialer, Agent Console, analytics, call logs, CDR recovery, dispositions, and DND safeguards.
- Twilio request-signature validation on public webhook endpoints.
- Optional dual-channel recording, disabled by default.
- Optional OpenAI transcription using `gpt-4o-mini-transcribe`, followed by the existing AI disposition workflow.
- System Manager provisioning of the TwiML Application and owned incoming phone numbers.
- Coexistence guard that requires CRM's built-in Twilio integration to be disabled.

## Install

```bash
cd /home/srdev/frappe-bench-v15
./env/bin/pip install -e apps/twilio_click_to_call
bench --site <site> install-app twilio_click_to_call
bench build --app twilio_click_to_call
```

## Configure

1. Open **Twilio Settings**.
2. Enter the Account SID, Auth Token, API Key SID, API Key Secret, caller IDs, public HTTPS webhook base URL, and optionally an existing TwiML Application SID.
3. Save while disabled, then click **Sync Twilio Configuration** as System Manager.
4. Create one enabled **Twilio User Mapping** for every agent.
5. Disable **CRM Twilio Settings** if that integration is active.
6. Enable this app's settings.
7. Allow microphone access in the agents' browsers.

Recording is opt-in. Confirm consent, retention, and regional calling/recording requirements before enabling it. For transcription, configure the OpenAI API key in Twilio Settings or site config.

## Twilio endpoints

- TwiML App Voice URL: `/api/method/twilio_click_to_call.api.twiml.outbound`
- Incoming number Voice URL: `/api/method/twilio_click_to_call.api.inbound.route`

The **Sync Twilio Configuration** button configures both URLs against the selected public webhook base URL.
