# PI test and activation review — 29 September 2026

**PI is not ready for unattended live service conversations yet. A WhatsApp access
token alone will not activate it.** The existing regression tests pass, but targeted
audit tests reproduce functional gaps, including a service-price guard bypass.
The deployed API also fails its dependency-readiness check.

This review tested the current local code and checked Workzap's live configuration.
No customer messages were sent, no live settings were changed, and no fixes were
deployed. AI and Meta delivery in the automated tests are mocked.

## Current live state

| Check | Observed result |
| --- | --- |
| PI overview, settings, WhatsApp, knowledge sources/documents, integration connections | Six endpoints returned HTTP 200 |
| WhatsApp connection | None; no WhatsApp integration connection exists either |
| Auto-replies | Off |
| AI providers | Overview reports all three unconfigured; a routing preview independently returned provider-unavailable human handoff |
| Reminders | Off; delay seven days; no template mappings |
| Audio, images, video | Enabled in PI settings; current configured media cap is 10 MB |
| Knowledge | One active source, two ready documents, three chunks; POS, ERP and onboarding searches return results |
| API liveness | HTTP 200 |
| API dependency readiness | HTTP 503 / `DEPENDENCY_UNAVAILABLE` on three checks |
| Database schema | Live revision `3ad535597720`; checked PI tables have all expected columns and integration workflow tables exist |

The readiness endpoint checks PostgreSQL and, in ARQ mode, Redis. Its response does
not identify the failed dependency. Successful scoped APIs and a direct read-only
schema check confirm database access worked during this review; they do not prove
Redis or a worker is healthy. Deployment logs and a worker health check are still
needed. No schema migration is currently missing for the checked PI tables.

Provider dashboard status has a separate bug described below. Therefore, its
“unconfigured” label alone does not establish that the deployed API keys are absent.
The current live routing preview nevertheless failed to obtain an AI decision.

## Reproduced gaps

1. **Service price protection is incomplete — fix before enabling unattended replies.**
   The guard rejects digits, currency symbols and a few English currency words,
   but accepts written-out Roman Urdu and Urdu prices. Scripted model replies
   `Is website ki qeemat pachaas hazaar rupay hai.` and
   `اس ویب سائٹ کی قیمت پچاس ہزار روپے ہے۔` both reached mocked WhatsApp delivery.
   These are failure-injection tests: they prove the final guard cannot stop those
   responses if a model produces them, not that a real model has already quoted them.
   Source: `apps/api/app/modules/pi/service_conversation.py`, `validate_service_reply`.

2. **Inbox assignment and unread filters are ignored.**
   `unread=true`, `assignment=mine` and `assignment=unassigned` each returned both
   seeded conversations when exactly one matched. The UI sends these parameters,
   but the backend does not apply them.
   Sources: `apps/api/app/modules/pi/routes.py`, `PiService.search` in `service.py`.

3. **Phone and message search do not work as advertised.**
   Searching a known phone number or stored message returned zero results; the
   backend searches customer names only, despite the UI promising all three.
   Source: `apps/api/app/modules/pi/service.py`, `PiService.search`.

4. **The inbox cannot load older history or additional conversation pages.**
   A seeded workspace returned 25 of 31 conversations and 100 of 107 messages in
   the initial requests. Explicit API pagination retrieves the remainder, but
   the current inbox has no next-page or older-message controls.
   Sources: `apps/web/src/features/pi/workspace/inbox-page.tsx`,
   `conversation-thread.tsx`, and `apps/web/src/features/pi/live.ts`.

5. **Agent publication can partially succeed while reporting that nothing changed.**
   The UI publishes the active version before updating tools in separate requests.
   A deliberately invalid subsequent tool request failed while the new version
   remained active. The UI error says “Nothing was changed.” This demonstrates the
   transaction boundary; valid tool updates were not observed failing spontaneously.
   Source: `apps/web/src/features/pi/config/agents/agent-new-page.tsx`.

6. **Provider readiness display ignores default model aliases.**
   With a test key and enabled default aliases, the model registry resolves a model
   but the overview still reports the provider unconfigured because the explicit
   model mapping is empty. No external provider call is involved in this probe.
   Sources: `apps/api/app/modules/pi/read_routes.py`, `apps/api/app/ai/registry.py`.

Other current limits: company summaries/notifications appear inside the application;
they are not sent to the owner's WhatsApp or email. Media and provider-failure notices
can fall back to English. Video currently requires the Gemini video path. Uploaded
audio/image/video interpretation and broad language fluency still require real-provider
acceptance tests. The agent “Test run” screen previews routing, not a complete customer
conversation or WhatsApp delivery.

## Verification performed

| Test | Result |
| --- | --- |
| Fresh disposable PostgreSQL migration to repository head | Passed |
| Current backend selection: `pytest -k 'pi or media or gateway'` | **175 passed, 1 skipped, 261 deselected** |
| Additional audit probes | **8 failed, 2 passed**; failures reproduce filters, search, two written-price cases and provider-status bug; passing probes confirm pagination and partial-publication behavior |
| Fresh isolated Next.js production build, including TypeScript | Passed |
| Current PI Playwright tests | **3 passed**: permissions, mobile knowledge layout, service/reminder settings |
| Live knowledge queries | Three passed |
| Live read-only schema inspection | Passed |

The skipped test requires an actual Redis/ARQ worker (`RUN_INTEGRATION=1`). No real
worker job, live AI/media quality, Meta token validity, webhook delivery or outbound
WhatsApp delivery was verified. The regression tests exercise webhook deduplication,
service briefs/leads, numeric-price rejection, language/media plumbing, human takeover,
reminder timing/consent/cancellation and the integration-to-PI bridge using provider doubles.

Audit artifacts are in `.cache/pi-review-20260929/` (`backend.xml`, `probes.xml`,
`test_service_readiness_probes.py`). The existing inbox probes are in
`.cache/pi-review-20260928/test_review_probes.py`. Live results are in
`.cache/pi-readiness-20260929.json` and `.cache/pi-runtime-health-20260929.json`.
These files contain test evidence; connection secrets were not printed or added here.

## What is needed in addition to the WhatsApp token

1. Repair the live dependency-readiness failure and verify the deployed Redis/ARQ
   worker, including its scheduled reminder jobs.
2. Configure and verify a usable AI provider and model aliases for the API and worker;
   include the required media capabilities for enabled media types.
3. In WhatsApp integration settings, supply the Phone Number ID, access token,
   webhook verification token and app secret (or the configured server app secret).
   Save/test the connection and select **Use for PI messaging**. Complete Meta's
   callback verification and subscribe to message events.
4. Fix the service-price guard issue before unattended customer use. Address the
   reproduced inbox/configuration issues so staff can operate it reliably.
5. For weekly reminders, add the WhatsApp Business Account ID and approved template
   mappings for each customer language. This implementation accepts text templates
   without variables/buttons/media headers and requires recorded reminder consent.
   Approved templates are required outside WhatsApp's customer-service window; see
   the [official WhatsApp messaging policy](https://whatsappbusiness.com/policy/).
6. Run a controlled real-number acceptance test: inbound message, service discovery
   without pricing, summary visible to staff, language switching, media, human
   takeover, opt-out and reminder delivery. Enable auto-replies/reminders only as
   part of that controlled activation after the blockers are resolved.

Real tokens should be entered in the application's secure connection form.
