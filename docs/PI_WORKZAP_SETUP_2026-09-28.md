# Workzap PI setup and verification — 28 September 2026

PI is installed and enabled in **Workzap / Production** on the
[live application](https://unified-business-platform-sooty.vercel.app/pi).
Knowledge ingestion, retrieval, routing previews and the PI dashboard work.
Live AI replies and WhatsApp delivery remain pending: no WhatsApp connection exists,
and the deployed overview reports OpenAI, Gemini and Groq as unconfigured.
Auto-replies and follow-up reminders remain paused.

## Completed live setup

- Signed in with the supplied Techmaster account and selected Workzap Production.
- Set timezone to `Asia/Karachi`, service enquiry mode, automatic customer-language
  matching, a friendly tone and a WorkZap greeting.
- Configured a 1,500-character reply limit, low generation temperature, one
  clarification at a time and retrieval of up to five passages with source citations.
- Published WorkZap-specific router, requirement, support and handoff guidance.
  Enquiries collect requirements without inventing prices or delivery commitments.
  Requests for a person or founder route to the owner/support team; no founder
  identity was assumed.
- Added one active company-information source and two ready documents containing
  three searchable passages, with zero failed documents.
  The product/onboarding summary references the public
  [WorkZap website](https://workzap.ai), accessed on 28 September 2026.
  A separate intake glossary makes POS and ERP individually searchable.
  This is a curated summary, not a full-site crawl or automatic website sync.
- Confirmed successful searches for `retail`, `POS`, `ERP`, `onboarding`,
  `finance` and `subscription`.
- Confirmed routing previews for a Roman Urdu service enquiry, a human request
  and provider-unavailable fallback. These previews create no customer messages.
- Checked the existing healthy Resend integration; no changes were needed.

## Live error repaired

The dashboard and WhatsApp APIs initially returned HTTP 500 because the deployed
database was still at `0006_pi_service_conversations`, while the application expected
the integration workflow schema.

Applied the existing repository migration `3ad535597720` after exercising the
upgrade on a fresh local database. It adds `integration_operations`,
`integration_workflows` and the nullable, scoped WhatsApp integration connection
reference. This updates the shared application schema. Before applying it,
read-only checks confirmed the expected database/workspace and that the WhatsApp
connection table was empty; schema metadata and the row count were recorded.
Existing business records were not deleted or rewritten.

After migration, all seven checked APIs returned HTTP 200: PI overview, WhatsApp,
settings, knowledge sources, knowledge documents, integration connections and
integration health. The overview, WhatsApp connection/status and knowledge screens
were rechecked in the live browser and rendered their expected state.

## Browser findings and local fixes

Audited 37 PI routes at 1,440px desktop and 390px mobile widths, covering overview,
inbox, handoffs, agents, WhatsApp, knowledge, analytics and settings. The initial
API errors above were fixed and the affected screens rechecked.

Two mobile overflow issues remain on the currently deployed frontend. Local fixes
are ready, but have **not been deployed**:

- Knowledge overview: constrain the single-column grid so long document titles
  truncate within the viewport.
- Permissions: show the current member's effective access and link to Roles &
  Permissions. The previous switches and Save button implied editable per-role
  settings even though the API rejects those writes. The access table now scrolls
  within a labelled, keyboard-focusable region on small screens.

## Verification

| Check | Result |
| --- | --- |
| Fresh-database migration plus PI management, knowledge jobs, integration API and API surface checks | 36 passed |
| Broader backend selection: `pytest -k 'pi or media or gateway'`, fresh local database | 175 passed, 1 skipped, 261 deselected |
| Focused Playwright checks: permissions, long knowledge titles on mobile, service/reminder settings | 3 passed |
| TypeScript, changed-file ESLint and Prettier | Passed |
| Isolated frontend production build | Passed |
| Live knowledge searches | 6 passed |
| Post-migration live API checks | 7 passed |

The skipped backend test requires Redis/ARQ. An earlier run against a reused local
database encountered two outbox-fixture failures; both passed in the fresh-database
runs. The automated runs use local/demo data and provider test doubles where
applicable. They do not establish live model fluency, media quality or actual
WhatsApp delivery. The 37-route audit checks rendering/navigation and responsive
layout; it is not an exhaustive test of every possible customer workflow.

## Remaining activation steps

1. In [WhatsApp integration settings](https://unified-business-platform-sooty.vercel.app/settings/integrations/whatsapp_meta),
   create a Production connection with the real Phone Number ID, access token,
   webhook verify token and app secret (or configured server app secret).
   Add the WhatsApp Business Account ID for template/reminder use. Enter secrets
   directly in the secure form.
2. Save and test the connection, then select **Use for PI messaging**. Complete
   Meta callback verification and message-event subscription using the callback
   details exposed by the application.
3. Configure a supported AI provider key and valid model aliases in the API/worker
   deployment. Verify the provider status becomes configured and the worker/Redis
   pipeline is running.
4. Complete controlled acceptance checks with the business owner's test number:
   English/Roman Urdu enquiries, website-grounded answers, unknown questions,
   founder/human handoff, and any enabled audio/image/video features. No live
   customer messages were sent during this setup.
5. Enable auto-replies after those checks. Enable reminders only after consent
   handling and approved language-specific Meta templates are configured and tested.

The account password, connection secrets and browser session state are intentionally
excluded from this report.
