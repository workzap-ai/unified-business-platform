# P-1 schema review: the complete field set before migration 0053 is written

Status: PROPOSAL for owner review, 2026-10-30. **No migration, SQL file or code exists.** Migration `0053`
stays reserved to lane U and is not written until the owner approves this document. Read from
`origin/main` (cc462c5), migration head `0052_pi_open_items`. Everything in the "D2 AMENDMENT FOR OWNER
REVIEW" boxes changes what the owner approved as D2 (constraints, tried and cause as JSONB columns on
`pi_problems`, one migration).

## 1. What already exists (so nothing is added twice)

`pi_problems` (`problem_models.py`) already holds: `current_workaround` (Text, 400 chars),
`systems_mentioned` (JSONB list, 8 x 60), `who_notices` (200), `person_believes_cause` (String 300,
redacted), `requested_solution` (300), `scope` (JSONB: where, of_total, products, channel, people), `impact`
(JSONB: types, money_text, time_text), `frequency`, `since`, `trigger`, `source_message_ids` (JSONB),
`goal_verb` (exists, never written) and `revision`. Every changed field is stored as an old/new pair in
`pi_problem_revisions.diff`. `ProblemNote` (`problems.py:77`) and the extractor's `SimpleNote`
(`problem_extract.py`) carry a subset of these.

`pi_memories` (`models.py:441`) holds customer-level `key: value` rows (content 500 chars; kind
`preference`, `requirement` or `context`; status active or archived). `memory_block.FACTS` has 10 keys
(name, role, business_name, business_type, location, team_size, channels, current_tools, website, goal) and
the prompt block is capped at 700 characters. `load()` reads only kinds `context` and `preference`.
Business-level keys are shared between contacts of one business that opted in (`shares_with_business`).
A correction archives the old row (R-MEM-04).

Erase: `brain_erase.erase_customer` deletes `PiProblem`, its revisions, links and groups by `customer_id`
(`brain_erase.py:182-186`; revisions 175-181, links 164-174) and deletes **every** `pi_memories` row of the
customer with no kind filter (`brain_erase.py:202-206`; correction: an earlier version of this line said it calls
`memory_block.forget`, which I could not find in `brain_erase.py`; `memory_block.py:396-405` is an identical
delete). So any new column on `pi_problems` and any new
`pi_memories` row is erased with the customer without a change to `brain_erase.py`, provided a test proves it.

Consequence: several requested items already have a place. The cause, the tried-before text, the systems and
the goal exist in weaker form. The design below upgrades them instead of duplicating them.

## 2. Proposed fields (complete list; one migration)

Notation: store A = new nullable JSONB or text column on `pi_problems`; store B = `pi_memories` row of kind
`requirement` (already allowed by the table's CHECK constraint, read by no existing query, so it stays out of
the 700-character prompt block); store C = derived at read time, nothing stored.

### 2.1 Per problem (store A, four new columns, all nullable, no default needed)

| Field | Column | Shape | Written by | Redaction and scope | Carry across chats | Size cap |
|---|---|---|---|---|---|---|
| constraints | `constraints` JSONB | `{"budget": {"text": "ready, about 5 lakh", "state": "ready", "msg": "<message id>"}, "staff": {"text": "2 people", "count": 2, "msg": ...}, "deadline": {"text": "before Eid", "msg": ...}, "cannot_change": [{"text": "keep the current POS", "msg": ...}]}` | extractor (new fields) and the reply model's notes | text passes `redact`; roles not names; tenant and environment through the row's scope columns | rows belong to the customer, so every later chat of the same customer reads them | 4 keys; text 160 chars; at most 5 `cannot_change` entries |
| tried | `tried` JSONB | `[{"what": "WhatsApp group for orders", "outcome": "orders got lost", "msg": ...}]` | extractor | same | same | 5 entries; 160 + 160 chars |
| cause | `cause` JSONB | `{"text": "no stock count at closing", "status": "owner_said", "evidence": {"msgs": ["..."], "words": ["we never count at night"]}}` | extractor writes `owner_said` only when the owner said it; pi's own guess is `pi_inferred`; `confirmed` only after the owner agrees | text and evidence words redacted | same | text 300; 3 evidence words of 120 chars |
| expected outcome | `expected_outcome` Text, 300 | "orders never lost, one list for the whole team" | extractor from the owner's words; staff may edit | redacted | same | 300 |

`status` values: `pi_inferred`, `owner_said`, `confirmed` (an unsupported cause may never be `confirmed`; this
is the measurable "unsupported causes 0" criterion of FT-B2a). The existing `person_believes_cause` column
is kept unchanged (old rows, `noted_context`, prompts and summaries read it today); new writes fill both until a later
cleanup, so nothing is migrated in place.

**D2 AMENDMENT FOR OWNER REVIEW (A1):** D2 lists constraints (budget, staff, deadline, cannot-change), tried
(what, outcome) and cause (status, source, evidence). This proposal (a) adds `expected_outcome`, (b) drops
`cause.source` because it can be derived (`owner_said` and `confirmed` mean the owner; `pi_inferred`
means pi), and (c) uses `evidence.msgs` plus `evidence.words` for evidence. Four columns instead of three.

### 2.2 Per customer or business (store B, no schema change)

| Field | Key | Shape | Written by | Scope | Cap |
|---|---|---|---|---|---|
| workflows | `workflows` | `"order taking by WhatsApp; stock count at closing; weekly payroll"` (semicolon list of the owner's steps) | extractor and S6 code | per customer; business level (shared with opted-in contacts of the same business) | 240 chars |
| entities and roles | `roles` | `"owner; two cashiers; one storekeeper; accountant"` (roles only, never names) | extractor | per customer, person level (not shared) | 160 chars |
| existing systems | `current_tools` (exists in `FACTS`) and `systems` | tool names | existing path | business level | existing cap 60; the new `systems` key 160 |
| expected business outcome | `goal` (exists, 90 chars) | the owner's goal | existing path | business level | 90, unchanged |
| budget and staff, business-wide | `budget`, `team_size` (exists) | `"ready, about 5 lakh"` | extractor | business level | 80 |
| requirement sheet | none (store C) | FT-REQ builds it at read time from problems, these rows, the slots and the brief | `requirements.py` | read-only | none |

New keys (`workflows`, `roles`, `systems`, `budget`) become `pi_memories` rows with `kind = 'requirement'` and
content `key: value`; they need `memory_block` code (a small `REQUIREMENT_FACTS` table of key, cap and level, and a
`load_requirements` read), but **no migration**. A newer value archives the older (existing behaviour), the
redactor and the role rule (`clean_value`) apply, and `forget` erases them.

**D2 AMENDMENT FOR OWNER REVIEW (A2):** D2 put constraints on `pi_problems` only. Budget and staff are normally
business-wide ("budget is ready" in the Artwing chat), so repeating them on every problem drifts. Proposal: the
problem columns hold problem-scoped constraints (`cannot_change`, `deadline`, and a problem-specific budget
or staff when the owner says one); business-wide `budget` and `team_size` live as memory rows; the reader uses
the problem's value, else the business value. Fallback if the owner prefers D2 exactly: store all four constraint
keys on each problem and have the extractor copy the business-wide ones; cost is duplication.

**D2 AMENDMENT FOR OWNER REVIEW (A3):** S6-a (D3) said "reuse `memory_block` rows with more keys". This proposal
uses kind `requirement` rows for the new keys so the 700-character prompt block does not grow; `noted_context`
and a new requirements read decide what reaches the prompt.

### 2.3 Per-field checklist (applies to every field above)

| Item | Decision |
|---|---|
| Nullable and default | new columns nullable, no server default; absent means "not said" (matches `ProblemNote`: empty means not said) |
| Old rows | untouched; code treats NULL as empty; no backfill |
| Extractor schema and prompt | `SimpleNote` (extractor) and `ProblemNote` gain: `budget`, `staff`, `deadline`, `cannot_change` list, `tried` list, `cause_text` with `cause_said` boolean, `expected_outcome`; prompt gains one rule: only what they said, roles never names, a guess is never written as said. Fields stay small so the model fills them reliably (the full 30-field note failed before) |
| `noted_context` | adds a compact `constraints`, `tried` and `cause_status` per problem (short strings) and `missing` gains `budget` and `cause` only when the owner has not said them; output is unchanged when the columns are empty |
| Revision history | add the four columns to the field lists used by `_revise` (`problems.py` about lines 634-662) so a correction keeps the old value in the diff |
| Redaction | `problems.redact` on every text; entity values are roles; a number that looks like a phone or card is dropped (`memory_block.clean_value` for store B) |
| Tenant and environment | store A rows carry `tenant_id`, `environment_id` and the scoped customer foreign key; store B rows the same; reads always filter on both (existing pattern) |
| Erase | none needed in `brain_erase.py` for store A (row deleted) or store B (`forget` deletes all kinds); a test per store proves it and fails if a future table is missed (builds on FT-E2b) |
| Tests | see section 5 |

## 3. Alternatives

| Option | What | For | Against |
|---|---|---|---|
| A. All JSONB on `pi_problems` | every field, including workflows, roles, systems, budget, on each problem | one migration, one store, simple reads | per-business facts repeated on each problem and drift; a correction must be applied on N rows; roles and workflows are not problems |
| **B. Split (recommended)** | per-problem facts as four columns, per-customer facts as `requirement` memory rows, sheet derived at read time | one migration, no new table, matches D3 (no new table), erase and isolation already proven for both stores, no prompt growth | two stores to read; the reader must merge problem over business |
| C. New table `pi_requirements` | one typed row per customer with history | strong typing, longer values, easy to audit | new table, new erase code, new two-tenant and erase tests, duplicates `pi_memories`; D3 said no new table unless S6-a is not enough |

## 4. Fields that could be dropped without losing the acceptance criteria

`constraints.*.msg` and `tried.*.msg` (message ids, kept only for audit; evidence is already on the problem's
`source_message_ids`); `constraints.budget.state` and `count` (normalised helpers; free text is enough for FT-REQ);
`roles` (could be derived from `workflows` and `who_notices`); `expected_outcome` (could reuse `requested_solution`
and `goal`, at the cost of mixing "what they want built" with "what result they want"); store-B `systems` (could use
`current_tools` with a larger cap). I recommend keeping them all except the helpers if the owner wants a smaller
first schema; none needs a migration to add later, because store B needs none and store A fields live inside JSONB.

## 5. Tests (written first, seen failing)

1. A problem with each new field: write, read back, revision diff holds the old value after a correction.
2. Extractor: "budget ready hai, 2 staff, Eid se pehle" gives constraints; a guess never becomes `owner_said`; a
   third party's name becomes a role; a phone number is dropped.
3. `cause.status`: `confirmed` cannot be set without `owner_said`; unsupported cause rate on Development is 0.
4. Memory rows: `requirement` kind is not in the 700-character block and not read by `load`; newer value archives older;
   cap enforced; `PLACEHOLDER` and phone rejected.
5. Two-tenant: the same phone in two workspaces never sees the other's constraints, tried, cause or memory rows;
   control proves the test can fail.
6. Erase: `erase_customer` leaves zero `pi_problems` and zero `pi_memories` rows (all kinds) for the customer; the FT-E2b
   completeness test still passes.
7. Old-row compatibility: rows written before the migration read as empty and produce unchanged `noted_context`.
8. Migration: up and down on the disposable database, `alembic heads` shows one head, downgrade drops exactly the four columns.
9. Scripted replay and Held-out: no score falls; the 9 labelled constraints are recorded at 90% or more on Development (Held-out checked once).

## 6. Migration outline (nothing is written)

`0053_pi_problem_requirements`, `down_revision = "0052_pi_open_items"`, additive only, lane U only. `upgrade`:
`op.add_column("pi_problems", ...)` four times: `constraints` JSONB nullable, `tried` JSONB nullable, `cause` JSONB nullable,
`expected_outcome` Text nullable. No index, no constraint, no data change, no new table. `downgrade`: `op.drop_column`
four times in reverse order. The real database is migrated only by the owner pasting `alembic upgrade 0052..0053 --sql`
into the Neon SQL editor, only when the owner asks. Check `alembic heads` before writing it.

## 7. Risk of a second migration and how this design avoids it

| Risk | Avoided by |
|---|---|
| a new per-customer fact is wanted later | store B: a new `requirement` key needs code only |
| a per-problem sub-field is wanted later | it lives inside a JSONB column (no schema change); a constraint of a new type is a new JSON key |
| a cause needs more evidence fields | `cause.evidence` is an object, extendable |
| a decision ledger (P-4) | not in this migration; the P-4 audit decides whether existing records or `requirement` rows are enough; a new table (a possible 0054) would be reserved only then |
| an index for reads | reads are by customer through the existing `ix_pi_problems_customer`; no new index is needed at this size |
| a typed or queryable constraint (a report by budget) | out of scope; adding a generated column later is a separate, owner-approved migration |

## 8. Dependencies and outstanding decisions

Dependencies: FT-02 integrated (lane S's hunks in `problems.py` and `problem_extract.py`) before lane U edits those files; D2 amended;
D3 amended (kind `requirement`); the role-not-name redaction fix on FT-02 (audit finding 2); the retention decisions R1 to R6
for how long `requirement` rows live (this design adds the same retention as other `pi_memories` rows: until erase).

Owner decisions needed:
1. Approve or change A1 (four columns, `cause.source` dropped, `expected_outcome` added).
2. A2: budget and staff business-wide (recommended) or on every problem (D2 as written).
3. A3: new keys as kind `requirement` rows (recommended) or kind `context` rows inside the 700-character block.
4. Whether business-level rows (`workflows`, `systems`, `budget`) may be shared with opted-in contacts of the same business
   (existing behaviour for business keys), or kept per person.
5. Which fields from section 4 to drop in the first version.

## 9. Limitations

Read from the code at cc462c5; no database was queried and nothing was run. I did not read `agents.py` and the tool-mode memory
paths beyond a grep, so whether any other writer uses kind `requirement` rows is unverified (the grep found none in `modules/pi`).
Caps and shapes are proposals, not measured. The claim that new columns are erased with the row, and new memory rows by
`forget`, comes from reading `brain_erase.py` and `memory_block.py`; the tests above would prove it.
