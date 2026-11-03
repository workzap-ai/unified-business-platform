# Consolidated owner review: P-1 to P-5 (2026-10-30)

Status: FOR OWNER REVIEW. Nothing here is approved or implemented. No migration, model call, spending, push
or merge. Roadmap A to G stays the master. FT-02 stays blocked and B2a has not started.

Sources: the five documents committed on their own branches (base `origin/main` cc462c5, docs only):
P-1 `02970b2`, P-2 `b2ca620`, P-3 `c95afbf`, P-4 `7ad1df9`, P-5 `ddaead5`. Each commit and its changed
paths were checked by me. I read the P-1 document's opening sections myself; the rest of this review
restates the authors' reports of their documents, so check a figure against its document before relying on it.

## 0. State of each item (the four levels kept apart)

| Item | Documented | Implemented | Scripted-tested | Real-model-verified |
|---|---|---|---|---|
| P-1 schema | yes (`pi-p1-schema-review.md`) | no | no | no |
| P-2 scorers | yes (design) | no | no | no |
| P-3 plan scorer | yes (design) | no | no | no |
| P-4 decision audit | yes (read-only audit, 15 decision types) | no | no | no |
| P-5 stage 2 and 3 | yes (two proposals, prices read from provider pages) | no | no (Stage 1 runner only: 47 tests, unrun) | no |

## 1. P-1: proposed schema and D2/D3 amendments

- **Reuse first.** `pi_problems` already holds `current_workaround`, `systems_mentioned`, `who_notices`,
  `person_believes_cause`, `requested_solution`, `scope`, `impact`, `source_message_ids` and an unused
  `goal_verb`; `memory_block` has `current_tools`, `team_size`, `goal`. The design upgrades these.
- **Per problem (four new nullable columns on `pi_problems`):** `constraints` (JSONB: budget, staff,
  deadline, cannot-change), `tried` (JSONB list, 5 entries, what and outcome), `cause` (JSONB: text, status
  `pi_inferred`/`owner_said`/`confirmed`, evidence message ids and words; an unsupported cause may never be
  `confirmed`), `expected_outcome` (Text, 300).
- **Per customer (no schema change):** workflows, roles (never third-party names), systems and budget as
  `pi_memories` rows of kind `requirement`. The requirement sheet is derived at read time.
- **One migration (0053), no new table.** Erase needs no `brain_erase.py` change (a test proves it).
- **D2 amendment (A1):** add `expected_outcome`; drop `cause.source` (derivable from status); four columns
  instead of three.
- **Amendment 2:** budget and staff business-wide in memory rows with a problem-level override (fallback:
  D2 exactly as written, with duplication).
- **Amendment 3:** kind `requirement` for the new memory rows, so the 700-character prompt block does not grow.
- **D3 effect:** S6-a still reuses `memory_block`; the new keys are `requirement` rows, not `FACTS` keys.
- **Rejected:** all-JSONB on `pi_problems` (duplicated business facts drift); a new `pi_requirements` table
  (new erase and isolation cost; D3 said no new table).
- **Needs from you:** the three amendments, whether business-level rows are shared with opted-in contacts
  of the same business (today's behaviour for business keys), and which droppable fields (section 4 of the
  document) to drop.

## 2. P-2: conversation-quality scorers, sample size, human labels

- **Gap:** `evalkit` scores one extraction and never sees pi's replies. None of the four scorers can run on
  today's 132 cases. A conversation case format is proposed (owner and pi turns, a record snapshot per
  turn, labelled requirements, answered facts, legitimate re-asks).
- **Scorers:** repetition (deterministic, reuses `slots.same_question`); redundant question (slot-based,
  reuses `known_in_record`; an unrecognised slot is "unclassified", never "not redundant"); requirement
  preservation (record, summary and solution text; weakest sink is the headline; a violated constraint is
  reported separately); creativity (deterministic caps for restating the owner or pack ideas, plus a 0 to 2
  grader rubric, never judged by the model that produced the reply; scripted runs get no creativity score).
- **Languages (from code, not measured):** en and roman_ur strong; ur and ar partial; hi weak.
- **Sample size (author's Wilson-interval arithmetic):** 20 labels cannot prove 85% (20 of 20 gives a lower
  bound of about 84%). Proposal: pilot of 20, then 60 (54 of 60 gives about 80% to 95%), at least 10 per
  language.
- **Human labels:** two independent labellers plus an adjudicator; label sheet; exact agreement primary,
  weighted kappa secondary; below 85% the judge is not used and the rubric changes, not the threshold.
- **Needs from you:** approve the case format; the sample size; name two labellers and an adjudicator;
  confirm 85% means exact agreement on the 3-point scale; a judge model other than the producer's, with its
  price, before any judge run; a Hindi tokenisation approach; whether P-1's new fields count as requirements.

## 3. P-3: solution format and industry coverage

- **What exists:** the Solution Box and older solution document store modules, phases, problem coverage and
  order of work. They do not store implementation steps, build-level dependencies, roles or a next action
  (only a loose `needs` list).
- **Two layers:** layer A (10 checks on what exists today, mostly language-independent) and layer B (steps,
  dependencies, roles, next action, constraints) which is specified only and starts only if you approve
  extending the plan format. Wording would stay "would", because of today's rules against dates, promises
  and "will".
- **Coverage today:** `evalkit/cases/` has only extraction cases; no plan cases exist; the 30 scripted
  solution cases of FT-A3 are not built. 89 industries appear in those cases (68 with one case, 20 with
  three, one with four, from the D5 proposal; not re-counted). None has 10, so every industry is "not yet
  measured". The 211-industry CSV records detection and stored text (stored 211 of 211, identified on every
  probe 179, retrieved on a probe 207), not plan quality; nothing shows an industry as verified.
- **No thresholds or minimum counts are set**, pending D5; the case-type and count questions are a list for D5.
- **Needs from you:** Q1 (extend the plan format); the ten D5 questions; who writes the expected module
  sets and who reviews care text for regulated trades.

## 4. P-4: decision persistence, retention and erase

- **No ledger exists.** Decisions live in the brief and flow state, customer-level tables and deal-flow tables.
- **Lost on a new chat:** `declines`, `box_declined_at`, `offer_declined`, `approval`, `revision_requested`
  (only `slot_carry`'s closed slots and asked facts carry). `declines` changes idea behaviour
  (`solution_context.py:83`, `solution_ask.py:406`), so a returning decliner looks new.
- **A decline is not durable:** the Box returns to collecting leaving a transition row with a fixed reason; a
  declined quote leaves only flow state.
- **Evidence already exists and is append-only:** `pi_box_transitions`, `pi_brain_documents` (`approved_by`,
  `approved_at`), `pi_brain_payments` (`confirmed_by`).
- **Erase:** documents and payments are kept on erase by design (R1 to R6 open). Free text missed by erase:
  `pi_documents.message_text` and `response_note` (G9), `sales_leads` (G14), `customer_activities` (G12).
  Tenant scoping looked consistent in the paths read.
- **Options (proposals):** A read-only function over existing records; B new `memory_block` keys (warning:
  `FACTS` also feeds `slot_carry.ASKED_KEYS`); C extend `slot_carry` to copy a few brief keys; D a new table
  (migration 0054; not proved necessary, not approved).
- **Needs from you:** may pi remember a decline across chats and for how long; do decision records follow the
  document policy (kept on erase) or the memory policy (erased); whether you ever want option D; may the
  quote's revision wording be remembered across chats.
- **Limits:** where the "brief confirmed" flag lives, whether `content`/`changes` pass the redactor, and the
  table behind `raise_decision_request` were inferred, not confirmed.

## 5. P-5: models, verified pricing, call estimates, hard caps

Prices are USD per 1M tokens, read from OpenAI's pricing and deprecations pages on 2026-10-30 through a
summarising fetch; re-check on your dashboard.

| Model | In | Cached | Out | Status |
|---|---|---|---|---|
| `gpt-4o-mini` | 0.15 | 0.075 | 0.60 | shutdown 2027-01-14; replacement `gpt-6-luna` |
| `gpt-6-luna` | 0.10 | 0.01 | 0.50 | no shutdown note found |
| `gpt-5.6-luna` | 0.20 | 0.02 | 1.20 | no shutdown note found |
| `gpt-5.4-mini` | 0.75 | 0.075 | 4.50 | no shutdown note found |
| `gpt-5.4` | 2.50 | 0.25 | 15.00 | not on the deprecations page |

Repo defaults: `router` (extraction and judge) `gpt-4o-mini`; `pi_brain` (replies) `gpt-5.4-mini`.

- **Stage 1 (approved, unrun):** 30 calls, USD 0.50 cap; worst case USD 0.0384 on `gpt-4o-mini`.
- **Stage 2 (extractor on Held-out once):** 63 calls (60 Held-out plus 3 Regression). Worst case and proposed
  hard cap: `gpt-4o-mini` USD 0.0824 / 0.10; `gpt-6-luna` 0.0644 / 0.10; `gpt-5.6-luna` 0.1477 / 0.20;
  `gpt-5.4-mini` 0.5539 / 0.60 (at USD 0.50 only 56 calls fit; reduce calls, never raise the cap).
  Held-out has hi 0, ar 4, ur 8: those stay "not yet measured".
- **Stage 3 (real reply pipeline over short conversations; owner messages scripted, replies real):** a
  worst-case turn is 7 calls and about USD 0.27 (typical about 0.11).

| Variant | Conversations x turns | Worst case | Hard cap | Max calls |
|---|---|---|---|---|
| Minimal | 6 x 3 | USD 4.86 | 5.00 | 126 |
| Lower | 10 x 4 | USD 10.80 | 11.00 | 280 |
| Full | 20 x 6 | USD 32.39 | 33.00 (not recommended first) | 840 |

- **Grading:** the `grader` agent reads saved transcripts afterwards, from a different vendor than the
  generator; an optional `gpt-5.4` API grader is about USD 0.0525 per conversation worst case. Creativity and
  depth stay unscored until the 85% test passes. No pass/fail thresholds (D5 pending).
- **Needs from you:** the Stage 1 and 2 extractor model and the router model after 2027-01-14; confirm the
  Stage 3 generator is `gpt-5.4-mini`; the Stage 3 variant and cap; the labelling method.
- **Unverified:** the figures above came through a summarising fetch; absence from the deprecations page is
  not a guarantee; whether your key can use each model is untested (the documents give a `curl` check);
  `gpt-6-luna` parameter support is unknown; Stage 3 prompt sizes are partly assumptions, so its caps need a
  measured dry run before approval.

## 6. Conflicts with the approved Roadmap A to G (and between the proposals)

| # | Conflict | Where | Proposed resolution (needs your decision) |
|---|---|---|---|
| C1 | P-1 changes approved D2 (adds `expected_outcome`, drops `cause.source`, splits budget/staff to memory rows) | D2 | decide amendments A1 to A3, or keep D2 as written |
| C2 | P-1 keeps `requirement` rows out of `memory_block.load()`, but S6/FT-S6 needs stated facts readable by `fact_ask` ("not asked again after 30 messages") | D3, FT-S6, P-1 | give S6 its own reader for `requirement` rows; do not widen the 700-character block |
| C3 | P-4 options B and C touch `memory_block.FACTS` / `slot_carry`, which feed `ASKED_KEYS`; P-1 also writes `memory_block`-family rows | D3, P-1, P-4 | one memory design for P-1 and P-4, decided together; no second parallel store |
| C4 | P-2 introduces a conversation case format; FT-A3 plans its own 30 scripted solution cases; P-3 needs plan cases | FT-A3, lane E | one case format for P-2, P-3 and FT-A3, owned by lane E |
| C5 | P-3 layer B (steps, dependencies, roles, next action) changes the plan format owned by lane S, and meets today's rules against dates, promises and "will"; a reviewer approves every solution document | lane S, FT-ART2, non-negotiables | roadmap addition for lane S after FT-02; wording stays "would"; reviewer gate unchanged |
| C6 | P-3 "verified industry" needs D5 criteria; roadmap goal is 211 verified | D5, FT-E4 | no verification claims until D5 |
| C7 | P-4 decision records versus erase: documents and payments are kept on erase by design; R1 to R6 open; new ledger must not add an erase gap | R1 to R6, G1 to G15 | decide the retention policy first; ledger design follows it |
| C8 | P-6 evidence needs P-4's append-only tables; a decline and a declined quote leave no durable row today | FT-X1, P-4 | P-6 can only prove what existing records show; adding a reason string to existing transitions needs a separate approved change |
| C9 | Stage 3 costs up to USD 5 to 33 and needs a provider-level spend guard (new code) and sealed Held-out conversation cases; approved D6 covers Stage 1 only (USD 0.50) | D6, FT-REPLAY (0.5 day) | FT-REPLAY effort and scope are understated for Stage 3; separate approval per stage; Stage 3 depends on the P-2 case format and labelled samples |
| C10 | `gpt-4o-mini` is removed on 2027-01-14 and is the production default for `router` | roadmap has no model-migration task | candidate roadmap addition: production model migration, with its own verification and approval (not in P-1 to P-6) |
| C11 | B2a acceptance labels only 9 constraints; P-1's `expected_outcome`, workflows and roles have no labelled data | FT-B2a | add labelled cases (lane E) before B2a's acceptance can cover them |
| C12 | P-1 and P-4 both need `problems.py` and `problem_extract.py` after FT-02; the FT-02 fix owns the role-not-name redaction P-1 depends on | FT-02, B2a | order unchanged: FT-02 fixed, verified and integrated first; B2a stays blocked |
| C13 | Hindi has 0 Held-out cases and a weak cue bank; B4 (multilingual) is approved only after B2, S6, C1 merge | D4, P-2, P-3 | Hindi stays "not yet measured" until B4 and new cases |
| C14 | Migration numbering: P-1 uses one 0053; P-4 option D would need 0054 | lane U, D3 | 0054 not approved; reserve only if P-4 proves a table is needed |

## 7. Decisions needed, in dependency order

1. Retention (R1 to R6) and the P-4 questions: decline memory, document-versus-memory policy, option D.
2. One memory design for P-1 and P-4 (C2, C3); then the P-1 amendments A1 to A3 and the droppable fields.
3. D5 thresholds and the industry criteria (unblocks P-3 coverage and the P-2 and P-5 pass/fail).
4. P-2 method: case format, sample size, labellers, judge model, Hindi approach.
5. P-3 Q1: extend the plan format.
6. P-5: Stage 1 and 2 model, router model after 2027-01-14, Stage 3 generator, variant and cap; each stage
   needs its own explicit run approval after a dry run.

Nothing runs, merges or is pushed until the relevant decisions are approved. FT-02: `pi/s-ft02` is at
`4caa0e5` with four unfixed blockers, so B2a stays blocked.
