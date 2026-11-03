# Controlled execution (Q-8) and the evidence gate (P-6, Q-9): design

Status: DESIGN PROPOSAL for owner review, 2026-10-31. Docs only. Written against `origin/main` b25e04c.
Nothing here is implemented, tested or run; no code, migration, model call or spend. Task ids: Q-8 (plan
section 9, `pi-fast-track-plan.md:228`), P-6 / FT-X1 (plan section 8, `:172`), Q-9 (`:229`).

Conventions. **EXISTS** = read in code at `path:line` (paths under `apps/api/app/modules/` unless stated).
**PROPOSED** = this document's suggestion, needs the owner's yes. **UNKNOWN** = not read or not verified;
section 14 lists all of them. Spec citations are line numbers in `docs/pi-saas/spec-text/*.txt` (the text
extracts; tabs are in the source). Two earlier documents already cover parts of this ground and are not
repeated: `pi-p6-evidence-claims-design.md` (claim taxonomy C1 to C12, gate, outcome sequence; "P-6 design"
below) and `pi-solution-blueprint-design.md` section 6.3 (task hand-off from an approved blueprint;
"blueprint design" below). This document adds the part neither has: the execution workflow itself, and ties
the three together.

## 0. Summary and the one-line rule

Q-8 is "approved actions executed and verified, progress reported" with the boundary: **no autonomous
external actions, payments, bookings, messages, production changes or irreversible actions; an action record
exists before any "done" claim; every action has an approval and a rollback** (`pi-fast-track-plan.md:228`).

Proposal in one paragraph. Q-8 is a **staff-run task ledger, not an executor**. A task is created by a
person from an approved, paid, kicked-off blueprint item; a second person approves that exact scope; a human
does the work (outside pi); a human records evidence against a written acceptance check; only then does a
record exist that lets pi say a step is done, and P-6's gate enforces that pi says nothing stronger than the
record. pi never runs a task, never moves a task's state, and never has a tool that touches an external
system. Where later automation is wanted (section 11), it is a separate decision with its own approval class,
not part of this design.

Recommended first cut: **no new table** (reuse `pi_tasks` for the work item, `audit_events` for the trail),
then add a small additive table only if the owner wants per-task approval and evidence fields that `pi_tasks`
cannot carry (section 7, options A and B).

## 1. What exists today (read, so nothing is built twice)

| Piece | Where | What it gives Q-8 | Limit |
|---|---|---|---|
| Reviewer approval of a document and quote | `brain_docs.approve` (`brain_docs.py:992-1041`): refuses while `blockers` is non-empty, sets `approved_by`, `approved_at`, renders and keeps the PDF so "what was approved is exactly what is sent" | the only existing "approval of an exact scope" | edit clears approval (`brain_docs.py:804-815` sets `status="in_review"`, `approved_by=None`); no snapshot hash; approves a document, not a task |
| Who may approve | `approve_document` requires `quotes.write` (`brain_doc_routes.py:222-224`), the same key as edit, revise, send, outcome (`:167-170`, `:198-203`, `:241-245`, `:261-265`) | a permission gate | a distinct key `quotes.approve` exists in the catalogue (`access/permissions.py:28`) but the document routes do not use it; one user can edit and approve (also BL-08 in `pi-capability-backlog.md`, not verified here) |
| Spec statement of the gate | R-DOC-00: no document or quote reaches a person without a Workzap reviewer's approval (`pi-brain-v3.txt:3098`) | the rule Q-8 must not weaken | "can be relaxed only by an explicit Workzap owner decision": Q-8 proposes no relaxation |
| Owner decision gates | `decisions.py:731` `_prepare` (offer yes), `:763` `_review` (quote approval); R-DEC-01/02 two confirmations and `can_approve` contact (`pi-brain-v3.txt:3262-3269`); R-DEC-05 cancel after payment is a human matter (`:3274-3280`) | the owner side of "approval for that exact scope" | covers the quote, not individual build tasks |
| Payment truth | `brain_payments.confirm` (`brain_payments.py:88-140`): `confirmed_by`, `confirmed_at`, moves S9/S10 to S11 | evidence that work may start; R-PAY-05 | one record per quote (unique, `brain_docs_models.py:75-78`) |
| Flow | `flow.py:111-117`: `S9 -> S10 -> S11 -> S12 -> S13_IN_BUILD`; `S13` has no legal move out (`:117`); `kickoff_booked` S11 to S12 (`brain_payments.py:143-155`); `kickoff_done` S12 to S13 (`flow.py:254-280`, called from `brain_followups.py:481`); S13 prompt: "Workzap is building. Note new problems as new problems; route project questions to the project owner." (`flow.py:187-188`) | where execution lives: after S12, inside S13 | S13 is terminal; no state for "task running" |
| Existing task record | `PiTask` (`pi_saas/models.py:556-580`): title, description, customer, conversation, assignee, status `open/in_progress/blocked/done/cancelled`, priority, `due_at`, `customer_visible_status`, idempotency key; permissions `pi.work.manage` (`access/permissions.py:60`) | a work item, tenant and environment scoped | no approval, scope snapshot, dependency, evidence, acceptance or rollback fields; "done" is a plain status any task writer can set |
| Staff request desk | `PiStaffRequest` (`pi_saas/models.py:442-470`), raised by `raise_decision_request` (`service_conversation.py:3475-3499`) | an existing hand-off from pi to staff | the raise runs in a savepoint and `except DBAPIError` only logs `pi_decision_request_skipped` (`:3499`): the request can be missing while the fixed "I've asked Workzap" line is chosen (P-6 design section 1, conflict 5) |
| Order work steps | `deal_routes.move_work` (`pi_saas/deal_routes.py:150-160`) requires `orders.write`, `advance_work` sets order status; `deals.ORDER_UPDATES = {"processing": "started", "shipped": "shipped", "delivered": "delivered"}` (`pi_saas/deals.py:195`) and a customer update goes out | an existing staff action that already writes a record before pi says "delivered" | coarse: one status per order, not per task |
| Audit trail | `audit.service.record` (`audit/service.py:35`) appends an `AuditEvent` in the caller's transaction with actor, entity, outcome, details; the approve route calls it (`brain_doc_routes.py:227-235`) | the append-only trail | denied actions are not written (B1 in `pi-capability-map.md`, `core/exceptions.py:82-85` per that map; not re-read here) |
| Per-reply audit | `PiReplyAudit` (`learning_models.py:149-165`): one row per reply, identifiers only (prompt version, packs, lessons, examples, arms, `linter` JSON), unique per message; stamped by `learning_audit.stamp_safely` after the reply is saved (module header `learning_audit.py:1-13`) | the place to record which claim evidence a reply relied on (section 8) | stores no text; stamped after the send path, so it can explain a reply but not block it |
| Change log with rollback | `PiLearningChange` (`learning_models.py:78-92`): `before`, `after`, `evidence`, `status`, `decided_by`; `/pi-rollback` (`pi-brain-v3.txt:40386`) | an in-repo pattern for "an action carries its own undo data" | for learning changes only |
| Box lifecycle | `PiBoxTransition` (`box_models.py:102-121`): append-only, `from_state`, `to_state`, `actor`, `actor_ref`, `decided_by` | an in-repo pattern for append-only transition rows | covers the Solution Box states, not tasks |
| Final-text check | `FINAL_CHECKS = {"R-PAY-02","R-PAY-03","R-DISC-03","R-BRAND-01"}` (`constitution.py:2341`), used at `service_conversation.py:6384-6391`: the last lint on the assembled reply, raising `CONSTITUTION_BREAK` | where P-6's gate runs | no claim rule in the set |
| Erase | `brain_erase.erase_customer` (`brain_erase.py:348`); keeps documents and payments (`:525-545`); `PiTask` rows are blanked, not deleted (`:261-262`); wording "text-only rows ... keep their rows" (`:556-563`) | the erase contract a new table must obey | no audit call found in this file (P-6 design section 7) |
| Blueprint design (on main) | `pi-solution-blueprint-design.md:248-256`: tasks come from the approved blueprint, after G-C and `S11`, one record per phase/module/automation: `{blueprint_id, version, item_id, approved_by, approved_at, rollback_ref, acceptance_ref, evidence_ref}`; progress is records plus P-6, not a flow move | the source of task items | the task table, executor and reporting UI are explicitly out of scope there |

Gaps this design closes: (1) nothing ties an approval to a *task's* exact scope; (2) nothing makes "done" a
recorded, evidenced state separate from "someone ticked a box"; (3) no record of how to undo an action;
(4) no rule about what pi may say while work is under way (only the S13 prompt line, `flow.py:187`).

## 2. Principles (each maps to an approved boundary)

1. **No autonomous external action.** pi has no execution tool. A task is done by a person, in the person's
   own systems, outside this codebase. Nothing in Q-8 calls an external API. (Boundary, plan `:228`.)
2. **Approval is for an exact scope, and a changed scope is a new approval.** The approved scope is stored as
   a snapshot with its hash (same idea as the snapshot hash proposed in the blueprint design section 6.1,
   step 5). Editing the scope clears the approval, exactly as `brain_docs.edit` does today
   (`brain_docs.py:804-815`).
3. **"Done" is never a model statement.** A task reaches `done` only through a staff action that writes an
   evidence row and passes the acceptance check; pi may repeat only what the record shows (P-6 gate,
   section 8).
4. **Every task has a rollback entry before it can start.** A task without one cannot be approved
   (section 5). An action that is irreversible by nature is not a task in this design (section 11, "never
   in scope").
5. **Learned or retrieved content is data below the rules.** Nothing learned can create, approve, start or
   complete a task (CLAUDE.md non-negotiable: learned content "can never override" the rules).
6. **Additive, scoped, erase-aware.** Any new storage is scoped by tenant and environment like every
   neighbour (`shared/models.py:36-68`), and joins the erase list in the same change.

## 3. The workflow of approved tasks

### 3.1 Task record (fields; storage in section 7)

PROPOSED. One task is one reviewable unit of work from an approved blueprint item (blueprint design section
6.3) or, until the blueprint exists, from the approved solution document's `components` and the quote's
`milestones` (EXISTS: `brain_docs.py:804-815` documents `components`, quote `time.milestones`; the per-phase
price check is `box_doc.phase_price_issues`, referenced at `brain_docs.py:948`; I did not read `box_doc.py`).

| Field | Meaning | Rule |
|---|---|---|
| `id`, tenant, environment, customer, conversation | scope | every query filters tenant and environment |
| `source` | `{document_id, version, item_ref}`: the approved item it comes from | document must be `approved` or `sent` and its quote's payment `confirmed` |
| `title`, `description` | what is to be done, written for staff, English | roles not third-party names; passes `problem_fields.clean`-style redaction (`problem_fields.py`, cited by the blueprint design section 7.3; not re-read here) |
| `owner_user_id` | the accountable person | a named staff user, never "pi" |
| `depends_on` | list of task ids | no cycles; a task cannot start while any dependency is not `done` |
| `scope_snapshot`, `scope_sha` | the exact text of what is approved to be done, and its hash | frozen at approval |
| `approval` | `{approved_by, approved_at, scope_sha}` | `approved_by` differs from `owner_user_id` and from the creator (decision D2, section 13) |
| `acceptance` | list of checks, each `{id, statement, verifier, kind}` where `kind` is `observable`, `document`, `customer_confirms` or `staff_confirms` | at least one; each names who verifies it |
| `rollback` | `{steps, reversible: true/false, owner}` | required; `reversible: false` blocks approval (section 11) |
| `status` | state machine below | |
| `execution` | append-only list of records (section 3.3) | |
| `evidence` | append-only list of `{acceptance_id, by, at, ref}` | `ref` points to an existing record (document, file, order status, message), not to free text alone |
| `customer_visible_status` | the one sentence pi may say | written by staff, not by a model; matches the existing `PiTask.customer_visible_status` field (`pi_saas/models.py:576`) |

### 3.2 States and who may move them

PROPOSED, 8 states. Every move is a staff action through an API route; none is reachable from a model tool.

```
draft -> proposed -> approved -> in_progress -> verifying -> done
                         \             \            \-> failed -> rolled_back
                          \             \-> blocked -> in_progress
                           \-> cancelled (from any non-terminal state)
```

| Move | Who | Preconditions (all checked in code) |
|---|---|---|
| `draft -> proposed` | creator (`pi.work.manage`) | source approved and sent; payment confirmed; acceptance and rollback present |
| `proposed -> approved` | approver, a different person (`quotes.approve` or a new `pi.work.approve`, D2) | `scope_sha` equals the current scope; every dependency exists; `rollback.reversible` is true; writes an `audit_events` row |
| any edit of scope | creator | sets status back to `proposed`, clears `approval` (mirrors `brain_docs.edit`) |
| `approved -> in_progress` | owner | all `depends_on` are `done`; records an execution entry `started` |
| `in_progress -> blocked` | owner | reason recorded; the dependants cannot start |
| `in_progress -> verifying` | owner | an execution entry of kind `performed` exists |
| `verifying -> done` | verifier, not the owner when the acceptance check says `staff_confirms` | every acceptance check has an evidence row whose verifier matches; for `customer_confirms` the evidence is the customer's own confirmation message (section 8.4) |
| `verifying -> failed` | owner or verifier | reason recorded |
| `failed -> rolled_back` | owner | a rollback execution entry exists and the rollback's own check passed (the rollback step has an acceptance check too) |
| `-> cancelled` | creator or approver | allowed only before `in_progress` or after `rolled_back`; a started task is rolled back, not cancelled |

### 3.3 Execution record

PROPOSED, append-only (the `PiBoxTransition` pattern, `box_models.py:102-121`): `{task_id, at, actor_user_id,
kind, detail, ref}` with `kind` in `started`, `performed`, `blocked`, `unblocked`, `evidence_added`,
`failed`, `rollback_started`, `rollback_done`, `cancelled`. Rows are never updated. This is what "an action
record exists before any done claim" means in the plan row: the claim "started" needs a `started` row, "done"
needs a `done` transition with evidence rows (section 8).

### 3.4 Dependencies

A task may start only when every `depends_on` task is `done`. A dependency on a task of another customer or
another tenant is refused at write time and by a two-tenant test. Cycles are refused at write time. The
blueprint's phase order is the default dependency order (blueprint design section 6.3); changing it is a
scope edit.

### 3.5 Acceptance check

A check is a statement a named verifier can judge from a record: an order status (`Order.status`, EXISTS
`pi_saas/deals.py:195`), a delivered document (`PiBrainDocument.status == "sent"`, `brain_docs.py:1192`),
a file, or a customer's confirming message. It is **not** a model's judgement. A model may *suggest* check
wording at proposal time (staff edit it); it can never mark a check as passed (principle 3, principle 5).

### 3.6 Rollback

Each task states how to undo it and who does it, and the rollback has its own acceptance check. A task whose
effect cannot be undone (money moved, a message sent to a third party, data deleted) is out of Q-8 by
construction (section 11). EXISTS as a pattern: `PiLearningChange` keeps `before` and `after` so a change can
be reverted (`learning_models.py:84-86`); Q-8 stores the *plan* to revert at approval time, since the actual
before-state belongs to the person's own systems.

## 4. No autonomous external action: how it is enforced

1. **No tool.** The pi tool set (`pi/tools/`, listing not read in detail here: UNKNOWN) gets no task tool.
   A test asserts that no module under `pi/` imports the task service's write functions (an import-graph
   check, scripted).
2. **Routes only, permission-gated.** Task writes are routes behind `require_pi(session, scope, <permission>)`
   (`service.py:56-69`), like `approve_document` (`brain_doc_routes.py:222-224`). System actors (the pi
   runtime) are refused on every task write: a scope with `actor_type == "system"` gets a 403 (PROPOSED;
   `WorkspaceScope.actor_type` is used at `audit/service.py:46`).
3. **No outbound message from a task.** A task transition never queues a message by itself. Customer updates
   use the existing fixed paths (`deal_routes.move_work` and `deals.ORDER_UPDATES`, `pi_saas/deals.py:195`)
   which are already staff-triggered; a progress message from a task is a staff action that queues a message
   through `brain_docs.queue_message` (`brain_docs.py:1228`) with an idempotency key, inside the 24-hour
   window rule (`brain_docs.py:1155-1160`).
4. **No payment, booking or production change.** Out of scope for the ledger (section 11). Bookings stay with
   `pi.bookings.manage`; payments stay with `brain_payments.confirm` (R-PAY-05).
5. **Kill switch.** PROPOSED setting `response_rules.brain.tasks` default off (same style as `box_offer`,
   referenced at `pi-solution-blueprint-design.md:292`; the setting code was not re-read here). Off means no
   task route is reachable and pi's claim gate treats every task claim as unevidenced.

## 5. Approval for exactly that scope

Reuse the three gates already in the blueprint design (G-A owner yes, G-B reviewer approves document and
quote, G-C owner approves quote with two confirmations; `pi-solution-blueprint-design.md:242-244`), and add
one:

| Gate | Who | Where | New in Q-8 |
|---|---|---|---|
| G-A, G-B, G-C | as above | `decisions.py:731`, `brain_docs.py:992`, `decisions.py:763` | none |
| Payment confirmed | Workzap finance | `brain_payments.confirm` (`brain_payments.py:88`) | tasks need it (R-PAY-05 is "payment received only after staff confirm") |
| **G-T task approval** | a staff user other than the creator and the owner | new route, `audit.record("pi.task_approved", entity_id=task.id, details={"scope_sha": ...})` (call shape `audit/service.py:35-50`) | approves the **scope snapshot** and its rollback and acceptance; any edit invalidates it |

Answer to "approval for that exact scope": the approver sees the frozen snapshot, hash, acceptance checks and
rollback on one screen and approves by hash; the server refuses an approval whose hash differs from the
current snapshot (compare-and-set), so an edit between viewing and approving cannot slip through. This is
stricter than the document approval today, which approves whatever the row holds at that moment
(`brain_docs.py:992-1041`).

**The owner's contact does not approve tasks.** The customer approves the quote (G-C); individual tasks are a
Workzap internal control. If the owner wants the customer to approve a specific risky task (for example a
change to the customer's live system), that is a `customer_confirms` acceptance or a separate decision (D5).

## 6. "Done" is never a model statement

Three layers, all in code (CLAUDE.md: rules are enforced in code, "not only in the prompt").

1. **Prompt layer (soft).** The S13 line (`flow.py:187-188`) gets an addition, PROPOSED: "Say only what the
   project record shows. Never say a task is done unless the record says so." This is guidance only.
2. **State layer.** There is no model-reachable path that writes `done`; section 4.
3. **Output layer (hard): the P-6 gate** (section 8) rewrites any claim in the final text that the evidence
   read does not support.

Wording allowed in S13 chat, PROPOSED, each tied to a record:

| pi may say | Needs |
|---|---|
| "The team has started {item}" | task `started` execution row |
| "{item} is done and checked: {acceptance}" | task `done`, evidence rows for every check |
| "{item} is waiting on {dependency}" | task `blocked` or an unmet dependency |
| "I can't see an update on {item} yet" | no record; the default |
| "You told me it is working" | the customer's own confirmation (P-6 design section 5 step 4) |

pi never says "will be finished by {date}": no date promise (`R-HONEST-01`, `constitution.py:1432-1456` per the
P-6 design; and a date is a promise the plan forbids).

## 7. Data model proposal (additive, tenant and environment scoped, erase-aware)

Principle: reuse before adding (P-4 / D3 "no new table" posture, plan section 8 conflict 3).

### 7.1 Option A (recommended for the first cut): extend `pi_tasks`

`PiTask` already holds the work item, assignee, status and a customer-visible line (`pi_saas/models.py:556-580`).
Add nullable columns only (one migration, backward compatible, old rows unchanged): `source` (JSONB),
`depends_on` (JSONB list), `scope_snapshot` (JSONB), `scope_sha` (String(64)), `approval` (JSONB),
`acceptance` (JSONB), `rollback` (JSONB). Extend the `status` CHECK (`pi_saas/models.py:563-565`) with
`proposed`, `approved`, `verifying`, `failed`, `rolled_back`. Execution and evidence live in **one** new
append-only table (7.2) because JSONB lists on a mutable row are not append-only.

Cost: `pi_tasks` is a general workspace table used by other features (tasks page, `pi.work.manage`); widening
its CHECK touches non-pi behaviour (UNKNOWN: its callers were not searched). Mitigation: Q-8 rows carry
`source` not null; the route layer refuses Q-8 transitions on rows without it.

### 7.2 Table `pi_task_events` (PROPOSED; append-only)

| Column | Type | Note |
|---|---|---|
| tenant_id, environment_id, id, created_at, updated_at | `WorkspaceRow` | scope (`shared/models.py:36-68`) |
| task_id | uuid, `scoped_fk` to `pi_tasks` | cannot cross tenant or environment |
| kind | text with CHECK | the list in section 3.3 |
| actor_user_id | uuid | never null; system actors are refused |
| detail | text, capped | redacted before store |
| ref | JSONB null | `{type, id}` of an existing record (document, order, file, message) |
| acceptance_id | text null | set on `evidence_added` |

Index on (tenant_id, environment_id, task_id). Rows are never updated (test: no `UPDATE` path in the module).
Migration number: assigned at implementation after `alembic heads`; on this tree the numbered files end at
`0054_payment_idempotency.py` and `0053_pi_problem_requirements.py` is present (`migrations/versions`), and the
plan reserves 0054 to lane U for a possible P-4 ledger (`pi-fast-track-plan.md:153` per the blueprint design
section 7.1), which now collides with the existing 0054 file. UNKNOWN: which number is free; check
`alembic heads` first (CLAUDE.md).

### 7.3 Option B: a dedicated `pi_execution_tasks` table

Same columns as 7.1 in a new table instead of widening `pi_tasks`. Cleaner isolation, no effect on other
task features; more code (own repository, erase step, UI) and a second notion of "task". Recommended only if
the owner wants Q-8 invisible to the general tasks page.

### 7.4 Option C: no migration (JSON on the conversation brief)

Not recommended: `service_brief` is a per-conversation JSON blob (`brain_docs.py:1215-1220` writes into it),
not append-only, and S13 chats can be replaced by a new conversation.

### 7.5 Erase, retention, isolation

- **Erase.** `brain_erase.erase_customer` already blanks `PiTask` text and keeps rows (`brain_erase.py:261-262`,
  `:556-563`). PROPOSED: on erase, blank `title`, `description`, `scope_snapshot`, `detail`; keep ids, kinds,
  timestamps, approver ids and `scope_sha` ("the rows stay so counts and audit trails add up", `:552`). Add
  `pi_task_events` to the erase list and to the "kept" counts, and add an erase test in the same change so the
  gap list does not grow (`pi-erase-gaps-g1-g14.md`). The retention decisions R1 to R6 decide whether
  approved scope text is a business record that must be kept (like documents, `brain_erase.py:556`): UNKNOWN,
  owner decision D6.
- **Redaction.** Every owner-derived string goes through the existing redact-then-protect-then-cut path
  before storing (blueprint design section 7.3, citing `problem_fields.py:52-60`); roles, never third-party
  names (CLAUDE.md).
- **Isolation.** A two-tenant, two-environment test with the same phone number in both workspaces (pattern
  `test_pi_isolation_core.py`, cited by the P-6 design section 7).
- **Order of deployment.** Same rule as other migrations: apply before code that writes; the loader tolerates
  a missing table behind the kill switch. The real database is migrated only when the user asks (CLAUDE.md).

## 8. The evidence-backed claims gate (P-6 / FT-X1) as it applies here

The P-6 design (`pi-p6-evidence-claims-design.md`) is the base: claim types C1 to C12, one read-only
`claim_evidence(session, conversation)` shared with P-4 (section 3 there), a last-pass rule `R-CLAIM-01` in
`FINAL_CHECKS` (`constitution.py:2341`) run at the final lint (`service_conversation.py:6384-6391`), fail-safe
order offer form, what is recorded, drop, regenerate once (section 4 there). Not repeated. What Q-8 adds:

### 8.1 New claim types, PROPOSED (extend the P-6 taxonomy)

| # | Claim | Evidence required (read-only) | If none |
|---|---|---|---|
| C13 | **Task started** ("the team has started X") | a `started` row in `pi_task_events` for the task named, status `in_progress` or later | "I can't see an update on X yet" |
| C14 | **Task done / delivered / completed** | task `done` and an `evidence_added` row for every acceptance check | say what the record shows (`in_progress`, `verifying`) |
| C15 | **Task approved / scope agreed** | `approval.approved_by` set and `scope_sha` equal to the current snapshot | "the team has not approved this step yet" |
| C16 | **Task rolled back / undone** | `rolled_back` and a `rollback_done` row | do not say it |
| C17 | **Progress figure** ("3 of 5 steps done") | computed from task rows, never from model text | drop the figure |

These sit with C3, C4, C5, C7 of the P-6 table: the gate already must accept "delivered" only when
`Order.status == delivered` (C7, P-6 design section 2). Where a task and an order both exist, the stricter of
the two applies (PROPOSED).

### 8.2 The evidence read

`claim_evidence` returns booleans and ids only and stores nothing (P-6 design section 3). Q-8 adds `tasks`:
a list of `{ref, status, started, done, approved, evidence_complete}` for the conversation's customer, read
through the same scoped repositories. No second function (P-6 design decision 3). UNKNOWN: whether the P-4
S7a audit has merged and fixed the signature (plan section 8, P-4).

### 8.3 Pre-presentation check (Q-9)

Q-9 (`pi-fast-track-plan.md:229`): "the check flags a seeded missing requirement, constraint violation and
unsupported claim in 100% of scripted negatives; false positive rate on positives stays under the owner's
limit". The **unsupported claim** part is the P-6 gate. Proposed placement of the three checks as one
function `presentation_check(draft, evidence, record)` returning a list of issues, run at two points:

1. **At drafting time, before the reviewer sees a document** (`draft_offer`, `brain_docs.py:601-773`, which
   already has an attempt-and-validate loop at `:661-673` per the blueprint design section 6.1 step 3, and
   `check_content` `brain_docs.py:286` as the existing validator). It checks missing requirement (a stored
   requirement not covered by any component or `wont_do`) and constraint violation (a component contradicts
   a stored constraint). Issues go to `review_notes` (`brain_docs.py:746` per the blueprint design) for the
   reviewer; they never silently edit the document.
2. **On the final reply, before sending** (the P-6 point). It checks unsupported claims only; requirements
   and constraints are not re-checked in chat, to keep the one-question rule and latency intact (UNKNOWN:
   latency budget, `latency.py` not read).

Both points are code, deterministic, and scripted-tested first. Whether a model assists in judging "covers
requirement" is open; it is excluded from the first cut because "scripted" results must not be labelled
"AI quality" (plan section 8, P-2 row). The false-positive limit is an owner number (D5, pending): UNKNOWN.
Q-9 depends on FT-C1 (plan `:229`), which was not read here.

### 8.4 Outcome after delivery

Unchanged from the P-6 design section 5: delivered is evidence of delivery, not of outcome. A task with a
`customer_confirms` acceptance check is `done` only when the customer's confirming message exists; the
evidence row's `ref` is that message id (EXISTS: `save_feedback` stores feedback, P-6 design section 5 cites
`service_conversation.py:7558-7600`; not re-read here). pi never marks it.

### 8.5 Interaction with `PiReplyAudit`

PROPOSED, optional: store in `PiReplyAudit.linter` (`learning_models.py:162`, JSONB, identifiers only) the claim
types the gate saw and whether each was `supported`, `rewritten` or `dropped`. No text and no new column.
This lets `pi-trace` show why a sentence was rewritten. It is stamped after the reply is saved
(`learning_audit.py:12-13`), so it records, it does not decide.

## 9. Non-negotiables mapping (CLAUDE.md)

| Non-negotiable | How Q-8 / P-6 respects it | Enforced in |
|---|---|---|
| First message says pi is an AI; "are you human?" answered "I'm an AI" | untouched; the gate never removes the disclosure (P-6 criterion 3) | existing linter; test that the gate keeps it |
| One question per message, last sentence | claim rewrite runs before `final_one_question`, which still sees final text (P-6 design section 4) | `service_conversation.py` last pass |
| No product, document, quote or price while listening | tasks exist only after offer, yes, approval, payment, kickoff: S12 or later | `flow.py:96-117`; task creation precondition |
| No payment in chat; no card, password, OTP, ID | tasks carry no payment step; a payment action is not a task type | section 11 |
| Reviewer approves every document and quote; pi never prices | unchanged; task approval is additional, never a replacement | `brain_docs.approve`, R-DOC-00 (`pi-brain-v3.txt:3098`) |
| No legal, medical, financial or tax advice; emergencies stop the flow | a task description is staff text; chat about tasks goes through the same safety gates (pre-model) | `safety.py`, `safety_guard.py` |
| Roles, never third-party names; redact before storing | redaction on every stored string (section 7.5) | `problem_fields.clean` path |
| Branding Workzap only; British spelling | customer-visible status written by staff; fixed lines in the lint | linter |
| Rules in code, learned content below the rules | no task path reachable from a model or from learning (principles 3 and 5; test) | route permissions, import check |
| "Payment received" only after staff confirm | tasks require a confirmed payment; gate C5 unchanged | `brain_payments.confirm`, `constitution.py:1841` (per P-6 design) |

## 10. State machine placement

No new `State` member and no new legal move in `flow.py`. Task states are a separate, per-task machine
(section 3.2); the conversation stays in `S13_IN_BUILD`, which is terminal today (`flow.py:117`). This agrees
with the blueprint design section 8 (`pi-solution-blueprint-design.md:294-306`). Rationale: `flow.py` models
the *conversation's* stage; several tasks are active at once, and a conversation can have none yet. Risk: S13
has no exit, so a finished project cannot leave S13; a "project complete" move is out of scope here and is an
owner question (D8). Existing hooks that already move S11 to S13 (`brain_payments.py:143-155`,
`flow.py:254-280`) are not changed.

## 11. Boundaries and what is never in scope

Never a task type, now or later without a separate owner decision with its own design: moving or requesting
money; sending a message to anyone from a task transition; booking; any change to the customer's or
Workzap's production systems performed *by this software*; deleting data (erase stays `erase_customer`);
anything with `rollback.reversible = false`. If the owner later wants software-run actions, the minimum is: a
named, allow-listed action type; per-run approval of the exact parameters; a dry run that writes an execution
row without effect; idempotency keys; an automatic rollback or a stop-and-hand-over; a per-tenant kill switch;
a two-person rule. That is a new design, not an extension of this one.

## 12. Staged merge plan (files touched, conflict risk)

Hot files named by the integrator: `service_conversation.py` (about 7,800 lines per the P-6 design section
10), `problems.py`, `decisions.py`, `part19.py`. **`part19.py` does not exist on `origin/main` b25e04c** (it is
untracked in the working tree of another session, and the P-6 design cites it only as `[a4fd6dc]`), so I read
nothing in it and every reference to it is UNKNOWN. All stages avoid these files except where stated.

| Stage | Content | Files (new unless marked) | Hot-file touch | Conflict risk | Depends on |
|---|---|---|---|---|---|
| T0 | this document, owner decisions D1 to D8 | `docs/pi-saas/pi-controlled-execution-design.md` | none | none | none |
| T1 | task service, scripted: states, transitions, dependency and cycle checks, approval by hash, import-graph "no model path" test; no DB | `pi/task_flow.py`, `tests/unit/test_pi_task_flow.py` | none | none | D1, D2 |
| T2 | migration and models (option A or B), event table, erase step, two-tenant and erase tests | `migrations/versions/00NN_*.py`, `pi_saas/models.py` (edit, option A) or `pi/task_models.py`, `pi/brain_erase.py` (edit, a step and the kept counts) | none of the four | low to medium: `brain_erase.py` and `pi_saas/models.py` are shared files (UNKNOWN: current churn) | T1, D6, migration number free |
| T3 | routes and permissions, audit rows | `pi/task_routes.py`, router registration (one line, file UNKNOWN, `pi/routes.py` not read), `access/permissions.py` (edit, if a new key, D2) | none | low; `access/permissions.py` is shared | T2 |
| T4 | evidence read: add `tasks` to `claim_evidence`; C13 to C17 detector patterns and templates in the P-6 `claims.py` | `pi/claims.py` (P-6, new), `tests/unit/test_pi_claims_tasks.py` | none yet | low | P-6 stage 1, FT-02 integrated |
| T5 | the gate call: one hunk at the final pass and one `FINAL_CHECKS` entry | `pi/constitution.py` (edit, one entry at `:2341`), `pi/service_conversation.py` (edit, one call near `:6384-6391`) | **both hot**; at most about 30 lines per hunk (plan section 1 rule per the P-6 design section 13) | **high**: the integrator rebases on the FT-02 and Part 19 hunks | T4, FT-02 |
| T6 | S13 prompt line and fixed task-status lines | `pi/flow.py` (edit, one string at `:187`), fixed lines file UNKNOWN | `flow.py` is shared with the flow owner | medium | T5 |
| T7 | Q-9 `presentation_check` at drafting time | `pi/presentation_check.py`, one call in `brain_docs.draft_offer` | `brain_docs.py` is lane S (the plan's lane table, per the P-6 design section 13) | low to medium | blueprint S-stages, FT-C1 |
| T8 | reviewer UI for tasks (web) | `apps/web` (UNKNOWN files) | none | UNKNOWN | T3 |

Each stage is its own branch, tests first, `ruff check`, `ruff format` on own files, `mypy app`, unit suite,
targeted integration on the disposable DB (`. ../../scripts/pi-test-env.sh`), rule-auditor on the diff, never
`git add -A` (CLAUDE.md; plan section 5 minimum checks). No migration is applied to the real database without
the user's request.

## 13. Test plan (scripted first; none run)

Unit, no DB: (1) every legal and illegal task move; (2) approval by hash: a changed scope or a stale hash is
refused; an edit clears approval; (3) approver is not creator and not owner; (4) dependencies: unmet,
cyclic, cross-customer refused; (5) rollback required: `reversible=false` blocks approval; (6) acceptance:
`done` refused without evidence rows for every check and with the wrong verifier; (7) no-model-path: import
graph and system-actor refusal; (8) **negative controls**: a service that lets pi approve or complete a task
must fail the suite; a gate that rewrites nothing must fail the claim tests; (9) claim detector table per type
C13 to C17 and language (en, roman_ur first; ur, ar, hi reported "not covered", P-6 design section 3); (10)
presentation check: seeded missing requirement, constraint violation, unsupported claim all flagged (Q-9
100% scripted negatives) and a labelled positive set measured for false positives.

Integration, disposable DB only: (11) two-tenant and two-environment isolation, same phone in both; (12) erase
blanks text, keeps ids and counts, `pi_task_events` handled, and C13 to C17 are unsupported afterwards; (13)
approval writes an `audit_events` row; (14) migration up and down, single head; (15) task creation refused
before payment is confirmed and before S12.

Real-model checks (proposals only; each needs its own approval, pricing and cap; none run, none authorised
by this document): a Stage 3 style replay of S13 chats designed to tempt a false "done" ("is it finished?"),
counted per 100 replies with the gate off and on (P-6 design section 8).

Status words (plan section 8): documented yes; implemented no; scripted-tested no; real-model-verified no.

## 14. Open owner decisions

D1. **Is Q-8 a ledger run by people, not an executor?** (this design's premise) If the owner wants any
software-run action, say which action type first (section 11).
D2. **Who may approve a task?** (a) existing `quotes.write` holder other than the creator; (b) the already
catalogued `quotes.approve` (`access/permissions.py:28`); (c) a new `pi.work.approve`. The document routes
use `quotes.write` for approve today (`brain_doc_routes.py:222-224`); aligning them is a separate change.
D3. **Option A, B or C for storage** (section 7). Recommendation: A for the first cut.
D4. **Which acceptance kinds are allowed**, and is `customer_confirms` enough for a given task type.
D5. **Does the customer approve any task?** Default no (section 5). Also the Q-9 false-positive limit and
thresholds (plan D5 is pending).
D6. **Retention:** is approved task scope a business record kept after erase like documents, or erased text
(R1 to R6, `pi-decision-retention-review.md`, not read here)?
D7. **Customer-visible wording** in section 6: who writes `customer_visible_status`, and may it be in the
customer's language (the other fixed lines are localised, `brain_docs.py:1162`)?
D8. **Project completion:** how a chat leaves S13 (`flow.py:117` has no exit).
D9. **Block "refunded", "reversed", "erased" claims outright** until record types exist (P-6 design
section 11 item 5; applies equally to C16).

## 15. Unknowns and what I did not read

- `part19.py` (not on `origin/main`); `box_doc.py` (only its call at `brain_docs.py:948` seen);
  `pi/tools/`; `pi/routes.py` and how routers register; `latency.py`; `problem_fields.py` (cited through the
  blueprint design); `service_conversation.py` beyond `:3475-3499` and `:6384-6391`; the callers of
  `erase_customer`; `core/exceptions.py` (B1 is cited through `pi-capability-map.md`); the web app.
- Not queried: any database. Not run: any test, lint, migration or model call.
- The shape of `WorkspaceScope.actor_type` values (only its use at `audit/service.py:46` was read).
- Whether anything already writes `PiTask.status = "done"` from a pi path (callers of `PiTask` not searched).
- Migration numbering: see section 7.2; check `alembic heads`.
- The spec text has no section about task execution or "Level 3": a grep of `spec-text/*.txt` for "Level 3",
  "autonomous" and "execut" found nothing relevant. The requirement comes from the plan (`pi-fast-track-plan.md:228`)
  and the coverage note (`pi-core-intelligence-coverage.md:50`), not from the platform spec. The nearest spec
  rules are R-DOC-00, R-DEC-01 to 05, R-PAY-05 and R-KICK-01 to 03 (`pi-brain-v3.txt:3098`, `:3262-3302`) and
  the S13 state (`:1496`, `:1619`).
