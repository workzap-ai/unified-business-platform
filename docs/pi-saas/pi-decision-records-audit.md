# FT-S7a: read-only audit of where pi keeps decisions (input to P-4)

Status: AUDIT, 2026-10-30, against `origin/main` cc462c5. Nothing was changed, queried or run: no database
(the real one included), no migration, no new table. Everything below was read from models and code.
"Inferred" marks a statement I did not confirm in code. Paths are under `apps/api/app/modules/`.

## 0. Scope and how decisions are stored today

pi has **no decision ledger**. A decision lives in one of four places:

1. **The conversation brief**: `pi_conversations.service_brief` (JSONB, `pi/models.py:192-238`), one per
   conversation. Written in `service_conversation.py` (`record_decision`, lines 3366-3454, and about a
   dozen other writers). Tenant-scoped through `tenant_id` and `environment_id` (`WorkspaceRow`).
2. **The conversation's flow state**: `flow_state`, `flow_state_since` on the same row, written at
   `service_conversation.py:1425-1446`. Only the current state, no history.
3. **Customer-level tables**: Solution Box and offer log (`pi/box_models.py`), brain documents and
   payments (`pi/brain_docs_models.py`), problems and revisions (`pi/problem_models.py`), `pi_memories`
   (`pi/memory_block.py`), idea feedback (`pi/solution_models.py`). All scoped by tenant and environment.
4. **The deal flow tables** (`pi_saas/deal_models.py`, `pi_saas/deals.py`): `pi_documents` and the
   commerce `Quote`, `sales_leads`, `customer_activities`.

What a **new** conversation of the same customer inherits (`pi/slot_carry.py`): only `closed_slots` (the
question text, never the answer) and `asked_facts`, within 30 and 2 days, marked `carried`. No decision
key is copied. Customer-level tables are readable by any new conversation of that customer (the brain
reads `brain_docs.open_quote(customer_id)` at `service_conversation.py:1585`), so a decision survives a
new chat only where it is in a customer-level table **and** some code reads it.

## 1. Decision records, one by one

| Decision | Where stored (file:line) | Writer | Level | Tenant scope | Survives into a new chat? | Erase today | Redaction |
|---|---|---|---|---|---|---|---|
| **Offer made** | `pi_offer_log` row per canOffer check: `rule`, `allowed`, `blocked_reason` (`box_models.py:86-99`; writer `box_lifecycle.py:190-205`); `pi_solution_boxes.state`/`offered_at` (`box_models.py:58-83`); `pi_box_transitions` (`box_models.py:102`); brief `offer_asked` (`decisions.py:563`) | `box_lifecycle.log_offer`, `box_lifecycle.offer`, `decisions.decide` | log: per conversation; box and transitions: per customer; brief: per conversation | yes (`WorkspaceRow`, scoped FKs) | box and transitions: yes, per customer. Offer log and brief: no | log erased (`brain_erase._erase_conversation_extras`, lines 51-70); box and transitions erased (`_erase_map_and_boxes`, lines 73-125); brief set to `{"erased": true}` | log holds a rule id and a reason only, no customer words |
| **Offer declined** | brief `offer_declined` (`decisions.py:727`), brief counter `declines` (`service_conversation.py:3370-3371`), brief `box_declined_at` (`box_lifecycle.py:275`); the box goes `offered -> collecting`, reason "owner declined" (`box_lifecycle.py:272-274`) | `decisions.decide`, `record_decision`, `box_lifecycle.on_decision` | brief: per conversation; transition row: per customer | yes | **brief keys: no.** Only the box transition row survives, and nothing reads it for the next chat. `declines` changes idea behaviour (`solution_context.py:83,370,656,713`, `solution_ask.py:406`) and is lost | as above | transition `reason` is fixed text |
| **Quote requested** | effect `request_solution` (`service_conversation.py:3383`); document and quote drafts in `pi_brain_documents` (`brain_docs_models.py:39-90`: `offer_id`, `kind`, `status`, `problem_ids`, `content`) | `brain_docs`, `service_conversation` | per customer, `conversation_id` nullable | yes | yes (`open_quote` reads the latest sent quote by customer) | **kept** on erase (`brain_erase.py:287-300`, kept reason "business records the company must be able to show") | `content` is built from the owner's problem words; inferred that it passes the redactor like the problem path, not confirmed |
| **Quote approved by staff** | `pi_brain_documents.status = approved`, `approved_by`, `approved_at`, `sent_at` (`brain_docs_models.py:78-84`; written `brain_docs.py:1004`) | staff through `brain_doc_routes.py` | per customer | yes | yes | kept | none stored beyond ids |
| **Quote approved by the customer** (explicit, confirmed twice) | brief `approval` `{quote, at}` (`service_conversation.py:3438-3441`); box `sent -> accepted`, reason "owner approved the quote" (`box_lifecycle.py:278-279`); `pi_brain_payments` row opened (`brain_docs_models.py:93-111`, `brain_payments.open_for`); a staff decision request raised (`service_conversation.py:3449-3452`, table in the requests module, not read for this audit) | `decisions.decide` (`decisions.py:776`), `record_decision` | brief: per conversation; box and payment: per customer | yes | box and payment: yes. Brief `approval`: no (the quote id and time are lost to the next chat; the payment row keeps the quote id) | box erased; payments **kept** | quote id only |
| **Revision requested** | brief `revision_requested {changes, message_id}` (`decisions.py:632`); effect `request_revision` raises a request (`service_conversation.py:3424-3428`); box `sent -> changes_asked` (`box_lifecycle.py:276-277`); the new version supersedes the old (R-QUOTE-08, `brain_docs_models.py:7-9`) | `decisions.decide` | brief: per conversation; versions and box: per customer | yes | versions and box yes; the owner's requested changes (free words in `changes`) stay in the brief and the staff request only | brief erased; the staff request is outside `brain_erase` (see G4, `pi_staff_requests`, in `pi-erase-gaps-g1-g14.md`) | `changes` are the owner's words; redaction at this write not confirmed (inferred) |
| **Quote declined** | `decisions.py:823` sets state `S9B_DECLINED_QUOTE` with an empty brief; no brief key | `decisions.decide` | conversation flow state only | yes | no | not applicable (state is reset with the conversation) | none |
| **Deal response** (customer opens the proposal page or answers in chat) | `pi_documents.response` in (`accepted`, `changes`, `rejected`), `response_note`, `responded_at`, `viewed_at` (`deal_models.py:40-66`; written `deals.py:1016-1034`); accepting moves the commerce quote to accept and the lead to `won` (`deals.py:1027-1029`) | `pi_saas/deals.respond` | per customer | yes | yes (documents are per customer) | `pi_documents` is **not** in `brain_erase`: free text `message_text` and `response_note` stay (G9) | none on `response_note` (2,000 characters, `deals.py:1025`) |
| **Brief confirmed** | deal flow: confirmed brief makes the proposal and moves the lead to `qualified` (`deals.py:3-7`, `deals.py:609-663`); the flag in the conversation brief was not located (inferred) | `pi_saas/deals` | lead: per customer; flag: per conversation | yes | lead yes; flag no | `sales_leads` not erased (G14) | `requirements` JSONB, redaction not confirmed |
| **Corrections** | `pi_problem_revisions` (`problem_models.py:111-128`, `reason` in created, correction, enrichment, merged; R-MEM-04); memory facts: the old `pi_memories` row set to `archived`, the new one added (`memory_block.py` docstring, `MAX_ARCHIVED = 30`) | `problems.py`, `memory_block.py` | per customer | yes | yes (problems and memory are customer-level) | erased (`brain_erase.py:141-204`) | memory values pass the redactor; roles not names (R-PRIV-04) |
| **Problem status** | `pi_problems.status` (`problem_models.py:98`, values in `taxonomy.STATUSES`) | `problems.py` | per customer | yes | yes | erased | as problems |
| **Attempted actions** (what the owner tried, with outcome) | **not stored as a structure.** One free slot `current_workaround` per problem and the model's own notes; tool attempts in `pi_tool_calls`; pending drafts in `pi_pending_actions` (`pi/models.py:353,375`) | extractor, tools | per conversation (tools) or per problem (slot) | yes | the workaround slot yes; outcomes no | `pi_pending_actions` not erased (G6) | n/a |
| **Facts about the business** (`memory_block`) | `pi_memories` rows, kind context or preference, `key: value`; keys: name, role, business_name, business_type, location, team_size, channels, current_tools, website, goal (`memory_block.py` `FACTS`) | `memory_block` | customer; business-level keys shared between contacts of one business (`BUSINESS_KEYS`), person-level keys not | yes | yes | erased (`brain_erase.py:204`) | redactor first, short facts, roles not names |
| **Ideas given and owner feedback** | `pi_solution_memory`, `pi_idea_feedback` (`solution_models.py`) | `solution_ideas`, learning | per customer | yes | yes | erased (`brain_erase.py:149-160`) | stored text redacted (inferred) |
| **Conversation flow state** | `pi_conversations.flow_state` | `service_conversation.py:1425-1446` | per conversation | yes | no (a new conversation starts at S0 or S1) | reset with the conversation | none |
| **Move history** | `pi_move_log` (`think_models.py:23`) | think layer | per conversation | yes | no | erased (`brain_erase.py:239`) | none |

## 2. Findings

1. **No cross-conversation decision memory in the brief.** `declines`, `box_declined_at`, `offer_declined`,
   `approval` and `revision_requested` die with the conversation. A returning customer who declined an
   offer yesterday is treated as one who never did, except that the box's state persisted at customer
   level. `declines` is used by the idea logic (`solution_context.py:83`, `solution_ask.py:406`), so this
   is a behaviour gap, not only a data gap.
2. **The strongest existing decision evidence is already customer-level and append-only:**
   `pi_box_transitions` (from state, to state, actor, reason, time), `pi_brain_documents`
   (`approved_by`, `approved_at`, `sent_at`, versions), `pi_brain_payments` (`confirmed_by`,
   `confirmed_at`). These are the natural evidence source for P-6.
3. **Declined is not a durable state.** The box returns `offered -> collecting` on a decline; the only trace
   is a transition row with a fixed reason and a brief key. A "declined" state exists in the machine
   (`sent -> declined`, `box.py:114-124`) but only after sending.
4. **Quote and payment records are kept on erase by design**; documents contain content derived from the
   customer's words. A ledger that points at them would also survive, consistent with that policy, but the
   retention decision (R1 to R6 in `pi-erase-gaps-g1-g14.md`) is still open.
5. **The deal flow records free text that erase does not reach**: `pi_documents.message_text` and
   `response_note` (G9), `sales_leads.requirements` and notes (G14), `customer_activities.summary` (G12).
6. **"Attempted actions" have no structure** (B2a `tried` is planned): today there is one workaround slot.
7. **Tenant scope is consistent.** Every table above is a `WorkspaceRow` with tenant and environment and
   scoped foreign keys; I found no unscoped read in the paths I read.
8. **memory_block keys are only business facts.** Adding decision keys would reuse the shared `FACTS` tuple,
   which `slot_carry.ASKED_KEYS` also reads, so a new key changes the "asked facts" carry as a side effect.

## 3. Decision type -> stored? -> carried to a new chat? -> gap

| Decision type | Already stored? | Carried to a new chat? | Gap |
|---|---|---|---|
| Offer made | yes (box, offer log) | box yes; log no | none for the box; pi does not tell the model an offer was made before |
| Offer declined | brief only (+ a transition row) | no | **yes**: a returning decliner looks new; `declines` lost |
| Quote requested | yes (`pi_brain_documents`) | yes (`open_quote`) | none beyond erase retention |
| Quote approved by staff | yes | yes | none |
| Quote approved by the customer | brief + box + payment row | box and payment yes, brief no | partial: the quote id and time are lost from the brief; the evidence exists elsewhere |
| Revision requested | brief + box + versions | versions yes, the words no | partial: the owner's change list is lost to the next chat |
| Quote declined | flow state only | no | **yes**: no durable record |
| Confirmed change to a fact | yes (memory archive, problem revisions) | yes | none |
| Attempted action and outcome | no structure | no | **yes** (planned in B2a) |
| Brief confirmed | lead and flag (flag not located) | lead yes | to verify |
| Deal accept, changes, reject (page) | yes (`pi_documents.response`) | yes | free text not erased (G9) |

## 4. Minimal design options (PROPOSALS, nothing built, not recommended over one another yet)

**A. Read existing customer-level records at context time (no new storage).** A small read-only function,
in the style of `brain_docs.open_quote`, returns "declined an offer on date", "approved quote Q-0002",
"asked for changes" from `pi_box_transitions`, `pi_solution_boxes`, `pi_brain_documents` and
`pi_brain_payments`. Tenant: scoped by `WorkspaceRepository`. Erase: box and transitions already erased,
documents and payments kept under today's policy. Retention: unchanged. Privacy: stores nothing new and
exposes ids, states and dates only. Limit: it cannot hold a decision that no existing row records
(a decline today is only a transition reason, quote declined only a flow state), so for those it needs a
small additive reason string on the existing transition, not a new table.

**B. New keys in `memory_block` (`pi_memories`).** Customer-level rows like `offer_declined: <date>`.
Tenant and erase: already covered (`erase_customer` deletes all rows). Retention: archived history is
capped at 30 per person. Privacy: values pass the redactor. Limits: the block is capped at 700 characters
and the `FACTS` tuple also feeds `slot_carry.ASKED_KEYS`, so keys must be added to a separate set; decisions
are not "the person's own words", which is the module's stated purpose.

**C. Extend `slot_carry` to copy a few brief keys** (`declines`, `box_declined_at`) for a window.
Tenant and erase: copies are erased with the customer (`erase_customer` clears every conversation).
Privacy: counters and dates only. Limit: a copy can go stale; it keeps decisions in a per-conversation place,
where the statement of what is true should be customer-level.

**D. A new decision-ledger table (needs migration 0054).** Not supported by this audit: options A to C cover
the gaps found, and `pi_box_transitions` is already an append-only record of actor, move, reason and time.
It would only be justified if the owner requires one immutable, queryable cross-feature ledger that the
records above cannot give. If it were ever built it would need the same tenant, environment, erase and
retention design as `pi_box_transitions`, and a decision on whether it survives erase like documents do.

## 5. Dependencies and outstanding decisions

- **Depends on** the erase retention decisions R1 to R6 (`pi-erase-gaps-g1-g14.md`): whether quotes and
  payments stay after an erase decides whether a decision that points to them stays.
- **Related** to S6-a (`memory_block` keys), B2a (`tried`, structured attempted actions), P-6 (the
  transition, document and payment rows are its evidence source) and FT-02 (Part 19 changes some
  decision wording; not touched here).
- **Owner decisions:** (1) is a decline a fact pi may remember across chats, and for how long; (2) do
  decision records follow the erase policy of documents (kept) or of memory (erased); (3) whether option D
  is ever wanted; (4) whether the quote's revision wording may be remembered across chats.

## 6. Limitations (what was read, what was inferred)

- Read: the models listed above, `brain_erase.py`, `slot_carry.py`, the head of `memory_block.py`,
  `decisions.py` at the cited lines, `box_lifecycle.py` lines 185-280, `service_conversation.py` lines
  1415-1450 and 3366-3470, `deals.py` at the cited lines, and `pi-erase-gaps-g1-g14.md` (via `git show`).
- Inferred, not confirmed: where the "brief confirmed" flag lives; whether `content` and `changes` pass
  the redactor; the table behind `raise_decision_request`; the contents of `pi_solution_memory`.
- Not read: the commerce `Quote` model, `customer_activities` writers, `brain_payments.py`, the learning
  tables. No database was queried, so no row counts or real data are reported.
