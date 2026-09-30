# Pi Agent Beta for Owner OS

This assistant is independent of the WhatsApp Pi product. Open **Pi Agent Beta** in the sidebar (`/workspace-agent`) or the floating button on any authenticated Owner OS page. Standalone Pi app routes, WhatsApp handling, operator Agenta, customer agents, subscription metering and their workflow logic are not changed by this feature.

## What it can do

| Capability | Behavior |
| --- | --- |
| Workspace identity | Uses the verified session's user, tenant, environment, roles and current permissions. Member names and owner/admin roles are available only with `admin.members.read`. |
| Live record lookup | Searches employees, customers, catalog, sales, quotes, orders, invoices, expenses, stock, members and tasks when their read permission is held. Results include source pages, exact matching counts and bounded pages. |
| Summaries | Summarizes authorized workspace data or an uploaded document. Samples are identified; the assistant must not invent complete financial totals from samples. |
| Multilingual chat | The configured AI gateway answers in the user's language, including Roman Urdu. Basic tools and CSV import also work without an AI provider. |
| Specialist agents | The coordinator can delegate to separate HR, CRM, finance and operations model runs. Each specialist has a narrower set of tools and the original user's scope. There are at most two specialist runs per chat request. |
| Work management | Create tasks, choose specialist/priority/due date, assign permitted members, update details/status, and mark work complete. These are tracked workspace tasks, not a promise of an unattended worker executing arbitrary work. |
| Employee/customer changes | Prepare creates and updates through the existing HR and customer business services. Mutations require a reviewable draft followed by explicit confirmation. |
| Employee import | CSV or AI-extracted TXT/MD/DOCX/text-PDF, up to 100 records. A 10-person **fictional example** is at `apps/web/public/templates/agent-employees-10.csv`; replace all sample information before real use. |
| Page navigation | Reads authorized pages through structured server tools and can open the corresponding internal page. No arbitrary browser, URL fetch, shell or SQL tool is exposed. |

The assistant does not create login credentials, change roles, reveal passwords or provider keys, send external messages, or alter WhatsApp Pi configuration. Employee creation means an HR record; account creation remains on the Members page. Other unsupported mutations should be handled on the appropriate authorized page or tracked as tasks.

## Permission and transaction rules

- Every endpoint requires an authenticated Owner OS session and matching `X-Workspace-Tenant` / `X-Workspace-Environment` headers. Scope never comes from a prompt, uploaded file or action payload.
- Domain tools retain their existing business permissions. Employee/customer mutations also require read permission to review the data. Compensation requires `hr.sensitive`.
- `tasks.read` permits reading tasks created by or assigned to the current user; `tasks.write` permits managing those tasks. `tasks.manage` permits all workspace tasks and assignment to other active members.
- Built-in roles receive task read/write access, except the viewer receives read only. Owner, administrator and manager receive task management. Custom roles are not expanded by the migration; administrators explicitly grant these new permissions.
- Drafts belong to one user and one tenant/environment. Even an owner cannot approve another user's draft. Drafts expire after 30 minutes. Confirmation rechecks authorization and references, locks the draft, rejects changed update targets, and commits the whole batch atomically. Repeating an applied confirmation returns the saved result.
- Employee imports check duplicate emails both at preview and confirmation. Imports made through this assistant serialize their duplicate check and insert within the same workspace. Existing HR UI operations do not acquire this assistant-specific advisory lock; this is not a new database-wide employee-email uniqueness constraint.
- Proposed/applied/cancelled operations are audited without storing document bodies or employee field values in audit details.
- Chat is kept in browser memory, cleared on user/workspace/permission changes and refresh. Pending drafts are durable and recoverable in the Drafts tab. There is no promise of permanent conversation history.
- No credentials tables, encrypted HR personal details or integration secret configuration are exposed to the tools. Uploaded text is treated as data; document summarization has no action tools. Common pasted secret patterns are redacted before AI calls, but users should not paste credentials.

## Import format

Required CSV headers: `full_name,job_title,employment_type,hire_date`.

Optional headers: `email,phone,department_id,manager_id,salary,salary_currency`.

Employment type is `full_time`, `part_time`, `contract`, or `intern`. Dates use `YYYY-MM-DD`. Department and manager references must already exist in the authorized scope. Files are read in memory, not stored in a public directory. Limits: 2 MB, 24,000 extracted characters, at most 30 PDF pages. Scanned PDFs require OCR before upload. DOCX and PDF extraction does not fetch linked resources.

## Running the feature

1. Apply database migration `0013_workspace_agent` using the project's usual migration process (`cd apps/api` then `alembic upgrade head`). This creates `workspace_agent_actions`, `workspace_tasks`, and grants task permissions to existing built-in roles.
2. Restart the API and rebuild/restart Owner OS web with its usual live configuration. No new package dependencies or WhatsApp token are required for this assistant.
3. For natural-language planning, specialist delegation, document summaries and non-CSV extraction, configure an existing AI gateway provider using the platform's normal server configuration. Never enter provider keys in chat. The assistant uses the `fast` alias and existing budgets/fallbacks. AI usage is recorded with `workspace.*` purposes without incrementing the separate Pi subscription meter.
4. Refresh the signed-in session after migration to pick up task permissions. Verify with an owner and a restricted employee account.

Demo mode clearly explains that no real business actions run. It provides the CSV example but does not simulate successful mutations.

## Verification

Tests cover real PostgreSQL transactions, ten-row CSV preview/confirmation, idempotent and concurrent confirmation, role revocation, sensitive HR fields, private drafts, cross-tenant isolation, stale workspace headers, CSRF, task assignment/ownership, expired/cancelled drafts, changed-record conflicts, hostile model tool requests, separate specialist dispatch, and document instructions that cannot trigger actions. Browser tests cover employee approval, CSV cancellation, viewer restrictions and the mobile drawer.

Testing uses an isolated local `*_test` database and an isolated Next build. No migration, sample employee import, AI request, WhatsApp message or deployment has been performed against the owner's live workspace as part of implementation verification.
