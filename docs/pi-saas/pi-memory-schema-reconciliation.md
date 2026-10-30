# One memory design: P-1, D2, D3/S6 and P-4 reconciled (documentation only)

Status: PROPOSAL for owner review, 2026-10-30. **No migration, SQL file or code exists.** Migration `0053` stays
reserved to lane U. Everything labelled "D2 AMENDMENT" changes something the owner approved (D2: constraints, tried and
cause as JSONB columns on `pi_problems`, one migration; D3: S6-a reuses `memory_block`, no new table).

Resolves conflicts C1, C2, C3 and C12 of `pi-p1-p5-consolidated-review.md`. Inputs: `pi-p1-schema-review.md`
(`02970b2`), `pi-fast-track-plan.md` (D2, D3, FT-B2a, FT-S6), `pi-decision-records-audit.md` (`7ad1df9`).

Read for this document, from the worktree at `cc462c5` (= `origin/main`): `memory_block.py` (whole file),
`slot_carry.py` (whole file), `reply_gates.known_in_record` (lines 238-256), `constitution.REASK_FIELDS` and its R-MEM-02
use (lines ~877-983), the `PiMemory` model (`models.py:441-462`). I did not re-read `problems.py` (the P-1 review
did) or the FT-02 commits (`pi/s-ft02`, still changing). Nothing was run.

## 1. Facts found in the code that decide the design

1. **`memory_block.load()` reads only kinds `context` and `preference`** (`memory_block.py:226`), and only keys in
   `FACT_CAP` for `context` rows (line 236). The business-peer query reads only kind `context` (line 257). A `requirement`
   row is therefore invisible to today's reader and never reaches the 700-character block. The `PiMemory` CHECK
   already allows `requirement` (`models.py:455`), so no migration is needed for it.
2. **Adding a key to `FACTS` has five side effects** (this is the "ASKED_KEYS side effect" of the P-4 audit, in full):
   - `slot_carry.ASKED_KEYS = frozenset(FACTS keys)` (`slot_carry.py:37`): a new key becomes a carried "asked fact".
   - `build()` puts every `FACTS` key into the prompt block in priority order (`memory_block.py:183-185`), so it competes
     for the 700 characters.
   - `refresh()` writes every `FACTS` key that `profile` holds as a `context` row (lines 327-329).
   - `merge_profile()` fills it from the conversation profile (lines 201-205).
   - `memory_reply()` indexes `LABELS[k]` and `LABELS_UR[k]` for every key in `facts_of(block)` (lines 429-430): a `FACTS`
     key with no label is a `KeyError` in the answer to "what do you remember about me?".
3. **`asked_facts` is written from `memory_block.asked_keys(reply)`** (service_conversation.py:6553-6555), which matches a
   reply's question against `constitution.REASK_FIELDS`. Only keys with a pattern there can ever be "asked"; the R-MEM-02
   lint (constitution.py ~954-983) reads `profile.get(field) or block.get(field)` for those same keys only.
4. **`known_in_record` (reply_gates.py:238) reads only the problem record's `missing` list** (`since`, `how_often`). It
   cannot see a budget, a staff count, a tool or a workflow; that is the gap S6 closes.
5. **`erase_customer` deletes every `pi_memories` row of the customer, scoped to tenant and environment, with no kind
   filter** (`brain_erase.py:202-206`, `delete(PiMemory).where(*mine(PiMemory), PiMemory.customer_id == customer_id)`).
   A new row of any kind is erased with the customer. A `pi_problems` column is erased with its row
   (`brain_erase.py:182-186`; revisions `175-181`, links `164-174`). **Correction to the P-1 review and to my first
   commit of this file:** they said `erase_customer` calls `memory_block.forget`. In `brain_erase.py` I found no such
   call (the delete above is inline); `memory_block.forget` (`memory_block.py:396-405`) is an identical delete that I
   did not find a caller for in `brain_erase.py` (a search of the rest of `app/` timed out, so other callers are
   unverified). The behaviour claimed (all kinds erased) is confirmed by lines 202-206.
6. **`refresh()` archives the older value and prunes archived history to `MAX_ARCHIVED = 30` per customer, counted across
   all kinds** (lines 380-393). Requirement history would share that 30 with facts and preferences.
7. **A memory row is `key: value`, content at most 500 characters, key `[a-z_]{2,20}`** (`ROW`, line 106; model line 461).
   `clean_value()` takes its cap from `FACT_CAP` and defaults to 40 for an unknown key (line 121), so every new key must
   be added to a cap table or its value is cut to 40 characters.

## 2. The design (store by store)

| Store | Holds | Why this store | Reader |
|---|---|---|---|
| **A. `pi_problems`, four new nullable columns** | per problem: `constraints` (JSONB), `tried` (JSONB list), `cause` (JSONB), `expected_outcome` (Text 300) | these facts belong to one problem; each problem can differ | `problems.noted_context()` (compact strings, `missing` gains `budget`, `cause` only when unsaid) |
| **B. `pi_memories`, kind `requirement`** | per customer or business: `workflows`, `roles`, `systems`, `budget`; existing `FACTS` keys (`current_tools`, `goal`, `team_size`) stay where they are | one value for the whole business; a correction archives the old one; erase already covers it | new `memory_block.load_requirements()` (section 3), **not** `load()` |
| **C. derived at read time** | the requirement sheet and its completeness score (FT-REQ, `requirements.py`) | nothing stored twice, nothing to drift | `requirements.sheet()` merges A (problem value) over B (business value) |
| **D. conversation brief** | `wants` (Part 19, per conversation, as reported by its author; I did not read it), `asked_facts`, `closed_slots`, decision keys | per-conversation working state | unchanged; only `slot_carry` copies, and only what it copies today |

Problem value wins over business value for budget and staff (D2 AMENDMENT A2 below); the sheet records which one it used.

## 3. The reader S6 / `fact_ask` needs, without widening the prompt block

- **Do not add the new keys to `FACTS`.** Add a separate `REQUIREMENT_FACTS` tuple (key, cap, level) beside it, with its
  own labels. `FACTS`, `FACT_CAP`, `BUSINESS_KEYS`, `build()`, `facts_of()`, `merge_profile()`, `refresh()` and
  `memory_reply()` keep their current inputs, so the 700-character block, the `ASKED_KEYS` carry and the label lookup are
  untouched.
- **New `load_requirements(session, scope, conversation, customer) -> dict[str, str]`** in `memory_block.py`: same scope
  filter (tenant, environment, customer, `status == 'active'`), `kind == 'requirement'`, a limit, parse with `parse_row`,
  business-level keys also read from opted-in peers of the same business (the same join `load()` uses for kind `context`,
  with `kind == 'requirement'`). Same error discipline as `load_safely`: a savepoint, and on any error an empty dict.
- **Its output goes to a new context key, `requirements_known`, not into `what_i_know`.** It reaches the model only as
  part of the FT-REQ sheet (its own cap, proposed 600 characters, D2 AMENDMENT A5), and only when `fact_ask` is on or the
  sheet is asked for. The existing 700-character block is not changed.
- **Gate:** a new `reply_gates.known_requirement(reply, requirements, noted)` in the style of `known_in_record`: when the
  reply asks about a budget, staff, tool, workflow or role and `requirements_known` (or the problem columns) already
  holds it, the reply is sent back with "it asks X, but you already hold it: use it". Conservative in the same way:
  no record, no block. Opt-in under the same `response_rules.brain` rule (read only when exactly `true`).
- **Write path:** `refresh()` gets a sibling `refresh_requirements()` (also `begin_nested`), writing `requirement` rows
  from the extractor's note. It uses the same `clean_value` rules (redact first, roles not names, phone/email rejected)
  with the cap taken from `REQUIREMENT_FACTS`.
- **Honesty (R-PRIV-06):** `memory_reply()` must also list the `requirement` rows ("what do you remember about me?"),
  otherwise pi keeps facts it will not tell. This is part of S6, with its own label table (EN and Roman Urdu; Arabic
  follows the existing `fallback (listed)` pattern).

## 4. ASKED_KEYS: exact handling

| Question | Decision |
|---|---|
| Do requirement keys enter `slot_carry.ASKED_KEYS`? | **No by default.** `ASKED_KEYS` stays `FACTS` keys. A requirement question that was asked and left unanswered would then not be carried to the next chat, which is today's behaviour for everything else. |
| If the owner wants unanswered requirement questions carried too | add a second frozenset `REQUIREMENT_ASKED` in `slot_carry.py` and matching patterns in `constitution` (a new `REASK_REQUIREMENT` tuple, not an edit of `REASK_FIELDS`), then make `carried()` accept the union. Costs one more regex table and tests; **D2 AMENDMENT A4**. |
| `memory_block.asked_keys(reply)` | unchanged (reads `REASK_FIELDS`). A sibling `asked_requirement_keys(reply)` reads `REASK_REQUIREMENT` only if A4 is approved. |
| R-MEM-02 lint | unchanged; the new gate is `known_requirement`, a separate function, so the existing lint cannot regress. |
| `memory_reply` label lookup | unchanged for `FACTS`; the requirement labels live in their own table, so no `KeyError` path is created. |

## 5. Carry across conversations

- Store A and B rows belong to the customer, so every later conversation reads them with no copy and no staleness
  (unlike a brief copy). This is the S6 acceptance ("not asked again after 30 messages or in a new chat").
- `slot_carry` stays as it is (closed slots 30 days, asked facts 2 days, marked `carried`, made once). It does not copy
  requirements, decisions or wants.
- **Decisions (P-4):** the gap found is `declines`, `box_declined_at`, `offer_declined`, `approval` and `revision_requested`
  dying with the conversation. See section 6.
- **`wants` (Part 19):** stay per conversation in the brief. S6 may later promote a durable want to a `requirement` row
  (key `wants`, cap 160). Not in this migration; **D2 AMENDMENT A8**.

## 6. How the P-4 decision-record options fit

| Option | Fits this design? | Reason |
|---|---|---|
| **A** read-only function over `pi_box_transitions`, `pi_solution_boxes`, `pi_brain_documents`, `pi_brain_payments` | **Yes. Recommended first.** No store, no migration, no erase change (box and transitions are erased, documents and payments are kept under today's policy). Lives next to `brain_docs.open_quote`, lane S (`box*.py`). | gives "declined an offer on date", "approved quote Q-nnnn". Cannot hold a decision that no row records (a decline is only a transition reason; a declined quote only flow state). |
| **B** decision rows in `pi_memories` | **No.** The only kinds the CHECK allows are `preference`, `requirement`, `context`: `context` would enter the 700-character block and `ASKED_KEYS`; `requirement` would mix needs with decisions; a new kind needs a CHECK change, which is a second migration. | decisions are not "the person's own words" (the module's stated purpose). |
| **C** `slot_carry` copies `declines` and `box_declined_at` | **Yes, small, for the one behaviour gap** (`declines` drives idea behaviour at `solution_context.py:83`, `solution_ask.py:406`). Counter and date only, a window, erased with the customer (it copies into a conversation). | a copy can go stale; keep it to those two keys. |
| **D** new ledger table (0054) | **Not supported.** Not needed for A and C; a second migration; needs its own erase and retention design. | stay unreserved until the owner asks for one cross-feature immutable ledger. |

Proposed: A plus C. The reason string that A needs for an unrecorded decline is a code change to an existing transition
(`box_lifecycle`, lane S), not a column. **Retention is the owner's call (D2 AMENDMENT A9):** documents and payments are
kept on erase; memory rows and brief copies are erased. A decision shown from kept documents therefore survives an erase,
a decision copied by C does not. R1 to R6 in `pi-erase-gaps-g1-g14.md` decide which policy applies.

## 7. Erase, retention, tenant, size, rollback

| Store | Erase today | Retention proposal | Tenant and environment | Size caps |
|---|---|---|---|---|
| A. problem columns | row deleted by `erase_customer` (`brain_erase.py:182-186`) | with the problem; revision diff keeps the old value (P-1 review) | row's `tenant_id`, `environment_id`, scoped customer FK; reads filter on both | `constraints`: 4 keys, 160 chars, 5 `cannot_change`; `tried`: 5 x (160 + 160); `cause` text 300 plus 3 x 120 evidence; `expected_outcome` 300 |
| B. `requirement` rows | all kinds deleted by `erase_customer` (`brain_erase.py:202-206`) | until erase (R1 to R6 may add a window); history pruned at 30 archived per customer | `WorkspaceRow` scope; peers only for business keys of opted-in contacts, same tenant and environment | `workflows` 240, `roles` 160, `systems` 160, `budget` 80 (content 500 incl. key); at most 40 active rows per customer |
| C. derived sheet | nothing stored | none | built from A and B only | proposed 600 characters in the prompt |
| D. brief | brief set to erased; copies erased with every conversation | per conversation | conversation scope | as today |

- **Archived-history cap (D2 AMENDMENT A6):** today 30 per customer across kinds. Proposal: count `requirement` rows
  separately so a long requirement history does not push facts out (a code change in `_prune_history`, no migration).
- **Tests the design needs (first, seen failing):** the P-1 list (sections 5.1-5.9 of the P-1 review) plus:
  `load()` still ignores `requirement` rows; the 700-character block is byte-identical with requirement rows present;
  `ASKED_KEYS` is unchanged; `memory_reply` lists requirement rows and raises no `KeyError`; `known_requirement` is
  silent with no record and with another customer's record; two-tenant (same phone, two workspaces); peer sharing only
  for business keys; erase leaves zero rows of every kind; archived-history cap per kind.
- **Rollback:** (1) flags first: the extractor fields, `refresh_requirements`, `known_requirement` and the sheet sit
  behind `response_rules.brain` flags read only when exactly `true`; turning them off needs no data change.
  (2) code revert: `requirement` rows stay in `pi_memories` but nothing reads them (`load()` filters kinds), and erase
  still removes them. (3) the migration's `downgrade` drops exactly the four columns (their data is lost; nothing else
  depends on them). (4) no real-database change without the owner pasting `alembic upgrade --sql` into Neon.

## 8. The single migration `0053` (outline only, nothing written)

`0053_pi_problem_requirements`, `down_revision = "0052_pi_open_items"`, additive, lane U only; run `alembic heads` first.
`upgrade`: `op.add_column("pi_problems", ...)` four times: `constraints` JSONB nullable, `tried` JSONB nullable, `cause`
JSONB nullable, `expected_outcome` Text nullable; no index, no constraint, no data change. `downgrade`: four
`op.drop_column` in reverse. **Nothing for store B** (the CHECK already allows `requirement`), **nothing for decisions**
(option A and C are code), **nothing for the sheet**. A second migration would be forced only by: a new memory `kind`
(CHECK change), option D, or a typed, queryable constraint column. None is in this design.

## 9. Field-by-field final table and ownership

Ownership: **U** understanding (`problem_models.py`, `problems.py`, `problem_extract.py`, `memory_block.py`, `slots.py`,
`slot_carry.py`, `requirements.py`, migration 0053); **S** solutions (`box*.py`, `brain_docs*.py`, `system_ask.py`);
**E** evaluation (`evalkit/**`); **R** isolation and erase tests. `reply_gates.py` and `constitution.py` are not assigned
to a lane in the plan: **owner to assign** (hot-file rule: a small hunk, rebased by the integrator).

| Field | Store | Key or column | Shape and cap | Owner | Carry | Erase | Status |
|---|---|---|---|---|---|---|---|
| constraints (budget, staff, deadline, cannot-change) | A | `pi_problems.constraints` | JSONB, 4 keys, 160 chars | U | customer-level (row) | row | proposal (A1, A2) |
| tried (what, outcome) | A | `pi_problems.tried` | JSONB list, 5 x 160+160 | U | customer-level | row | proposal (A1) |
| cause (status, evidence) | A | `pi_problems.cause` | JSONB; `confirmed` needs `owner_said` | U | customer-level | row | proposal (A1: `source` dropped) |
| expected outcome | A | `pi_problems.expected_outcome` | Text 300 | U | customer-level | row | proposal (A1: added) |
| workflows | B | `workflows` | 240, business level | U | customer, shared with opted-in peers | `forget` | proposal (A3, A7) |
| roles (entities, never names) | B | `roles` | 160, person level, not shared | U | customer | `forget` | proposal (A3) |
| existing systems | B | `systems` (and `current_tools`, unchanged) | 160 | U | customer, business level | `forget` | proposal (A3, A7) |
| business-wide budget | B | `budget` (and `team_size`, unchanged) | 80, business level | U | customer, business level | `forget` | proposal (A2, A7) |
| requirement sheet, completeness score | C | derived (`requirements.py`) | 600 chars in the prompt | U (reader), S (documents consume it) | derived | none | planned (FT-REQ) |
| reader for `requirement` rows | code | `memory_block.load_requirements`, `refresh_requirements` | n/a | U | n/a | n/a | proposal (A3, A4) |
| gate `known_requirement` | code | `reply_gates.py` | n/a | owner to assign | n/a | n/a | proposal |
| decision history (declined, approved) | code | read-only function (P-4 option A) | ids, states, dates only | S | derived from kept and erased records | per source table | proposal (A9) |
| `declines`, `box_declined_at` carry | brief | `slot_carry` (option C) | counter and date | U | window | erased with conversations | proposal (A9) |
| labelled requirements in cases | evalkit | conversation case format (P-2, P-3, FT-A3) | n/a | E | n/a | n/a | proposal |
| erase and isolation tests | tests | two-tenant, erase completeness | n/a | R | n/a | n/a | planned (FT-E2) |

## 10. Items that still need an owner decision

| Label | Decision | Recommendation |
|---|---|---|
| **D2 AMENDMENT A1** | four columns (add `expected_outcome`, drop `cause.source`) instead of D2's three | approve |
| **D2 AMENDMENT A2** | budget and staff business-wide in memory rows with a problem-level override, or on every problem (D2 as written, duplication) | business-wide with override |
| **D2 AMENDMENT A3** | new keys as kind `requirement` rows with their own reader (not in `FACTS`, not in the 700-character block); this amends D3's "reuse `memory_block` rows with more keys" | approve; a separate `REQUIREMENT_FACTS` |
| **D2 AMENDMENT A4** | carry unanswered requirement questions across chats (a second `ASKED` set and `REASK_REQUIREMENT` patterns) | not now; keep `ASKED_KEYS` as is |
| **D2 AMENDMENT A5** | a separate prompt cap for the requirement sheet (proposed 600 characters on top of the existing prompt, which is already large) | approve a cap, measured on a dry run first |
| **D2 AMENDMENT A6** | archived-history cap counted per kind | approve |
| **D2 AMENDMENT A7** | business-level `workflows`, `systems`, `budget` shared with opted-in contacts of the same business (today's rule for business keys) or kept per person | per person if unsure; sharing is a privacy choice |
| **D2 AMENDMENT A8** | `wants` stay per conversation, or promote durable ones to a `requirement` row | stay per conversation for now |
| **D2 AMENDMENT A9** | decisions: P-4 option A plus C only; retention of a decision follows the document policy (kept on erase) or the memory policy (erased); option D never or later | A plus C; policy after R1 to R6 |
| **A10** | `memory_reply` lists `requirement` rows so pi tells what it keeps | yes (R-PRIV-06) |
| **A11** | who owns `reply_gates.py` and `constitution.py` hunks for `known_requirement` | assign to lane U with integrator rebase |
| **A12** | which droppable fields (P-1 review section 4) to omit in the first version | keep all except the helper fields |

## 11. Conflicts resolved, and what remains

- **C1 (P-1 versus D2):** resolved as A1 to A3; the owner still decides. **C2 (P-1's `requirement` rows versus S6 needing a
  reader):** resolved by `load_requirements`, `requirements_known` and `known_requirement` (section 3). **C3 (one memory
  design for P-1, S6, P-4):** this document; decision records stay out of `pi_memories` (section 6). **C12 (FT-02 first):**
  unchanged: lane U edits `problems.py` and `problem_extract.py` only after FT-02 is integrated; `memory_block.py` is not
  touched by FT-02 as far as the reported file lists show, but the extractor schema (shared by B2a and S6) is, so S6 follows
  B2a as D3 says. B2a has not started.
- **Remaining:** A1 to A12; the retention decisions R1 to R6; the prompt-size effect of A5; FT-02 must be integrated.
- **Limits:** read from the code at `cc462c5`; nothing queried or run; the Part 19 `wants` behaviour is from its author's
  description, not read; caps are proposals, not measured.

## 12. Check against the approved master roadmap (`pi-fast-track-plan.md`, sections 1 to 8)

Status words: **APPROVED** = the owner approved it as written (D1 to D4, the lane table, the acceptance criteria of
FT-B2a, FT-S6 and FT-REQ, and the P-1 to P-6 approval with its conditions). **PROPOSED** = this document, needs the
owner. No existing acceptance criterion is changed; where this document differs from approved text it is a labelled
amendment (A1 to A12, section 10).

| Roadmap item | Approved text | Status in this design | Check |
|---|---|---|---|
| D2 | constraints, tried and cause as JSONB columns on `pi_problems`, one migration 0053 | APPROVED as written | A1 (four columns, `cause.source` dropped, `expected_outcome` added), A2 (budget, staff business-wide) are **PROPOSED amendments**; if the owner declines both, D2 stands unchanged and section 8 is the same |
| D3 | S6-a: reuse `memory_block` rows with more keys and code-side extraction, no new table | APPROVED as written | A3 is a **PROPOSED amendment** (separate `REQUIREMENT_FACTS`, kind `requirement`, own reader, not `FACTS`); no new table either way |
| FT-S6 acceptance | with `fact_ask` on, a fact said in message 1 is not asked again after 30 messages or in a new chat; two-tenant, erase, newer value archives the older, redactor applied, block cap kept | APPROVED, unchanged | met by design: customer-level rows (section 5), `refresh_requirements` archives the older value (`memory_block.py:354-356` pattern), `clean_value` redaction (`memory_block.py:118-136`), 700-character block untouched (`memory_block.py:44`) |
| FT-S6 affected files | `memory_block.py`, `reply_gates.py`, `service_conversation.py` (small hunk) | APPROVED | same files; `reply_gates.py` has no lane in the plan's lane table (section 1): flagged as A11 |
| FT-S6 "code-side extraction of a stated number or tool" | D3 wording | APPROVED | **Open:** section 3 writes requirement rows from the extractor's note. D3 says code-side extraction. Assumption: both are allowed (the note supplies the value, a code-side check supplies a stated number or tool). Not decided: see C-A below |
| FT-B2a acceptance | 9 labelled constraints recorded at 90% on Development; a cause is `confirmed` only when the owner said it; old rows unchanged; migration up and down; two-tenant and erase tests | APPROVED, unchanged | met by the P-1 schema (store A) and section 7 tests; `expected_outcome` and the new business-level keys have **no labelled data** (conflict C11 of the consolidated review), so B2a's criterion does not cover them |
| FT-B2b | `understood_count` becomes a quality score; write `goal_verb` | APPROVED | untouched here; it reads store A columns |
| FT-REQ | read-only sheet per customer, completeness score, top 3 missing, ask only the top 1; files `requirements.py`, `brain_docs.py` (hook), `think_prompt.py` (one line) | APPROVED | store C is that sheet; **cross-lane:** `brain_docs.py` belongs to lane S in the plan's lane table, so the FT-REQ hook there is a lane-S hunk |
| Lane table (section 1) | U owns `memory_block.py`, `slots.py`, `slot_carry.py`, migration 0053, `requirements.py` | APPROVED | section 9 follows it; decision history (P-4 option A) is placed in lane S (`box*.py`) |
| Hot-file rule | small hunks (about 30 lines) into `service_conversation.py`, integrator rebases | APPROVED | the reader call and the sheet hook are two small hunks there; unchanged |
| Migration rule | only lane U writes `0053`; others reserve the next number first | APPROVED | this design needs no second migration (section 8); `0054` stays unreserved |
| Critical path | FT-02 then FT-B2a, no B2a before FT-02 integrates | APPROVED | unchanged; this document is design only |
| P-1 (section 8) | workflows, entities, roles, systems, expected outcome in FT-REQ and B2; full schema reviewed before 0053 | APPROVED with conditions | this document and the P-1 review are that review; the owner has not approved the schema |
| P-2, P-3 | case format shared by P-2, P-3, FT-A3 (lane E); no verification thresholds | APPROVED with conditions | this design only needs "labelled requirements" in cases (section 9, last data row); it defines no format and no threshold |
| P-4 | read-only audit first; then a privacy-safe decision ledger; no table or 0054 | APPROVED with conditions | section 6 proposes A plus C, a derived record and a counter copy, **not a stored ledger**. Assumption: the owner's "ledger" can be satisfied by a derived read function. If a stored ledger is required, option D and migration 0054 return. PROPOSED |
| P-5 | stages need separate approval | APPROVED | no model call, spending or run in this document |
| P-6 | evidence-backed claims | APPROVED with conditions | P-6 would read the same append-only records section 6 reads (`pi_box_transitions`, documents, payments); not designed here |

## 13. Unresolved conflicts and assumptions

| # | Item | Kind | What is open |
|---|---|---|---|
| C-A | Write path for requirement rows: the extractor's note (P-1) versus code-side extraction (D3 wording) | conflict between approved D3 text and the P-1 design | choose one, or both with the code-side check winning on a stated number or tool |
| C-B | P-4 "decision ledger" versus section 6 (derived read plus counter copy, no stored ledger) | assumption | owner confirms a derived record is enough |
| C-C | `reply_gates.py` and `constitution.py` have no lane | gap in the lane table | owner assigns (A11) |
| C-D | FT-REQ's `brain_docs.py` hook is in lane S's files | cross-lane hunk | integrator rebases; lane S agrees |
| C-E | prompt size: the sheet adds about 600 characters to a prompt that already carries `spec_guidance` of tens of thousands of characters (a recorded run showed 46,096 for that key in a test log) | risk | measure on a dry run before A5 is approved |
| C-F | `wants` (Part 19) lives in the brief, per conversation, while `expected_outcome` and `goal` are durable | overlap | A8 decides; I did not read the Part 19 code |
| C-G | `refresh()` archives and prunes at 30 across kinds (`memory_block.py:380-393`), so requirement history can push facts out | behaviour change | A6 |
| C-H | erase retention for decisions (documents kept, memory erased) is undecided | open decision | R1 to R6 and A9 |
| C-I | B2a's 90% criterion covers only the 9 labelled constraints | gap | labelled cases for the new fields (lane E) before they can be accepted |
| C-J | `forget` callers outside `brain_erase.py` unverified (search timed out) | unverified | confirm with a narrower search |
| C-K | FT-02 is still changing `problem_extract.py` and `problems.py` on `pi/s-ft02` | dependency | lane U starts only after integration |
| C-L | Whether business-level rows are shared with opted-in peers (privacy) | open decision | A7 |

Assumptions made: (1) the new `requirement` keys fit the `key: value` row shape (`memory_block.py:106`, key at most 20
characters, content at most 500, `models.py:461`); (2) a `requirement` kind row never reaches `load()` or `merge_profile()`
(read from `memory_block.py:226,236,257`; true at `cc462c5`, not guaranteed if another change widens `load()`);
(3) `Customer.business_id` and `shares_with_business` are the sharing rule for the new business-level keys
(`memory_block.py:240-268`); (4) the P-1 review's column shapes are final enough to outline 0053.

## 14. Source references used (path:line, at `cc462c5` in the worktree `.cache/lanes/sch`)

Read by me for this document:
- `apps/api/app/modules/pi/memory_block.py`: `BLOCK_CHARS` 44, `MAX_ARCHIVED` 45, `FACTS` 48-59, `FACT_CAP`/`BUSINESS_KEYS`
  60-61, `LABELS`/`LABELS_UR` 63-86, `clean_value` 118-136 (cap default 40 at 121), `ROW`/`parse_row` 106/143-145,
  `build` 179-194, `facts_of` 197-198, `merge_profile` 201-205, `load` 208-286 (kinds 226, `FACT_CAP` test 236, peers 240-268,
  peer kind 257), `asked_keys` 300-309, `refresh` 312-377 (FACTS loop 327-329), `_prune_history` 380-393, `forget` 396-405,
  `memory_reply` 423-441 (label lookup 429-430), `load_safely` 458-467.
- `apps/api/app/modules/pi/slot_carry.py`: windows 30 and 2 days 30-31, `ASKED_KEYS` 37, `carried` 60-95, `carry_into` 98-127.
- `apps/api/app/modules/pi/reply_gates.py`: `known_in_record` 238-256, `fact_already_given` 212-229.
- `apps/api/app/modules/pi/constitution.py`: `REASK_FIELDS` 877ff, R-MEM-02 lint 962-983.
- `apps/api/app/modules/pi/models.py`: `PiMemory` 441-462 (CHECK kinds 455, content 461).
- `apps/api/app/modules/pi/brain_erase.py`: `erase_customer` 128ff; problems 182-186, revisions 175-181, links 164-174,
  memories 202-206.
- `apps/api/app/modules/pi/problems.py`: `noted_context` 871ff (the `missing` list begins 898).
- `apps/api/app/modules/pi/service_conversation.py` (grep only, not read in full): memory load 4032-4036, `asked_facts`
  write 6553-6555, `memory_reply` call 2132, `declines` increment 3371, `think_prompt.block` 1194.
- `apps/api/app/modules/pi/solution_context.py`: `declines` read 83, 370, 656, 713; `solution_ask.py:406`.
- `apps/api/app/modules/pi/brain_docs.py:1259` (`open_quote`, grep only).

Carried from the P-1 review and the P-4 audit, **not re-read here**: the `pi_problems` columns (`problem_models.py`),
`erase` of `pi_box_transitions` and documents kept (`brain_erase.py:287-300`), `slot_carry` call placement,
`box_lifecycle.py:272-279`, the Part 19 `wants` behaviour, and everything about `pi/s-ft02`.
