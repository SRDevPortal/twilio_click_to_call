# Twilio Click-to-Call Implementation Plan

## Document control

| Item | Value |
| --- | --- |
| Target bench | /home/srdev/eternity-bench |
| Target site | eternity.localhost |
| Frappe app | twilio_click_to_call |
| Installed version | 0.1.0 |
| Plan date | 2026-08-27 |
| Production owner | To be assigned |
| Twilio account owner | To be assigned |

## Objective

Deliver a standalone Frappe v15 click-to-call application backed by Twilio Programmable Voice. Agents must place and receive calls through one browser softphone, while signed Twilio callbacks remain authoritative for call state.

The app must not import from or write to vobiz_click_to_call or vobiz_ai. The vobiz_click_to_call site app has been uninstalled after a backup; its source directory is retained for controlled recovery. Frappe CRM's built-in Twilio integration must remain disabled while this app is active.

## Current baseline

Completed on eternity.localhost:

- [x] App installed independently beside both Vobiz apps.
- [x] Python package installed with twilio 8.5.0.
- [x] Twilio DocTypes synchronized, assets built, and migration completed.
- [x] Scheduler hooks registered for stale calls, CDR sync, inbound backfill, and attendance cleanup.
- [x] Current server test suite passes: 128 tests.
- [x] Twilio Settings, recording, transcription, and AI disposition are disabled by default.
- [x] CRM Twilio Settings is disabled.
- [x] vobiz_click_to_call was backed up and uninstalled from the site; its source directory remains available.
- [x] vobiz_ai was backed up, uninstalled, and archived; WA Chat Hub's optional Vobiz patient-routing branch is no longer active.

Implemented surfaces include Twilio Settings, User Mapping, Incoming Mapping, Blocked Number, Agent Attendance Log, Call Log, Error Log, Voice SDK tokens, outbound TwiML, inbound routing, signed callbacks, recording proxying, CDR recovery, Agent Console, analytics, dispositions, and click-to-call controls.

## Production-readiness gaps

These gaps block production cutover even though the app is installed:

| Requirement | Current state | Required change | Exit evidence |
| --- | --- | --- | --- |
| Explicit registration | softphone.js registers after page load | Add a visible Go Online action that requests microphone permission, obtains a token, and registers | Browser test proves no registration before the gesture |
| One Device per user | No BroadcastChannel or local-storage lease is present | Add cross-tab ownership, takeover, unload cleanup, and stale-lock recovery | A two-tab test proves only one Device registers |
| Private identity | identity_for_user sanitizes the Frappe user string | Use a stable alphanumeric hash that cannot expose an email | Unit tests cover stability, uniqueness, and privacy |
| Presence recovery | Token refresh exists; stale heartbeat and registration-loss behavior needs completion | Add server heartbeat, TTL detection, offline transitions, and reconnect UX | Network-loss tests mark the agent unavailable |
| Provisioning safety | Sync Twilio Configuration writes immediately | Add preview, explicit apply, ownership checks, audit, and rollback | Preview makes no writes; apply and rollback tests pass |
| API key lifecycle | Sync does not create an API key | Implement owned key creation/rotation or retain an approved manual policy | Approved operating procedure |
| Provisioning audit | Twilio Provisioning Change is absent | Add resource SID, operation, previous/desired values, result, actor, and time | Apply and rollback create immutable rows |
| Browser automation | Current suite is server-side | Add mocked Device tests for registration, refresh, calls, controls, reconnect, tabs, and disposition | Browser CI suite passes |
| Live validation | Current tests are mocked | Use a controlled live number in staging | Signed staging acceptance report |

## Phase 1 - Interfaces and safety

- [ ] Inventory authenticated APIs, guest endpoints, DocTypes, custom fields, realtime events, jobs, and assets.
- [ ] Add a test that fails if Twilio code imports Vobiz modules or writes to Vobiz data.
- [ ] Confirm outbound preparation enforces login, document access, allowed DocType, number normalization, DND, limits, mapping, caller ID, and availability.
- [ ] Confirm guest endpoints allow only intended methods and validate X-Twilio-Signature against the exact external URL.
- [ ] Approve recording consent, retention, and regional telephony requirements.

Exit: the interface and security inventory is reviewed with no Vobiz dependency or write path.

## Phase 2 - Browser Device and presence

- [ ] Make frappe.twilio_softphone the only Device owner.
- [ ] Require Go Online before microphone access or device.register().
- [ ] Replace the current identity with a deterministic hashed identity.
- [ ] Refresh on tokenWillExpire and recover from transient failures.
- [ ] Add a BroadcastChannel lease with local-storage fallback.
- [ ] Add heartbeat, expiry, logout cleanup, and offline transitions.
- [ ] Keep mute, accept, reject, cancel, hangup, timer, log navigation, and disposition state consistent.

Exit: tests pass for denied permission, duplicate tabs, token expiry, network loss, reconnect, and logout.

## Phase 3 - Outbound hardening

- [ ] Preserve agent-first flow: authenticated preparation, one-use callback token, browser Device.connect, then Dial Number.
- [ ] Store browser parent Call SID and PSTN child Call SID separately.
- [ ] Treat signed callbacks as authoritative and tolerate retries and out-of-order events.
- [ ] Verify busy, no-answer, failed, canceled, rejected, connected, and completed transitions.
- [ ] Verify DND, safety limits, caller-ID ownership, and stale-token rejection.

Exit: callback permutations pass and controlled calls match Twilio records.

## Phase 4 - Inbound hardening

- [ ] Validate account SID, signature, and called DID.
- [ ] Route known callers through current lead/patient ownership and mapping rules.
- [ ] Route browser users with Dial Client and try fallbacks deterministically.
- [ ] Verify unknown-caller lead creation and mapping defaults.
- [ ] Use final mobile or AI fallback only when explicitly enabled.
- [ ] Release availability after reject, offline, busy, timeout, and network loss.

Exit: acceptance passes for known/unknown callers, accept/reject, fallback, and no-agent cases.

## Phase 5 - Recording, transcription, and AI

- [ ] Keep recording opt-in and use dual-channel recording where supported.
- [ ] Proxy authorized media without exposing Twilio credentials or raw media URLs.
- [ ] Make recording and transcription work idempotent with safe retries.
- [ ] Require manual review below the AI confidence threshold.
- [ ] Approve consent, retention, deletion, and access before enabling.

Exit: authorized playback and one-time transcription pass; unauthorized playback fails.

## Phase 6 - Safe provisioning

- [ ] Add a read-only preview of TwiML Application and number changes.
- [ ] Require explicit System Manager confirmation before apply.
- [ ] Record previous values before every Twilio mutation.
- [ ] Add rollback for app-owned resources and selected number webhooks.
- [ ] Never provision from settings save or a scheduler event.
- [ ] Define API key ownership and rotation; never re-display its secret.

Exit: preview, apply, repeat apply, partial failure, and rollback tests pass.

## Phase 7 - Staging and rollout

- [ ] Configure a controlled number and stable public HTTPS hostname.
- [ ] Follow the [setup and configuration guide](twilio_click_to_call_setup_and_configuration.md).
- [ ] Test outbound connected, busy, no-answer, and cancel.
- [ ] Test inbound accept, reject, timeout, and fallback.
- [ ] Test two tabs, microphone denial, refresh, network loss, token refresh, and worker restart.
- [ ] Test recording/transcription only after approval.
- [ ] Compare Call SIDs, duration, cost, status, and recording metadata with Frappe logs.
- [ ] Obtain business, security, and operations sign-off.
- [ ] Schedule a monitored cutover and assign a rollback owner.

Exit: acceptance evidence, monitoring owner, rollback owner, and cutover approval are recorded.

## Production cutover

1. Verify a recent backup and export current Vobiz and Twilio webhook values.
2. Confirm web, Socket.IO, workers, scheduler, Redis cache, and Redis queue are healthy.
3. Keep Twilio Settings disabled while entering and validating configuration.
4. Confirm CRM Twilio Settings is disabled.
5. Validate User Mappings and Incoming Mappings.
6. Review provisioning preview and every affected resource SID.
7. Apply provisioning and make one controlled outbound and inbound call.
8. Confirm vobiz_click_to_call remains uninstalled and retain its pre-uninstall backup.
9. Enable Twilio Settings and bring pilot agents online.
10. Expand only after the pilot monitoring window passes.

## Rollback

Triggers include elevated failure rate, missing callbacks, duplicate Devices, wrong routing, inaccessible fallback, or inconsistent Call Log state.

1. Disable Twilio Settings and mark Twilio users offline.
2. Restore saved TwiML Application and number webhook values. Until automated rollback exists, use the pre-cutover export.
3. Reinstall Vobiz from the retained source and restore its backed-up data only with business approval.
4. Preserve Twilio logs, Vobiz records, and audit evidence.
5. Capture Call SIDs, timestamps, users, Twilio Debugger events, and Frappe logs.

## Final acceptance criteria

- One browser Device owner exists per user.
- Invalid signatures and unexpected account or DID values are rejected.
- Parent and child Call SIDs correlate and retries are idempotent.
- Supported browsers complete inbound and outbound journeys.
- DND, permissions, limits, hours, availability, and fallbacks are enforced server-side.
- Recording and transcription stay off without documented approval.
- Provisioning is previewable, auditable, repeatable, and reversible.
- Twilio activity never writes to Vobiz tables or fields.
- Monitoring, ownership, backup, and rollback evidence exists before broad enablement.
