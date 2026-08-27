# Twilio Click-to-Call Setup and Configuration

This runbook configures the installed twilio_click_to_call app on:

- Bench: /home/srdev/eternity-bench
- Site: eternity.localhost
- App version: 0.1.0

The app is installed, migrated, asset-built, tested, and disabled. It is standalone and does not depend on vobiz_click_to_call or vobiz_ai.

## Production warning

Use the current build for controlled configuration and staging only. Before production cutover, resolve the gaps in the [implementation plan](twilio_click_to_call_implementation_plan.md), especially explicit Go Online, single-tab Device ownership, hashed identities, provisioning preview/audit/rollback, and browser acceptance tests.

Do not put Account SID, Auth Token, API Key Secret, OpenAI key, callback tokens, or other credentials in this file, Git, screenshots, tickets, or chat. Store secrets in the Password fields of Twilio Settings or protected site configuration managed by the deployment secret process.

## Call architecture

Outbound:

1. A logged-in mapped agent prepares a call from an allowed document.
2. The server checks permissions, DND, limits, mapping, caller ID, and availability.
3. The browser connects through Twilio Voice SDK.
4. Twilio requests the app's outbound TwiML endpoint.
5. TwiML dials the customer and signed callbacks update Twilio Call Log.

Inbound:

1. A customer calls a Twilio DID listed in Twilio Settings Caller IDs.
2. Twilio posts to the app's inbound route.
3. The app validates signature, account, and DID, then selects an available mapped user.
4. TwiML dials that user's browser Client identity; configured fallbacks follow.
5. Signed callbacks update state and restore availability.

## 1. Prerequisites

Prepare:

- An organization-controlled Twilio account or staging subaccount.
- Account SID (AC...) and Auth Token.
- API Key SID (SK...) and its one-time secret. The current app does not create this key; create it manually in Twilio Console.
- At least one voice-capable Twilio number in E.164 format.
- A stable, public HTTPS base URL for the Frappe site. Localhost and private addresses are rejected. Use a tunnel only for controlled staging.
- Reverse proxy forwarding that preserves the external scheme, host, path, and query used for signature validation.
- Running Frappe web, Socket.IO, scheduler, workers, Redis cache, and Redis queue.
- Supported desktop browsers with microphone permission and networks allowing Twilio WebRTC.
- Named owners for Twilio, Frappe, security, compliance, and rollback.

Configuration worksheet - fill outside source control:

| Value | Placeholder |
| --- | --- |
| Public HTTPS base URL | https://public-frappe-host |
| Twilio Account SID | AC... |
| Twilio Auth Token | Secret - do not record here |
| API Key SID | SK... |
| API Key Secret | Secret - do not record here |
| Caller IDs | One E.164 number per line |
| Default country code | +91 unless requirements differ |
| Pilot agent users | Frappe user IDs |
| Pilot incoming DID | E.164 number |
| Recording approval | Not approved or approval reference |
| Cutover owner/window | Owner and date-time |

## 2. Verify installation

Run from WSL:

~~~bash
cd /home/srdev/eternity-bench
bench --site eternity.localhost list-apps | grep twilio_click_to_call
bench --site eternity.localhost execute twilio_click_to_call.api.provisioning.get_setup_status
~~~

Expected initial state:

~~~json
{
  enabled: false,
  crm_twilio_enabled: false,
  twiml_application_sid: ",
  caller_ids: []
}
~~~

An existing application SID or caller IDs are acceptable only when deliberately configured. Never expose secret-bearing command output.

## 3. Disable competing integrations

In Frappe Desk:

1. Open CRM Twilio Settings if it exists.
2. Clear Enabled and save.
3. Confirm no other custom app creates a Twilio Voice SDK Device for the same user.
4. Leave Vobiz installed for history and rollback, but do not run two calling integrations for pilot agents.

The app refuses Twilio synchronization while CRM's built-in Twilio integration is enabled.

## 4. Configure Twilio Settings

Open Twilio Settings as System Manager. Keep the application disabled during setup. If API fields are hidden, temporarily select Enabled to reveal them, enter values, clear Enabled again, then save.

### Required API values

| Field | Value |
| --- | --- |
| Account SID | Twilio account SID beginning AC |
| Auth Token | Twilio Auth Token stored as Password |
| API Key SID | Twilio API Key SID beginning SK |
| API Key Secret | Key secret stored as Password |
| TwiML Application SID | Leave blank for first sync, or enter an explicitly owned AP SID |
| Caller IDs | Voice-capable Twilio DIDs in E.164, one per line |
| Default Country Code | Prefix for local number normalization; default +91 |
| Webhook Base URL | Public HTTPS origin without /app, /desk, /login, or /api |

### Recommended initial values

| Field | Initial value | Notes |
| --- | --- | --- |
| Allowed DocTypes | CRM Lead, Contact, Patient, Customer | Patient Encounter and Issue are also included internally |
| Default Call Flow | Agent First | Read-only |
| Prefer Current Lead Assignment | Enabled | Prefer existing lead owner for inbound calls |
| Agent Ring Timeout | 30 seconds | Adjust only after staging evidence |
| Max Call Duration | 3600 seconds | Approved safety ceiling |
| End Fallback | Disabled | Enable only with an approved E.164 destination |
| Busy Callback AI Fallback | Disabled | Enable only after route acceptance |
| Prevent Blocked Numbers | Enabled | Keep enabled |
| Max Attempts Per Record Per Day | Set a business limit | Zero means unlimited |
| Max Calls Per User Per Day | Set a business limit | Zero means unlimited |
| HTTP Timeout | 20 seconds | Default |
| Store Raw Callback Payloads | Enabled for staging | Review retention before production |
| CDR Sync | Enabled, 7-day lookback | Default |

Keep Recording, Transcription, AI Disposition, Auto Apply AI Disposition, and fallback features disabled for initial validation. Enable recording only after consent, retention, deletion, access, and regional requirements are approved.

For later approved use:

- Default transcription model: gpt-4o-mini-transcribe.
- Default AI model: gpt-4.1-mini.
- Sync AI choices from active SR Lead Disposition records.
- Keep automatic disposition application off until separately accepted.
- Keep manual review for results below the confidence threshold.

Save while Enabled remains cleared.

## 5. Create Twilio User Mappings

Create one mapping per pilot agent:

| Field | Guidance |
| --- | --- |
| User | Enabled Frappe user operating the browser softphone |
| Enabled | Enable only for a controlled pilot |
| Queue Source | CRM Lead, Patient, both, Patient Encounter, Issue, or Discontinued |
| Agent Mobile | Required by the schema; use approved E.164. Normal user inbound routing uses the Client identity |
| Twilio Number | Select a DID from Settings Caller IDs |
| Accept Calls | Enable for incoming-call pilots |
| Availability Status | Start Offline; go online only during the test window |
| Auto Available After Call | Normally enabled |
| Working Hours | Enable with start/end/days when required |
| Fallback User(s) | Enabled mapped users in priority order; avoid loops |
| Team / Team Leader / Pipeline | Fill when used for reporting and visibility |

Saving an enabled mapping assigns the Twilio Agent role. Patient queues also require Department and Follow Up ID; Regional routing additionally requires Disease and Language.

## 6. Configure incoming DID routing

For each number, create a Twilio Incoming Mapping:

1. Enter DID Number in E.164 format.
2. Select Round Robin or Load Balancing.
3. Set the default CRM Lead status and optional pipeline, platform, and source for unknown callers.
4. Add enabled rows with Agent User, required Agent Mobile, and priority.
5. Confirm every row's user has an enabled Twilio User Mapping.
6. Save and confirm the normalized DID matches a Settings Caller ID.

Add prohibited destinations to Twilio Blocked Number. Confirm source documents are marked Do Not Call where applicable.

## 7. Provision Twilio resources

Current behavior matters: Sync Twilio Configuration performs immediate Twilio writes. It has no preview, audit, rollback, or API-key creation.

For controlled staging:

1. Export the current TwiML Application Voice URL and selected phone-number Voice URLs to a restricted change record.
2. Reconfirm CRM Twilio Settings is disabled.
3. Open Twilio Settings and click Sync Twilio Configuration once.
4. If the application SID was blank, the app creates Frappe Twilio Click To Call and saves its AP SID.
5. It sets the TwiML Application Voice URL, method POST, to:

   https://public-frappe-host/api/method/twilio_click_to_call.api.twiml.outbound

6. It sets each owned Caller ID's incoming Voice URL, method POST, to:

   https://public-frappe-host/api/method/twilio_click_to_call.api.inbound.route

7. Review returned synced_numbers and missing_numbers.
8. Verify the exact application SID, URLs, methods, and number assignments in Twilio Console.

Do not sync shared or production numbers until preview/audit/rollback exists or an approved manual rollback record has been captured.

## 8. Validate before enabling

Run:

~~~bash
cd /home/srdev/eternity-bench
bench --site eternity.localhost run-tests --app twilio_click_to_call --skip-test-records --skip-before-tests
~~~

Expected for version 0.1.0: 128 tests pass.

Then confirm:

- The HTTPS hostname serves the intended Frappe site without redirecting to localhost or another host.
- Twilio reaches both Voice URLs over HTTPS.
- Invalid or unsigned requests are rejected. Do not weaken validation to make manual curl requests pass.
- Web, workers, scheduler, Socket.IO, Redis cache, and Redis queue remain healthy.
- Twilio Debugger has no DNS, TLS, signature, timeout, or application errors.
- Twilio Error Log contains no unexpected failures.

## 9. Controlled staging acceptance

Use one pilot DID and one or two pilot agents. Enable Twilio Settings only for the test window.

Capture evidence for:

- Outbound connected, busy, no-answer, rejected, canceled, and hangup.
- Inbound known lead, known patient, unknown caller, accept, reject, timeout, and fallback.
- Correct browser parent and PSTN child Call SIDs in Twilio Call Log.
- Duplicate and out-of-order callback handling.
- Mute, hangup, timer, log navigation, disposition, and availability restoration.
- Microphone denied, refresh, token refresh, network loss, and reconnect.
- Two tabs for one user; production requires exactly one Device owner.
- DND, blocked number, document access, limits, hours, and unavailable-agent enforcement.
- CDR reconciliation of duration, cost, status, and missing inbound calls.

Twilio test credentials do not execute TwiML or send normal callbacks. Final staging acceptance requires a controlled live number.

## 10. Production activation

Do not activate until the implementation plan's final acceptance criteria pass.

1. Take and verify a site/database backup.
2. Export current Twilio and Vobiz webhook values.
3. Confirm mappings, DIDs, permissions, limits, hours, and fallbacks.
4. Confirm CRM Twilio is disabled.
5. Apply reviewed Twilio provisioning.
6. Make one controlled inbound and outbound call.
7. Disable Vobiz calling without uninstalling apps or deleting history.
8. Enable Twilio Settings.
9. Bring pilot agents online, monitor, and expand gradually.

## 11. Rollback

1. Clear Twilio Settings Enabled.
2. Mark mappings unavailable or offline.
3. Restore previous TwiML Application and phone-number Voice URLs. Use automated rollback when implemented.
4. Re-enable Vobiz only with business approval and known-good configuration.
5. Preserve Twilio Call Logs, Error Logs, Vobiz history, and incident evidence.
6. Record affected Call SIDs, users, timestamps, Twilio Debugger events, and Frappe logs.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Token request says disabled | Enable Settings only during an approved window |
| Token request says credentials missing | Account SID, API Key SID, API Key Secret, and TwiML Application SID |
| Sync refuses | CRM Twilio must be disabled; user needs System Manager |
| Caller ID unavailable | Normalize to E.164 and add to Settings Caller IDs |
| Webhook URL rejected | Use public HTTPS; localhost, private IPs, and Desk/API suffixes are invalid |
| Signature errors | Exact public URL, proxy scheme/host, query, HTTP method, and Auth Token |
| No inbound browser call | Mapping, Twilio Agent role, Accept Calls, availability, hours, registration, and DID mapping |
| Calls remain stale | Scheduler, workers, Redis, callbacks, and CDR logs |
| Recording inaccessible | Completion status, user permission, credentials, and proxy authorization |
| missing_numbers returned | Number ownership in the configured account and E.164 formatting |

## Optional protected site-config keys

The app can read these through protected Frappe site configuration:

~~~text
twilio_account_sid
twilio_auth_token
twilio_api_key_sid
twilio_api_key_secret
twilio_twiml_application_sid
twilio_default_country_code
twilio_default_caller_id
twilio_webhook_base_url
twilio_openai_api_key
openai_api_key
~~~

Prefer Twilio Settings Password fields for interactive setup. Never commit real values or pass secrets on a shared command line where shell history or process logs may capture them.
