# P-4 retention review: how long pi should keep each decision, and what an erase does to it

Status: FOR OWNER REVIEW, 2026-10-30. Documentation only. No migration, no new table, no code change, no
database use (the real one included). Read against `origin/main` cc462c5 in the worktree
`.cache/lanes/s7`. Nothing here is implemented, scripted-tested or real-model-verified.

How to read the marks:
- **[FACT]** read in code or a document; the path and line are given.
- **[INFERRED]** not confirmed in code; stated so.
- **[APPROVED]** an owner decision recorded in the master roadmap.
- **[PROPOSED]** my suggestion; not approved, and no acceptance criterion changes because of it.

Paths are under `apps/api/app/modules/` unless they start with `docs/`, `tests/` or a branch name. Roadmap
references are to `docs/pi-saas/pi-fast-track-plan.md` on branch `pi/doc-fast-track` ("roadmap:LINE");
consolidated-review references are to `docs/pi-saas/pi-p1-p5-consolidated-review.md` on the same branch
("consolidated:LINE"); erase-gap references to `docs/pi-saas/pi-erase-gaps-g1-g14.md` on `pi/d-erase-gaps`.

## 0. Check against the approved master roadmap (sections 1 to 8) and P-1 to P-6

| Roadmap item | What it says | Status | Effect on this document |
|---|---|---|---|
| D1 merge policy, D2 B2 field set, D3 S6-a (no new table), D4 | roadmap:119-122, confirmed approved at roadmap:130-131 | [APPROVED] | Nothing here changes D1 to D4. D3 ("no new table unless S6-a is not enough") is respected: no option below needs a table except D, which is not recommended. |
| D5, D7, D8 | pending (roadmap:131-132) | pending | Not touched. |
| P-4 | "FT-S7a read-only audit ... then FT-S7b privacy-safe decision ledger"; S7b: "reuse existing records or `memory_block` first; a new table or migration only if S7a proves it necessary and the owner approves" (roadmap:170) | [APPROVED] as a task; the ledger design itself is not approved | This document is input to FT-S7b. It does not start S7b and does not change its acceptance text. |
| Roadmap conflicts 3 and 4 (P-4 vs D3; P-4 and erase) | roadmap:182-185 | open | Section 7 below lists the same conflicts with line evidence and adds new ones. |
| Merge check 5 and 6 (two-tenant test for new stored data; erase covers any new table, column or brief key) | roadmap:104-105 | [APPROVED] | Any option B or C below must meet both before it ships. Stated in section 3. |
| P-1 (schema), consolidated conflicts C2, C3, C7, C8 | consolidated:149, 150, 154, 155 | proposals under review | See section 7, items 4 to 7. Consolidated C8 is partly wrong (section 7, item 3). |
| P-6 (evidence-backed claims) | roadmap:172 | planned | Section 4, Q3 and section 5 say which existing records could be its evidence. |

No acceptance criterion in the roadmap is changed by this document.

## 1. What the repository says about retention

| # | Source | What it says | Mark |
|---|---|---|---|
| 1 | `pi/brain_erase.py:1-15` | Erase removes problems, map, Solution Boxes and their move history, offer log, profile, open items, move log, memory notes, quarantine copies, learning scores and message words. It keeps quotes, solution documents and payments ("business and financial records the company must be able to show") and the CRM contact. It cites platform spec 4.9 item 10 and ST12 ("the box history follows the retention rules"). | [FACT]. I read the code comment, not the PDF. |
| 2 | `pi/brain_erase.py:306-314` | `kept_reasons` for documents, payments, customer contact and message rows. | [FACT] |
| 3 | `tests/unit/test_pi_erase_completeness.py:36-47` | Tables deliberately not erased, with reasons. `pi_customer_consents` is listed: "consent evidence must outlive an erase request; no customer words" (line 40). | [FACT]. The only existing rule that a *decision record* outlives an erase. |
| 4 | `docs/pi-saas/pi-rule-coverage.md:84` | `App.D-4` (Brain p.447): retention periods for messages, quarantine and learning data are a human decision for the Workzap owner; "code defaults are safe until it is made". | [FACT]. Decision records are not named, so they have no stated period. |
| 5 | `docs/pi-saas/pi-brain-state-machine-plan.md:124` | Retention for messages and the PII quarantine must match the public privacy page. | [FACT]. The privacy page was not read. |
| 6 | `docs/SECURITY.md:48` | "define retention/access policies before production". | [FACT] |
| 7 | `pi/slot_carry.py:30-31` | Answered questions carry for 30 days, an unanswered asked fact for 2. | [FACT] |
| 8 | `pi/memory_block.py:45` | At most 30 archived values per person. | [FACT] |
| 9 | grep of `purge`, `retention`, `older than` over `pi/*.py` | No purge job for decisions in the pi module. | [FACT] for the pi module only; other modules were not searched. |

**Spec PDFs: retention text was not searched.** No text extraction exists under `docs/` in this worktree; the
six PDFs are untracked files in the shared tree. "Owner to decide" below means no retention rule was found in
rows 1 to 9 above, `CLAUDE.md` or the coverage documents.

## 2. The decision types: what is stored, why, and whether an erase removes it

This table covers the 16 rows of my earlier audit plus one I missed (row 17). Erase column: **E** = erased
with the customer, **K** = kept on purpose, **G** = kept but holds words (known gap), **S** = survives an
erase (not in the erase code).

| # | Decision | Where stored (path:line) | Sensitivity (mine) | Business purpose | Reason to keep | Erase today |
|---|---|---|---|---|---|---|
| 1 | Offer made | `pi/box_models.py:58` box, `:86-99` offer log (`blocked_reason` :99), `:102-118` transitions; brief `offer_asked` `pi/decisions.py:563`; move on offer `pi/box_lifecycle.py:263-267` | Low (rule ids, states) | prove the offer rules held; next move | ST12 "retention rules" (period unset); owner to decide | **E**: offer log `pi/brain_erase.py:56`, boxes and transitions `:89-125`, brief `:265` |
| 2 | Offer declined | brief `offer_declined` `pi/decisions.py:727`; `declines` `pi/service_conversation.py:3371`; `box_declined_at_pi` `pi/box_lifecycle.py:37,274`; `box_declined_at` `:275`; transition "owner declined" `:272-273` | Low | stop re-offering (B7: no new offer for 8 messages, `pi/box.py:16,70-74,172-179`; `pi/box_lifecycle.py:35,51-56`); ideas after a decline `pi/solution_context.py:78-86` | none found | **E** (transition `pi/brain_erase.py:97-103`, brief `:265`) |
| 3 | Quote requested | effect `request_solution` `pi/service_conversation.py:3383`; `pi_brain_documents` `pi/brain_docs_models.py:39-79` (status :75) | Medium (`content` is built from the owner's words, [INFERRED] redacted) | the quote | "records the company must show" `pi/brain_erase.py:310` | **K** `:286-295` |
| 4 | Quote approved by staff | `pi/brain_docs_models.py:77-79` (`approved_by`, `approved_at`, `sent_at`) | Low | proof a reviewer approved (CLAUDE.md) | same | **K** |
| 5 | Quote approved by the customer | brief `approval` `pi/decisions.py:780`, `pi/service_conversation.py:3438-3439`; box accepted `pi/box_lifecycle.py:278-279`; payment `pi/brain_docs_models.py:93-114` (`confirmed_by` :113) | Low-medium | agreement; payment follow-up | payments: `pi/brain_erase.py:311` | payments **K** `:296-305`; box **E**; brief **E** |
| 6 | Revision requested | brief `revision_requested` `pi/decisions.py:632`; effect `pi/service_conversation.py:3424-3433`; box changes_asked `pi/box_lifecycle.py:276-277` | Medium (the owner's words) | version N+1 | quote versions are records; words: none found | brief **E**; staff-request copy **G** (G4, `tests/unit/test_pi_erase_completeness.py:58-59`) |
| 7 | Quote declined | flow state `S9B_DECLINED_QUOTE` `pi/decisions.py:651,660,823`. The box machine has `sent -> declined` (`pi/box.py:102,114,116,124`) but `on_decision` never makes that move (`pi/box_lifecycle.py:263-279`) and nothing else in `pi/*.py` writes the state `"declined"` (grep) | Low | stop chasing | none found | flow state **S** (see row 15); no other record |
| 8 | Deal response (page or chat) | `pi_saas/deal_models.py:62-66` (`message_text`, `response`, `response_note`); written `pi_saas/deals.py:1025`; lead to won `:1030` | Medium (free text) | accept, changes, reject | the document is a record; the note is not | **G** (G9, `tests/unit/test_pi_erase_completeness.py:68-69`) |
| 9 | Brief confirmed | lead "qualified" `pi_saas/deals.py:3,236-237`; the conversation-brief flag: not located | Medium-high (requirements, notes) | sales pipeline | owner to decide (R5) | **G** (G14, test:78-79) |
| 10 | Corrections | `pi/problem_models.py:111-126` (revision `reason` :126); memory archive `pi/memory_block.py:10,355` | Medium | show what changed (R-MEM-04) | none found | **E** `pi/brain_erase.py:139-206` |
| 11 | Problem status | `pi/problem_models.py:98` | Low | track open or solved | none found | **E** |
| 12 | Attempted actions and outcomes | slot `pi/problem_models.py:93`; `pi_tool_calls` `input`/`output` JSONB `pi/models.py:353-372`; drafts `pi/models.py:375` | Medium ([INFERRED] for tool JSON) | what pi did or drafted | none found | slot **E**; drafts **G** (G6, test:62-63); `pi_tool_calls` **S** (section 5) |
| 13 | Facts about the business | `pi/memory_block.py:48,61` | Medium | stop re-asking | none found | **E** `pi/brain_erase.py:202-206` |
| 14 | Ideas given, owner feedback | `pi/solution_models.py:70,99` | Low-medium | cap of ideas per business | none found | **E** `pi/brain_erase.py:147-160` (audit range; the delete calls are at :147-157) |
| 15 | Conversation flow state | `pi/models.py:233-234` (`flow_state`, `flow_state_since`) | Low (a state name) | where the chat is | none found | **S**: the erase update sets only `service_brief`, `followup_due_at`, `summary` and the preview (`pi/brain_erase.py:259-270`), not the flow state |
| 16 | Move history | `pi/think_models.py:23` | Low | explain the chat's moves | none found | **E** `pi/brain_erase.py:237-243` |
| 17 | **Reminder and marketing consent** (new row) | customer level `pi_saas/models.py:710-726` (purpose reminders or marketing, status granted or withdrawn, `source`); per conversation brief key `reminder_consent` (`pi/service_conversation.py:6510-6519`; read by `pi/followups.py:192,272,366`, `pi/brain_followups.py:105,236,435`, `pi/check_in.py:148,200`) | Low-medium (an opt-out is personal) | lawful follow-up and campaigns | **a keep rule exists**: `tests/unit/test_pi_erase_completeness.py:40` | table **K** on purpose; brief copy **E** (`pi/brain_erase.py:265` replaces the whole brief) |

## 3. Retention options and what each does

Letters used in section 6: **A** keep as a record that survives an erase; **B** keep for N days, or keep the
row and strip the words (anonymise); **C** erase with the customer and do not carry across chats.

| Effect | A keep | B limited or anonymised | C erase, do not carry |
|---|---|---|---|
| pi behaviour | recognises a returning customer from the record | remembers inside the window, then behaves as new | treats a returning customer as new (today for rows 2, 5-brief, 6, 7) |
| Erase completeness | list it in `kept` with a reason (`pi/brain_erase.py:286-314`) and in `ALLOWED` (`tests/unit/test_pi_erase_completeness.py:36-47`) | an erase change (blank the words, keep the row), a failing test first, removal from `KNOWN_GAPS` (`:51-80`) | already satisfied for customer-level tables; any new copy needs an erase and a test (roadmap:105) |
| Tenant isolation | rows are `WorkspaceRow`; every read behind tenant, environment and customer | same; a carried marker is read only for the same workspace and customer, as `pi/slot_carry.py` does | nothing new stored |
| New storage | none for rows 3 to 5 and 17 (already kept) | read existing rows, or copy a few brief keys; no new table | none |

## 4. The four owner questions, with options (all [PROPOSED]; owner decision pending)

**Q1: how long may pi remember a decline across chats?**
- Options: 0 days (today); 30 days (the window `pi/slot_carry.py:30` already uses); 90 days; until the box
  changes state; forever.
- What exists today [FACT]: within one conversation a decline blocks a new offer for 8 messages (B7:
  `pi/box.py:16,70-74`; counted from `box_declined_at` string, `pi/box.py:172-179`, and from
  `box_declined_at_pi`, a per-conversation sent-message count, `pi/box_lifecycle.py:37,51-56,274`) and
  lowers the idea allowance (`pi/solution_context.py:78-86`). None of this reaches a new conversation.
- A decline **does** leave a durable row where the box feature is on: the transition `offered -> collecting`
  with reason "owner declined" (`pi/box_lifecycle.py:272-273`), per customer, no schema change needed
  (`reason` is free text, `pi/box_models.py:118`; the only constraint on that table is on `actor`, `:111`).
  The box feature is a workspace setting (`pi/box_lifecycle.py:47-48,257`), so for workspaces with it off there
  is no row. A reader that surfaces this row in a new chat needs no new reason string and no migration.
  (This corrects my earlier audit and consolidated C8, see section 7, item 3.)
- Cadence: the 8-message quiet is message-count based; a cross-chat window would be date based, so it would
  be a different clock, not an extension of B7. [INFERRED] whether platform spec Book 5 allows a longer quiet
  was not checked.
- **Proposal:** a read-only marker (count and date, no words) for 30 days, cleared by a new R1 ask or R3
  signal, erased with the customer. Needs a rule-auditor and spec check first.

**Q2: do decision records follow the document policy (kept) or the memory policy (erased)?**
- Options: all kept; all erased; split by purpose.
- Precedent [FACT]: consent is kept on purpose (`tests/unit/test_pi_erase_completeness.py:40`); quotes and
  payments are kept (`pi/brain_erase.py:310-311`); box history and transitions are erased
  (`pi/brain_erase.py:89-125`; comment at `:11-13`).
- **Proposal:** split. Evidence that holds ids, states and times and that the company must be able to show
  follows the document policy; behavioural memory (a decline marker, the owner's revision words) follows the
  memory policy. The owner decides whether box transitions count as evidence, because today they are erased.

**Q3: do you ever want option D (a new decision-ledger table, migration 0054)?**
- Evidence that already exists and is append-only [FACT]: transitions (`pi/box_models.py:102-118`),
  document approval (`pi/brain_docs_models.py:77-79`), payment confirmation (`:113-114`), consent
  (`pi_saas/models.py:710-726`). Tool-run outcomes sit in `pi_tool_calls` (`pi/models.py:353-372`), which is
  not erased and has no customer or conversation column (section 5).
- **Proposal:** no new table now; decide Q3 together with P-6's evidence design (roadmap:172).

**Q4: may the quote's revision wording be remembered across chats?**
- Options: never carry the words; carry a flag only ("changes asked on version N"); carry the words N days.
- The words are the owner's (`pi/decisions.py:632`) and also sit in the staff request (G4).
- **Proposal:** do not carry the words; keep the versions.

## 5. Erase gaps that touch decisions, and new candidates

| Item | Table | Decision touched | What survives an erase | Source |
|---|---|---|---|---|
| G9 | `pi_documents` | rows 6, 8 | `message_text`, `response_note` | `tests/unit/test_pi_erase_completeness.py:68-69`; `pi_saas/deal_models.py:62,65` |
| G12 | `customer_activities` | decision events in the timeline | `summary` | test:74-75; erase-gap doc section 3 |
| G14 | `sales_leads` | row 9, and row 8 accept (lead won) | `requirements`, `notes`, `title` | test:78-79; `pi_saas/deals.py:1030` |
| G4 | `pi_staff_requests` | rows 5, 6 | question, summary, answer | test:58-59 |
| G6 | `pi_pending_actions` | row 12 | payload, summary | test:62-63 |
| New 1 (inferred) | `pi_tool_calls` | row 12 | `input`, `output` JSONB, if they hold words | `pi/models.py:353-372`: no `customer_id` or `conversation_id` column, so the completeness test (`KEYS`, test:33) cannot see it; `pi/brain_erase.py` never names it |
| New 2 | `flow_state`, `flow_state_since` | rows 7, 15 | the state name, for example a declined quote | `pi/models.py:233-234`; not in the erase update `pi/brain_erase.py:259-270` |

Whether `pi_tool_calls.input/output` ever holds customer words is not confirmed.

## 6. Decision table for the owner to fill in ([PROPOSED] column is mine, not a decision)

A keep as a record, B keep N days or anonymise, C erase with the customer and do not carry.

| # | Decision | Today | Your option | N days if B | Proposal |
|---|---|---|---|---|---|
| 1 | Offer made | C | | | C (no change) |
| 2 | Offer declined | C, not carried | | | B, 30 days, marker only |
| 3 | Quote requested | A | | | A; ask whether `content` is anonymised after N years |
| 4 | Quote approved by staff | A | | | A |
| 5 | Quote approved by the customer | payments A, brief C | | | A for payment and document rows, C for the brief copy |
| 6 | Revision requested | words C (G4 gap), versions A | | | C for the words, A for versions |
| 7 | Quote declined | none | | | B only if you want it remembered (needs a new writer); otherwise C |
| 8 | Deal response | A (G9 gap) | | | B: keep response, times, ids; blank free text on erase |
| 9 | Brief confirmed | lead kept (G14 gap) | | | B per R5: clear requirements and notes, keep stage |
| 10 | Corrections | C | | | C (no change) |
| 11 | Problem status | C | | | C (no change) |
| 12 | Attempted actions | slot C; drafts G6; tool calls S | | | C for slot and drafts; tool calls: decide with Q3 |
| 13 | Facts about the business | C | | | C (no change) |
| 14 | Ideas given and feedback | C | | | C (no change) |
| 15 | Conversation flow state | S | | | C (blank on erase); a new change, needs a test |
| 16 | Move history | C | | | C (no change) |
| 17 | Reminder and marketing consent | table A, brief C | | | A for the table (rule exists); decide how a new chat learns an earlier opt-out |

## 7. Unresolved conflicts and assumptions

**Conflicts**
1. **Q1 versus B7 and the offer-once rule.** CLAUDE.md fixes the offer as made once for the whole set. A
   cross-chat decline window changes offer cadence beyond B7's 8 messages (`pi/box.py:16`). Not checked
   against the platform spec Book 5 text. [PROPOSED] only.
2. **Q2 and the box history.** Today box transitions are erased (`pi/brain_erase.py:89-125`). The code
   comment reads ST12 as "the box history follows the retention rules; here only the box's own words and
   history go, never a quote" (`pi/brain_erase.py:11-13`), so erasing them matches that comment. What is
   open is the retention period itself (`App.D-4`, rule-coverage:84) and whether transitions count as
   evidence for P-6. I did not read ST12 in the PDF.
3. **Corrections to earlier documents of mine** (stated here, not silently changed):
   (a) the audit and consolidated:155 say a decline leaves no durable row; a transition row with reason
   "owner declined" exists when the box feature is on (`pi/box_lifecycle.py:272-273`); (b) the audit says
   flow state is reset with the conversation; the erase update does not touch it (`pi/brain_erase.py:259-270`);
   (c) the audit cites the `approval` brief key at `pi/decisions.py:776`; the key is written at `:780`;
   (d) the audit lists 15 types, its table has 16, and this review adds a 17th (consent); (e) the audit's
   `box_declined_at` omitted the second decline key `box_declined_at_pi` (`pi/box_lifecycle.py:37`).
4. **Consolidated C3 (one memory design).** Option B of the audit (new `memory_block` keys) would also feed
   `slot_carry.ASKED_KEYS`, which is built from `FACTS` (`pi/slot_carry.py:37`; `pi/memory_block.py:48`).
5. **Consolidated C2 and P-1.** P-1 keeps `requirement` rows out of `memory_block.load()` (P-1 document);
   a decision marker in such rows would not be read by pi unless a reader is added. Not re-verified here.
6. **Consolidated C7 and R1 to R6.** Quote and payment retention is open (erase-gap doc R1 to R6), and
   `App.D-4` is a human decision (rule-coverage:84). The ledger design cannot be final before both.
7. **Possible consent gap [INFERRED].** Reminder follow-ups read the per-conversation brief key
   (`pi/followups.py:192,272,366`; `pi/brain_followups.py:105,236,435`; `pi/check_in.py:148,200`), while the
   customer-level table is read by campaigns (`pi_saas/campaigns.py:193-196`) and the inbox view
   (`pi/inbox_routes.py:387-395`). I did not find a path that copies an earlier opt-out into a new
   conversation's brief, and erase replaces the brief (`pi/brain_erase.py:265`). Not tested; the owner should
   confirm before this is called a defect.

**Assumptions**
- Sensitivity labels are my classification, not legal advice.
- "Kept on purpose" statements are read from code comments, not from the specification PDFs.
- Behaviour of `box_offer` off workspaces was read from `enabled_for` (`pi/box_lifecycle.py:47-48,257`), not run.
- Lines I did not re-read in this task and took from my earlier audit: `pi/brain_docs.py:1004`,
  `pi/brain_docs_models.py:7-9`, the `pi_staff_requests` model, the writer of `log_offer`.

## 8. Dependencies and outstanding decisions

- **Depends on:** R1 to R6 (erase-gap doc), `App.D-4`, the P-1/P-4 shared memory design (consolidated:150),
  FT-02 (Part 19 wording; not touched), S6-a and B2a `tried` (roadmap:74,76), P-6 (roadmap:172).
- **Needs from you:** the section 6 table; Q1 to Q4; whether `pi_tool_calls` and flow state are in scope for
  erase work; whether the consent finding (section 7, item 7) should be verified by a test.
- No database was queried; no row counts or real data appear here.
