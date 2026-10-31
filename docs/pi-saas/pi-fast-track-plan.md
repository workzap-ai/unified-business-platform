# pi Fast-Track Execution Plan (tracks A to G), for review

Status: PROPOSAL, 2026-10-30. Nothing here is started. Written for the owner (to approve) and for the
agents that will run the lanes. Effort is in agent-days with about plus or minus 50% error; it is an
estimate, not a measurement. Thresholds, language scope and industry criteria stay PENDING owner approval
(`pi-eval-thresholds-proposal.md`); no task below uses them as a release gate before that.

## 0. Where things stand (evidence, 30 Oct)

| Track | Done and merged | Open |
|---|---|---|
| A measure | 102 scripted cases (Held-out 60, Development 39, Regression 3), scorers, replay, coverage doc | Development smaller than Held-out; Hindi 0, Arabic 4; no scorer for constraints, relevance or cause evidence; no real-model run (key, budget) |
| B understand | B1 no-drop (opt-in), B3 eight notes, B6 S1 to S5 (extractor survives rewrite, since/cost/count carried, short repeats caught, closed slots carried, fact gate reads records) | **B2** (constraints, tried, cause source), **S6** (stated facts), B4 multilingual, B5 `other` bucket, requirements completeness (B7.3) |
| C solutions | C2 no guessed industry | C1 relevance in code, C3 six weak industries, C4 depth, C5, C6 |
| D learning | isolation test for learning surfaces | D1 verify end to end, D2 scorers into reward, D3 prompt_version, D4 |
| E engineering | unit suite green on main (7595); two-tenant test for learning; red-team round 2; erase covers conversations | memory/profile/slot two-tenant tests, erase-completeness check, RLS decision, release gates, spec sign-off |
| F/G product | nothing started | F1 audit, F2 capability map, G2 journeys, F6 tests, F8 view |
| Real case | Artwing Studios 2026-10-30: a regression test and `system_ask.py` exist **uncommitted** from another agent | land it, then extend with B2 and S6 |

Reuse, do not rebuild: `memory_block.py` (durable customer facts), `slots.py` and `slot_carry.py`,
`problem_extract.py` and its replay path, `evalkit/`, `reply_gates.py`, `brain_erase.py`,
`rule_index.json`, the two-tenant test pattern in `test_pi_learning_tenant_isolation.py`.

Known failures on main, unrelated to this plan: `test_merge_split_link_withdraw_and_rename_a_group` and
`test_the_summary_then_the_fixed_offer_with_buttons` (the second is the open X1/X2 offer decision).

## 1. Lanes, ownership and branches

Each lane works in its own git worktree on its own branch cut from `origin/main`, stages only its own
paths, and never runs `git add -A`. One integrator merges branches **fast-forward only**, one at a time,
in the order of section 3, after the gate of section 5. No force push, no history rewrite.

| Lane | Owner | Branch prefix | Owns (writes) | Reads only |
|---|---|---|---|---|
| U understanding | agent U | `pi/u-` | `problem_models.py`, `problems.py`, `problem_extract.py`, `memory_block.py`, `slots.py`, `slot_carry.py`, migration `0053`, new `requirements.py` | everything else |
| S solutions and Artwing | the agent already editing `system_ask.py` (agent S) | `pi/s-` | `system_ask.py`, `box*.py`, `solution_*.py`, `expert_advisor.py`, `idea_filter.py`, `brain_docs*.py` | `problems.py` |
| E evaluation | agent E | `pi/e-` | `evalkit/**`, `cases/*.json`, `docs/pi-saas/pi-eval*` | no production code |
| R isolation and release | agent R | `pi/r-` | new tests, `brain_erase.py` (additions only), release scripts | all |
| I industries | agent I | `pi/i-` | `industry_packs.py`, `industry_words.py`, `packs/industry/*.json`, `scripts/build_industry_packs.py` | taxonomy |
| P product audit | agent P | `pi/p-` | `docs/pi-saas/capability-map*`, later F6/G2 tests | `apps/web`, `apps/pi`, all API |

**Hot files** (`service_conversation.py` 7,800 lines, `constitution.py`, `safety.py`): any lane may add
a small hunk (about 30 lines at most, a call into its own module), but must rebase on the latest
`origin/main` immediately before merge; the integrator resolves any conflict, never the author alone.
**Migrations:** current head is `0052_pi_open_items`. Only lane U writes `0053` (B2). Anyone else needing a
migration reserves the next number in this document first and checks `alembic heads`. The real database is
migrated only by the owner pasting `alembic upgrade --sql` into Neon.

## 2. Parallel tasks (no dependency on B2; start together)

| ID | Task | Lane | Effort | Depends on | Affected files | Acceptance (measurable) |
|---|---|---|---|---|---|---|
| FT-01 | Lane guard: a script that fails when a staged file is outside the lane's paths | R | 0.5 | none | `scripts/check_lane_paths.py` (new) | staging a foreign file exits non-zero; own files pass |
| FT-02 | Land the in-flight Artwing and warm-up work: review (rule-auditor), clean-worktree verification, merge as a branch | S | 1 | none | `system_ask.py`, `box.py`, `box_signals.py`, `expert_advisor.py`, `service_conversation.py`, `test_pi_artwing_system_request.py`, commit `44f40b9` | their tests plus full unit green on the branch; the Artwing test passes; rule-auditor reports no violation of the non-negotiables |
| FT-A1 | Grow Development from 39 to 60 or more with new text; Hindi 15, Arabic 15, Urdu script 20 | E | 1.5 | none | `cases/extraction.json`, `test_pi_evalkit_heldout.py` | Development at least 60; the 63 earlier cases byte-identical; 0 messages shared with Held-out; invariants test passes |
| FT-A2 | Scorers for constraints and cause evidence, reading `expected.constraints` and `hypothesis_only` (adds only) | E | 1 | none | `evalkit/scorers.py`, tests | negative controls fail; every existing score unchanged; the 9 labelled constraints scored |
| FT-A3 | Solution relevance scorer (problem link, fact reuse, constraint fit) plus 30 scripted solution cases | E | 2 | FT-A2 | `evalkit/`, new cases | agreement with the `grader` agent at least 85% on 20 hand-labelled samples before it is used for anything else |
| FT-E2a | Two-tenant tests for memory block, business profile, slots and carry, problem book, map | R | 1 | none | `tests/integration/test_pi_isolation_core.py` | each surface has a control and a leak check; any leak is a G3 critical fault: stop and alert |
| FT-E2b | Erase completeness: a test that lists every model with `customer_id` or `conversation_id` and fails if `brain_erase` misses one | R | 1 | none | test plus `brain_erase.py` (additions) | the test fails when a table is added without erase, passes today |
| FT-C3 | Fix the 6 weak industries (catering, FMCG, pharma manufacturing, solar, sports retail, used cars) and 8 probes per industry | I | 2 | none | `industry_packs.py`, `industry_words.py`, `build_industry_packs.py`, packs | the 6 pick on at least 2 of 3 probes; the 211-industry audit does not regress |
| FT-C6 | Vet stored pack ideas with the reply linter (R-SOL-03/04/09) | I | 1 | none | tests, pack data | 0 hard violations in all packs, or each listed with a reviewer |
| FT-D3 | `prompt_version` covers hardcoded prompts, pack hashes and operator guidance | S | 1 | none | `learning_audit.py` | changing any of those changes the version; unit test |
| FT-F1 | Dashboard audit, read only: 22 areas, each classified implemented, partial, broken, disconnected, duplicated or missing | P | 4 | none | `docs/pi-saas/capability-map.md` | every area has file:line evidence; confirmed defects kept apart from ideas |
| FT-E5 | Spec reading log rows for v1.5, platform-spec, platform-spec-1 | R | 2 | none | `pi-rule-coverage.md` | each spec has rows with rule, enforcement point, test, status |

## 3. Sequential tasks and the critical path

Critical path (bold): **FT-02 → FT-B2a → (FT-B2b, FT-S6) → FT-REQ → FT-C1 → FT-REPLAY → FT-E4**.
About 15 working days if FT-B2b and FT-S6 run side by side, FT-REPLAY waits for the owner, and nothing
slips; the Artwing extension and B4 sit beside it.

| ID | Task | Lane | Effort | Depends on | Affected files | Acceptance (measurable) |
|---|---|---|---|---|---|---|
| **FT-B2a** | Problem record gets `constraints` (budget, staff, deadline, cannot-change), `tried` (what, outcome) and a cause with status, source and evidence: nullable JSONB columns, migration 0053, extractor schema and prompt, `noted_context` | U | 2 | FT-02, owner decision D2 | `problem_models.py`, `problems.py`, `problem_extract.py`, `0053`, tests | the 9 labelled Held-out constraints recorded at 90% or more on Development (Held-out checked once); a cause is "confirmed" only when the owner said it (unsupported causes 0 on every split); old rows unchanged; migration up and down on the disposable database; two-tenant and erase tests added |
| **FT-B2b** | `understood_count` becomes a quality score (what, size, since, cause, constraints present and grounded); write `goal_verb` | U | 1.5 | FT-B2a | `problems.py`, `problem_models.py`, tests | score table tests; golden and red-team suites unchanged |
| **FT-S6** | Stated-facts ledger, option S6-a: reuse `memory_block` rows with more keys and code-side extraction of a stated number or tool, no new table | U | 3 | FT-B2a (shares the extractor schema), owner decision D3 | `memory_block.py`, `reply_gates.py`, `service_conversation.py` (small hunk), tests | with `fact_ask` on, a fact said in message 1 is not asked again after 30 messages or in a new chat; two-tenant, erase, newer value archives the older, redactor applied, block cap kept |
| **FT-REQ** | Requirements completeness: a read-only requirement sheet per customer (business, problem and outcome, figures, since and how often, budget, staff and deadline, tools, tried, missing) and a completeness score | U | 3 | FT-B2b, FT-S6 | new `requirements.py`, `brain_docs.py` (hook), `think_prompt.py` (one line), tests | the Artwing transcript: all 8 modules present in the sheet; the sheet names the top 3 missing items; pi asks only the top 1; completeness reported on Held-out (target set by the owner) |
| **FT-C1** | Relevance in code: score each idea (link to a stated problem, fact reuse, constraint fit, minus generic); a violated confirmed constraint rejects the idea whatever its score; "no idea" is a valid result | S | 3 | FT-B2a, FT-A3 | `idea_filter.py`, `expert_advisor.py`, tests | FT-A3 relevance score above the recorded baseline on Development and confirmed once on Held-out; 0 hard violations; no idea quota filled |
| FT-ART2 | Artwing extension: "budget is ready" and the cannot-change lines enter the solution; a system request with several modules becomes one Solution Box with a section per module | S | 2 | FT-02, FT-B2a, FT-REQ | `system_ask.py`, `box_doc.py`, `brain_docs.py`, tests | the Artwing test: 8 modules each in the document; the "can Workzap do all this" question is read as R3 and answered; the ask is not forgotten next turn; no "those are all the ideas" dead end |
| **FT-REPLAY** | Real-model sample, 30 calls first | E | 0.5 plus cost | FT-A1, FT-A3, approved thresholds, **owner: key and budget** | `evalkit/`, report | T1 to T11 measured per language and industry cell; cells below their minimum reported "not yet measured" |
| FT-B4 | One multilingual cue module (English, Roman Urdu, Urdu, Hindi, Arabic, Persian, French, Spanish) | U | 5 | **owner approval**, FT-B2 and FT-S6 merged (hot files `problems.py`, `warmup.py`, `dial_signals.py`, `taxonomy.py`) | those files | per-language recall on Development not below today's; "10 nahi, 100" style corrections in each language |
| FT-C4 | Depth beyond 2+2 (pack `ask_first`, care, build ideas, neighbours, overlays) | I | 8 | **owner approval**, FT-C1, FT-C3, FT-A3 | packs, `solution_ideas.py` | relevance not below FT-C1 on every industry cell with enough cases; care sections marked for human review |
| FT-D1 | Verify the learning loop end to end (freeze, canary, rollback, versioning) and feed A-scores into reward | E | 3 | FT-A3 validated | `learning_*.py` tests | rollback and freeze tests; no reward before scorer agreement is shown |
| FT-F2 | Capability map v1 and prioritised backlog | P | 2 | FT-F1 | docs | one deduplicated backlog with severity, evidence and effort |
| FT-G2 | Journey tests (customer, quote, order, billing, finance; member, role, permission) as candidates | P | 3 | FT-F1 | `tests/integration/` | each journey checks UI/API, DB, permission and audit; a failing one is first reproduced before it is called a defect |
| **FT-E4** | Release gates: golden, red-team round 2, scripted 211x3 replay, old-versus-new on saved chats (disposable copy), Workzap canary plan, rollback rehearsal | R | 3 | all of the above, owner approvals | scripts, docs | no drop on Regression or Held-out, per language and industry; safety metrics unchanged; rollback rehearsed |

## 4. What blocks overall progress

1. **FT-02** (the in-flight Artwing work is uncommitted in the shared tree and touches the hot file B2 also touches).
2. **Owner decisions D1 to D3** (below) before FT-B2a.
3. **FT-B2a** itself: C1, REQ and ART2 all need constraints.
4. **Key and budget** for FT-REPLAY: without it nothing about real model quality can be claimed.
5. **Thresholds approval**: without it no release gate exists.

## 5. Minimum checks before any branch is merged

1. Full unit suite on the branch: 0 failures, and no more tests failing than on `origin/main`.
2. Targeted integration tests for every area touched, on the disposable database
   (`. scripts/pi-test-env.sh`, never `apps/api/.env`); a failing test is shown to fail on `origin/main`
   too before it is called unrelated.
3. Every new test written first and seen failing.
4. `ruff check`, `ruff format`, `mypy` on the files touched.
5. Isolation: a two-tenant test with a control for any new stored data.
6. Erase: any new table, column or brief key is covered by `brain_erase` and a test.
7. `rule-auditor` on the diff against the non-negotiables; `redaction-checker` for anything learnable.
8. Evalkit scripted report: no drop on Regression or Held-out.
9. Migration: up and down on the disposable database, `alembic heads` is a single head.
10. Diff review: only the lane's paths, no secrets, no unrelated hunks; verified on a clean worktree of
    `origin/main` with only the branch's changes.

Security stop rule: a confirmed tenant, privacy or security fault stops the lane, keeps the evidence, and
is reported to the owner at once (G3); nothing is changed in production by any agent.

## 6. Decisions needed from the owner

| # | Decision | Recommendation |
|---|---|---|
| D1 | Merge policy: one integrator, fast-forward only, in the order above | yes |
| D2 | B2 field set: constraints (budget, staff, deadline, cannot-change), tried (what, outcome), cause (status, source, evidence) as JSONB columns on `pi_problems` | yes, one migration `0053`. Amendment A1 (four columns: `cause.source` dropped, `expected_outcome` added; evidence is `msgs` plus `words`) approved by the owner delegating recommended decisions, 2026-10-31. A2 (business-wide budget and staff) stays with S6, not B2a |
| D3 | S6 as S6-a (reuse `memory_block`, no new table) first; a new table only if S6-a is not enough | S6-a |
| D4 | Approve B4 and C4 to start after B2/S6/C1 merge | yes, later |
| D5 | Thresholds S1 to S7, T1 to T11, language scope, industry standard | approve or change |
| D6 | OpenAI key and a budget for the 30-call sample | approve a small cap |
| D7 | Offer wording X1/X2 (Solution Box or document offer) | decide; it closes a failing test |
| D8 | Postgres row-level security yes or no | decide before FT-E4 |

## 7. Running state (2026-10-30, Wave 1 integrated at cc462c5)

Approved: D1 (one integrator, fast-forward only), D2 (B2 fields, one migration 0053), D3 (S6-a), D4 (B4 and
C4 after B2/S6/C1 merge). Pending for separate review: D5, D7, D8 (proposal documents are prepared on a
separate branch; nothing is decided). D6: Stage 1 only (30 calls, USD 0.50), no key created or used; the
runner stays unmerged on `pi/e-d6-runner` until the owner approves model and prices.

Integrated into `origin/main` (fast-forward only, gate: full unit suite 7670 passed, 2 xfailed, 0 failed;
isolation integration test 6 passed, disposable database):

| Task | Commit |
|---|---|
| Lane E: Development 39 -> 69, constraint scorer | 39ffc06, 7ae1a4c |
| FT-01 lane guard | ea5cb4c |
| FT-E2a two-tenant isolation | 6a4e4b1 |
| FT-E2b erase completeness (14 gaps recorded) | dcc8c19 |
| FT-C6 pack-idea vetting (58 allowlisted) | 9dffa1c |
| FT-C3 weak-industry probes | be203dc |
| FT-F1 capability map | cc462c5 |

Still blocked: FT-02 / Part 19 waits for the session owner-os-4c (`pi/s-ft02`); B2a (lane U, migration
0053) starts only after their `problems.py` and `problem_extract.py` hunks are merged. Lane worktrees live
under `.cache/lanes/` (ignored by git). Commit 44f40b9 is not reviewed or approved and is not part of any
branch.

Test recipe for any lane (same shell, never piped): `. "$MAIN/scripts/pi-test-env.sh"`, then pytest from
the lane's `apps/api` with `$MAIN/.venv/Scripts/python.exe`. Integration tests share one disposable
database, so each run holds `mkdir $MAIN/.cache/test.lock` and removes it afterwards. Unit tests need
neither.

## 8. Owner-approved additions P-1 to P-6 (2026-10-30); Roadmap A to G stays the master

Approved as mandatory acceptance requirements, with conditions. Nothing below is started; no API call,
spending, production change or push to a shared branch is authorised by this approval. Status words:
**planned** (task exists), **implemented** (merged), **scripted-tested** (automated tests, no model),
**real-model-verified** (measured on a real model). Today nothing in P-1 to P-6 is real-model-verified.

| ID | Task | Lane | Depends on | Acceptance | Tests | Status |
|---|---|---|---|---|---|---|
| P-1 | FT-SCHEMA: complete schema review (owner sees it before 0053 is written); FT-REQ and B2 carry workflows, entities (roles only, never third-party names), roles, existing systems, expected outcome | U | FT-02 integrated; owner D2 amended | one reviewed schema document; one migration 0053 (up and down on the disposable DB, single head); old rows unchanged; no field duplicated in two stores | extractor schema tests, two-tenant, erase, role-not-name redaction | planned |
| P-2 | FT-A4: scorers for repetition, redundant question, requirement preservation, creativity | E | FT-A2, FT-A3; hand labels | creativity used for nothing until 85% agreement with human labels on 20 or more samples; scripted results labelled "scripted", never "AI quality" | negative controls fail; labelled-sample agreement test | planned |
| P-3 | FT-A5: plan-completeness scorer (modules, steps, dependencies, next action); cases per industry | E, I | D5 (industry criteria); FT-A3 | an industry is "verified" only with the D5 minimum of representative cases and its acceptance criteria passed; otherwise "not yet measured" | scorer controls; per-industry count test | planned |
| P-4 | FT-S7a read-only audit of deal, quote and conversation records; then FT-S7b privacy-safe decision ledger | U, S | S7a: none (read-only). S7b: S7a result, S6-a, erase decisions R1 to R6 | S7a: a table of what each record already holds. S7b: reuse existing records or `memory_block` first; a new table or migration only if S7a proves it necessary and the owner approves | two-tenant, erase, retention, redaction | planned (S7a not started) |
| P-5 | Staged real-model plan: Stage 1 approved (extractor, Development, 30 calls, USD 0.50, model and key pending); Stage 2 and Stage 3 each need their own model verification, pricing, cap, scope and explicit run approval | E | D5, D6, grader agreement | proposal documents per stage, no run before approval | runner tests (no network) | Stage 1 runner scripted-tested, not run; Stages 2 and 3 planned (proposals only) |
| P-6 | FT-X1: evidence-backed claims: no "done", "sent", "approved" or "booked" unless a record shows it; outcome check after delivery | S | FT-02; capability-map B1 (denied actions audit); after-payment records | the linter and a gate block a completion claim with no record; a test per claim type | final-text lint, two-tenant | planned |

### Conflicts and open questions found while mapping (to resolve before implementation)

1. **P-1 versus D2.** D2 approved constraints, tried and cause only. P-1 adds workflows, entities, systems
   and expected outcome. Some of these are per business, not per problem. Proposal: per problem (on
   `pi_problems`): constraints, tried, cause, expected outcome; per customer: workflows, roles, systems
   through S6-a (`memory_block`) and the FT-REQ sheet, no new table. The owner reviews the full schema first.
2. **Entities versus "roles, never third-party names".** Entities are stored as roles only; the
   redaction and role-conversion fix on FT-02 (audit finding 2) must land first.
3. **P-4 versus D3 (no new table).** The ledger must reuse deal and quote records or `memory_block`
   unless the audit proves otherwise; a new migration (0054) is reserved only then.
4. **P-4 and erase.** The ledger cannot ship before the retention decisions R1 to R6 and the G10
   share-link fix, or it adds a fifteenth erase gap.
5. **P-6 versus Part 19 wording.** "starts the quote" and "the quote will cover" are claims; the FT-02 fix
   changes them to staff-review wording. P-6 must not be built on the old wording.
6. **P-6 evidence source.** Denied actions are not audited (B1); the evidence for "done" must come from
   existing records, otherwise P-6 can only block claims, not prove them.
7. **P-2 labels.** The 85% test needs human-labelled samples; someone must label them (owner or a named
   reviewer). The `grader` agent is a model, so it is not independent human truth.
8. **P-3 versus D5.** "Sufficient representative cases" is undefined until D5 is approved; Held-out has
   no industry with 10 cases.
9. **P-5.** `gpt-4o-mini` is removed on 2027-01-14; the Stage 1 model needs your choice; Stages 2 and 3 have
   no budget or scope yet.
10. **Hot files.** P-6 and FT-REQ touch `service_conversation.py` and the linter; they follow FT-02 and
    rebase on the integrated Part 19 hunks. Migration 0053 stays reserved to lane U.

### Revised execution sequence

1. **Now:** FT-02 blockers fixed by owner-os-49 (R3 offers only; final-text lint; redact then truncate and
   roles; no problem words in the signed link, erase invalidates links; staff-review wording), then unit,
   integration and rule-auditor gates, then fast-forward. B2a stays blocked until then.
2. **In parallel, no code dependency on B2 or FT-02:** FT-S7a read-only record audit; FT-A4 and FT-A5
   scorer design (lane E, scripted only); the Stage 2 and Stage 3 proposal documents; FT-REQ schema review
   document (P-1). Erase fixes wait for retention decisions.
3. **Owner reviews:** the P-1 schema; D5, D7, D8; erase retention R1 to R6; D6 model.
4. **Then:** B2a (migration 0053 from the reviewed schema) -> B2b and S6 -> FT-REQ -> FT-C1 -> FT-ART2 ->
   FT-S7b -> FT-X1.
5. **Real-model evidence** (Stage 1, then 2 and 3 as separately approved) -> FT-E4 release gates ->
   Workzap canary. Final acceptance: all six requirements work in real customer scenarios.

## 9. Implementation backlog: Q-1 to Q-11 added (owner approval 2026-10-30, with boundaries)

Approved into the backlog. Roadmap A to G stays the master. No push, deployment, production migration or
external API cost without separate approval. FT-02 (sixth commit) stays the immediate priority. Status:
**planned** unless stated; nothing below is real-model-verified.

| ID | Task | Owner lane | Depends on | Ready now? | Measurable acceptance (proposed, owner may amend) | Boundary from the approval |
|---|---|---|---|---|---|---|
| Q-1 | State (stated, assumed, unknown, recommended) on every fact | U | P-1 schema review decision, FT-02 | no | a fact never shows `recommended` as `stated`; unsupported cause confirmed = 0 on every split | reconcile with P-1 and 0053; schema amendment presented, never silent |
| Q-2 | Rank missing information by effect on the solution | U | FT-REQ, B2a | no | asked question is the top-ranked missing item in the labelled cases; 0 questions that do not change the recommendation | impact on the recommended solution, not checklist completion |
| Q-3 | Root-cause quality criteria and labelled causes | E | FT-A2 (merged), P-2 labels | partly (criteria and labelled cases are scripted work) | agreement with human labels meets the P-2 method before use | must improve solution quality, not add fields |
| Q-4 | Options comparison in the plan format | S | FT-02, P-3 Q1 decision | no | each solution document compares at least two real options with benefit, cost source, limit, risk; reviewer approves | after the offer and the owner's yes; cost from staff, never priced by pi |
| Q-5 | Blueprint schema (entities, APIs, automation, dashboards, security, phases, risks, success criteria) | S | FT-02, P-3 Q1, P-1 reconciliation | no | blueprint completeness scored on plan cases; reviewer sign-off | reconciled with P-1 and 0053 before implementation |
| Q-6 | Verify `open_items.py` carry across chats | U | none | **yes** | a test shows unresolved questions and next steps carry to a new chat of the same customer and tenant, and are erased with the customer | preserve privacy, tenant isolation and erase rules |
| Q-7 | Contradiction detection against the stored record | U | B2a, Q-1 | no | a new statement that contradicts a stored fact produces one clarification, not an overwrite, on labelled cases | preserve privacy, tenant isolation and erase rules |
| Q-8 | Level 3: approved actions executed and verified, progress reported | S, owner scope | FT-02, P-4 decisions, P-6 | architecture and planning only | an action record exists before any "done" claim; every action has an approval and a rollback | no autonomous external actions, payments, bookings, messages, production changes or irreversible actions |
| Q-9 | Runtime pre-presentation self-check | S | FT-02, P-6, FT-C1 | no | the check flags a seeded missing requirement, constraint violation and unsupported claim in 100% of scripted negatives; false positive rate on positives stays under the owner's limit | measurable criteria required |
| Q-10 | Actionability and user-satisfaction measures | E | P-2, P-5 | no | each measure has a definition, a labelled sample and an agreement result; satisfaction comes from a real signal, not a model | measurable criteria required |
| Q-11 | End-to-end scenarios for nine industries | E, I | case format decision, D5, P-5 approval | no | at least the owner's minimum of realistic scenarios per industry (booking, rental, e-commerce, SaaS, wedding and banquet, healthcare, education, logistics, agriculture), each reviewed by an independent human | real-model calls need separate explicit cost approval |

### Dependency-ready work started in this round (approved tasks, no dependency on FT-02 or B2a)
- **FT-D3** (lane S files `learning_audit.py` only): `prompt_version` covers hardcoded prompts, pack hashes and operator guidance. Unit tests first, no database.
- **Q-6** (lane U, tests first, no production change in hot files): open-items carry audit with tests.
- **Not started, waiting on a decision:** FT-A3 (relevance scorer and 30 scripted solution cases) needs the case-format decision (CF1, CF4, CF5); B2a and everything marked "no" waits for FT-02.
