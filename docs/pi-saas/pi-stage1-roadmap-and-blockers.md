# pi Stage 1: roadmap, dependencies, owner decisions, branch actions

Status: PROPOSAL for owner review, 2026-10-31, branch `pi/stage1-architecture` (origin/main `954441c4`). Documentation only. FACT = read in git or files this session; INFERENCE = my reasoning. I ran no test. Companion documents: `pi-memory-architecture.md`, `pi-memory-gap-analysis.md`, `pi-memory-entities-and-lifecycle.md`, `pi-industry-matrix.md`.

## 1. Dependency map across the lanes

Commits are branch tips observed this session by `git rev-parse`. `pi/ps-flow` moved while I worked (`ad59e5bc`, `a07fe1e0`, `1653b510`); `1653b510` is the last I saw.

| Lane | Tip | Provides (FACT from commit subject or file read) | Needs | Blocks | State |
|---|---|---|---|---|---|
| PS-0 baseline | `b1ea97b6` | baseline numbers, case files, evalkit | none | every accuracy claim (measurement) | docs and cases, not in main |
| L1 extraction wiring | `07a96679` | worked attempts stored as worked; extraction fields | L1-7a in main (`767b14c4`, merged) | PS-5, constraints M3 | 9 commits ahead of main, carried by ps-flow |
| L2-1 hard gate | `b3f3944a` | limits as rules in en/ur/ar/hi, staff caps | B2a columns (main, `0053`) | M3, PS-5, option ranking | 4 ahead, carried by ps-flow |
| L2-2 root cause | `97dedb39` | root-cause scorer | none | PS-7 hypotheses scoring | in main |
| L2-3 options record | `ff445e00` | options record, "without a fee" handling | L2-1 | blueprint, PS-3 | 5 ahead, carried by ps-flow |
| PS-3 idea relevance | `4c3eb77e` | tried outcome decides relevance | FT-A3 (main) | idea filter | 3 ahead |
| PS-4 blueprint | `f9b15bae` | blueprint builder; main has isolated version via `954441c4` | L2-3 | documents, M6 | later fix unmerged |
| PS-5 unknown resolution | `09b8f812` | the one question that settles unknown options | L2-1 | owner-limit capture | 28 ahead |
| PS-6 scenario suite | `9822b246` | 32 scripted journeys, flow traceability doc | ps-flow | independent verification | merge reverted on ps-flow (FACT `git log`); traceability doc needs correction |
| PS-7 problem graph | `d1a33810` | evidence-only edges, layers, hypotheses | L1, B2a | M5 persistence | on ps-flow `1653b510` used for wording only (`graph_voice.py`) |
| PS-8 context memory | `822ee103` | read-only context bundle | B2a, `0053` | one reader (D2), M7, M9, M10 | called on ps-flow brain turns |
| PS-9 language script | `66b18c96` | per-message language and script | none | multilingual memory, RLANG09 | called on ps-flow `1653b510` (`service_conversation.py:1646`); no stored `current_language` |
| PS-10 self review | `8f4a33d0` | 14 of 16 review checks (plan statement) | PS-9 | pre-send guard | called on ps-flow |
| ps-flow | `1653b510` | integration of the above, SR-13/SR-16 guard | the above | everything live | 88 commits ahead, unaudited |
| Safety (gap 3, gap 4) | `b12a4cba` | lexicon wave 5, first-person self-harm grammar | native-speaker review | safety claims | 12 ahead |
| Level 3 (Q-8, P-6) | `56c478d1`, `856c63cc` | controlled-execution scope; evidence claims design | approvals, security gate | M6 outcomes, execution | design plus scoped code, not merged |
| Erase (G1-G10, FT-E2b) | `438e0c16` (merged), `60b1fa66` | erase through G10; completeness test | owner decisions G11-G14, R1 | every new table | partly merged |
| Stage 1 sibling lanes | `954441c4` (both, no commits yet when I looked) | spec extraction, traceability | none | requirement matrix | in progress elsewhere |

INFERENCE on the critical path: ps-flow audit and merge decision, then the memory contract and reader consolidation (D1, D2), then the additive migrations, then retrieval metrics. Nothing in Stage 2 memory work should land in `service_conversation.py` or `runtime.py` except through the flow lead.

## 2. Phased implementation roadmap (Stage 2, starts only after owner approval of Stage 1)

Acceptance means executed tests plus measured evidence; a prompt line, a row or a screen is not acceptance. Thresholds marked OWNER are set by the owner before measuring.

| Phase | Work | Measurable acceptance | Needs owner approval of |
|---|---|---|---|
| P0 Baseline | audit and merge decision for ps-flow; correct plan items listed in section 5; spec matrix gaps by severity | independent audit report per lane; unit suite green on the disposable database, number reported with the command | merge of live-path work |
| P1 Contract and reader | one write contract function; `context_memory.build_context` as the single reader; `memory_block` renders from the bundle; shared knowledge-state vocabulary | fixture test: old and new block agree; erase and export read the same bundle; zero direct writes to `pi_memories` outside the contract (search test) | none (no DDL) |
| P2 Additive migrations A | E4 link columns, E5 fact history, E6a `problem_uuid`, E8 constraint JSON shape | fresh-database upgrade and downgrade on the disposable database; model/migration parity; PS-7 edge persisted once and idempotently with quote and basis; withdrawal and expiry scenarios | migration numbers and SQL file |
| P3 Documents | E1 extracts and segments, readers return page/sheet/section segments | question about a stored file answered with name and page or sheet; unreadable PDF handled; cross-tenant read returns nothing; erase removes segments; redaction test | E1 privacy review, G13 retention |
| P4 Rejections, decisions, outcomes | E3, E2 only if the gap test fails, E6b, delivered marker | scenario tests for reject-then-reverse, supersession, failed outcome recalled; PS-8 reports "implemented" only with a verified marker | delivered marker, retention table |
| P5 Retrieval | ordered path (structured, keyword, graph, validity/tenant, ranking, conflict), per-reply influence log (E7) | retrieval precision and recall on a labelled set per kind (OWNER thresholds); cross-tenant leakage = 0 (hard); latency and token cost reported | semantic search yes or no |
| P6 Transparency | explanation view, full export, corrections through the contract, deletion path from chat | export contains every table named by the completeness test; correct, withdraw and erase scenarios in en, Roman Urdu, Urdu, Arabic, Hindi | G10-G14, R1, chat deletion policy |
| P7 Learning split | knowledge learning separated from performance learning; outcome-verified only; freeze/canary/rollback kept | learning never changes safety, privacy, approval or feasibility rules (existing red-team tests plus new ones); drift check unchanged | learning scope |
| P8 Industry framework | schema 2 supplement, CI validator, 12 deepened packs, labelled cases per industry | validator green; for each deepened industry the OWNER-set number of independently labelled cases and thresholds met on sealed Held-out; matrix shows Verified only then | thresholds, case counts |
| P9 Controlled execution | Level 3 only after approval and security gate | exact-approval tests, no payment in chat, reviewer approval of every document (non-negotiables) | execution scope |

Final acceptance is the plan's 14 owner conditions (ADDENDUM A7); this roadmap does not claim any of them is met today.

## 3. Owner-decision register

| # | Decision | Options | My recommendation (INFERENCE) | Blocks | Evidence |
|---|---|---|---|---|---|
| D-1 | Approve additive migrations (E4, E5 history, E6a, E8) and numbering after `0054` | approve now / after audit | approve after P0 audit | P2 | this document set; last file `0054_payment_idempotency.py` |
| D-2 | E1 extracted-text tables | approve / defer / approve with redaction-only text | approve with redaction and a per-customer cap | P3, M1 | entities doc E1 |
| D-3 | E2 decisions ledger | derive first / build now | derive first, build only if the gap test fails | M2 | entities doc E2 |
| D-4 | pgvector and embeddings | off (keyword only) / on for knowledge only / unify memory + knowledge + learning | decide after P5 keyword baseline; if on, one embedder and index | D4, M10 | no vector column in migrations read; `0002` says optional and applied manually (unverified on Neon) |
| D-5 | Row-level security (D8) | defer / enable on tenant-scoped tables | owner decision; keep isolation tests either way | security layer | `d8-rls-security-assessment.md` on `pi/d-decision-docs` `71218948` (proposal) |
| D-6 | Erase gaps G11 to G14 and R1 | blank / keep / delete per table | follow the retention table; always delete extracted text | M8 | `pi-erase-gaps-g1-g14.md` on `pi/d-erase-gaps` `174517ab`; docstring in `brain_erase.py` |
| D-7 | Bare "ok" as a yes | not a yes (ROFFER03 v1.6:1831) / yes (classifier v1.6:3666) | not a yes (CLAUDE.md says "ok" is not a yes) | offer gate | plan A1; CLAUDE.md non-negotiables |
| D-8 | Ideas cap | 4 per conversation (RVAL02) / 8 per business (Book 5 decision 5) | 8 per business, code uses 8 | idea filter | plan A1; CLAUDE.md |
| D-9 | `ask_which_language` wording | add a rule / leave | add a rule with PS-9 | language | plan A1 |
| D-10 | "Delivered" marker and states beyond `S13_IN_BUILD` | add states / outcome table / none | outcome table E6b | M6 | `flow.py` ends at `S13_IN_BUILD`; `IMPLEMENTED_STATES=("delivered",)` |
| D-11 | 18.2 fallback template versus "no template path" | keep fixed fallback after two failed gate attempts / change | owner decision (spec conflict) | pre-send guard | plan A1, `service_conversation.py` fallback |
| D-12 | Proposal "never reported delivered" rule | add rule / leave | add | M6 | plan A1 |
| D-13 | Staff edits count as owner-confirmed? | yes (owner role only) / never | owner-role only | conflict policy | entities doc section 9 |
| D-14 | Chat "delete everything" automatic erase | automatic with confirmation / staff only | automatic with a confirmation step and audit | M8 | plan A1 |
| D-15 | Retention periods for decisions, outcomes, extracts | per P-4 table | per table | P3, P4 | `pi-decision-retention-review.md` on `pi/s-s7a-audit` `169e4763` |
| D-16 | Evaluation thresholds and case counts per industry | D5 numbers / own | owner sets before measuring | P8, matrix | `d5-threshold-proposal.md` (PROPOSAL) |
| D-17 | Real-model runs and embedding spend | allow capped / not | ask per run (memory: sweeps spend the owner's balance) | verification | memory note |

## 4. Branch actions: preserve, correct, merge, audit (every `pi/*` branch, exact tip)

Legend: PRESERVE = keep as is (already in `origin/main` or reference only). CORRECT = known defect to fix before use. MERGE = ready to merge after review, docs or via ps-flow. AUDIT = live-path or security change not independently reviewed. "In main" = `git merge-base --is-ancestor` against origin/main `954441c4`. Tips read at the end of this session.

| branch | commit | ahead of origin/main | in main | action | reason |
|---|---|---|---|---|---|
| pi/bl-04-denied-audit | 69842cd9 | 0 | yes | PRESERVE | in origin/main; plan lists BL-04 as independently audited PASS (plan FACT, not re-verified here) |
| pi/bl-05-payment-idempotency | b25e04ce | 0 | yes | PRESERVE | in origin/main |
| pi/bl-15-file-audit | b10cef6f | 0 | yes | PRESERVE | in origin/main |
| pi/c-c3-weak-industries | 25c3922b | 0 | yes | PRESERVE | in origin/main |
| pi/d-decision-docs | 71218948 | 1 | no | MERGE (docs) | D5 thresholds, D7 wording, D8 RLS assessment: all PROPOSALS |
| pi/d-erase-gaps | 174517ab | 1 | no | MERGE (docs) | erase gaps G1-G14 table |
| pi/doc-fast-track | f9d6eaec | 6 | no | MERGE (docs) | roadmap section 9 (Q-1..Q-11) |
| pi/doc-spec-text | 6a4fa14e | 1 | no | PRESERVE | spec text extraction; int-3 (merged) carries the same subject; check duplicate before merging |
| pi/e-a1 | 7ae1a4c6 | 0 | yes | PRESERVE | in origin/main |
| pi/e-a1-dev-cases | de2c7123 | 0 | yes | PRESERVE | in origin/main |
| pi/e-a3-inflection | 12a9a81b | 0 | yes | PRESERVE | in origin/main; plan lists FT-A3 as independently audited PASS (plan FACT, not re-verified here) |
| pi/e-a3-relevance | 03739919 | 0 | yes | PRESERVE | in origin/main |
| pi/e-case-format | 898e0baf | 2 | no | MERGE (docs) | case format approvals CF1, CF4, CF5 |
| pi/e-d6-runner | 5dfe4562 | 3 | no | AUDIT | runner that takes a configurable model; real-model spend needs owner approval |
| pi/e-p2-scorer-design | 93e5378d | 2 | no | MERGE (docs) | design doc |
| pi/e-p3-plan-design | c95afbf4 | 1 | no | MERGE (docs) | design doc |
| pi/e-p5-stage-proposals | 6e4ad9ed | 2 | no | MERGE (docs) | design/cost doc |
| pi/e-q11-nine-industry | a8e3a961 | 0 | yes | PRESERVE | in origin/main |
| pi/e2-tenant-scope | c73cf4f4 | 0 | yes | PRESERVE | in origin/main |
| pi/e2b-tenant-scope | c73cf4f4 | 0 | yes | PRESERVE | in origin/main |
| pi/e2c-tenant-hardening | 0d9cf78a | 0 | yes | PRESERVE | in origin/main; plan lists E2c as independently audited PASS (plan FACT, not re-verified here) |
| pi/execution-board | c73cf4f4 | 0 | yes | PRESERVE | in origin/main |
| pi/f-capability-map | 724939b2 | 0 | yes | PRESERVE | in origin/main |
| pi/i-allowlist-review | c36891b9 | 1 | no | MERGE (docs) | review of 58 allowlisted pack-idea violations |
| pi/i-c3 | 5a2fc8b4 | 2 | no | AUDIT | FT-C3 probes for weak industries; compare with int-1 which has the same subject line |
| pi/int-1 | be203dc8 | 0 | yes | PRESERVE | in origin/main |
| pi/int-2 | cc462c5b | 0 | yes | PRESERVE | in origin/main |
| pi/int-3 | 001990e6 | 0 | yes | PRESERVE | in origin/main |
| pi/integ-1 | 1c14aeba | 0 | yes | PRESERVE | in origin/main |
| pi/l1-extraction-wiring | 07a96679 | 9 | no | MERGE (via ps-flow) | L1 wiring tip carried by ps-flow |
| pi/l1-multilingual-cues | 767b14c4 | 0 | yes | PRESERVE | in origin/main; plan lists L1-7a as independently audited PASS (plan FACT, not re-verified here) |
| pi/l2-hard-gate | b3f3944a | 4 | no | MERGE (via ps-flow) | L2-1 hard gate; constraint element shape extends it (M3) |
| pi/l2-options-record | ff445e00 | 5 | no | MERGE (via ps-flow) | L2-3 options record |
| pi/l2-root-cause | 97dedb39 | 0 | yes | PRESERVE | in origin/main; plan lists L2-2 as independently audited PASS (plan FACT, not re-verified here) |
| pi/l3-exec-scope | 56c478d1 | 4 | no | AUDIT | Level 3 controlled execution scope (Q-8); execution boundary, security review first |
| pi/main-release-1 | 954441c4 | 0 | yes | PRESERVE | in origin/main |
| pi/p-f1 | 9d1bbf7b | 1 | no | MERGE (docs) | capability map; int-2 carries a version |
| pi/ps-flow | 1653b510 | 88 | no | AUDIT | flow lead integration: wiring of L1/L2/PS-3/4/5/6/8/10 and pre-send guard; unaudited live path; moves (seen ad59e5bc then a07fe1e0) |
| pi/ps0-baseline | b1ea97b6 | 6 | no | PRESERVE | baseline numbers and case files used for the industry matrix counts; docs and cases only |
| pi/ps10-self-review | 8f4a33d0 | 37 | no | AUDIT | SR checks wired on ps-flow (service_conversation.py); 14 of 16 per plan |
| pi/ps2-number-word-corrections | ada8c94a | 1 | no | AUDIT | number-word figures; check overlap with L1 extraction before merge |
| pi/ps3-idea-relevance | 4c3eb77e | 3 | no | MERGE (via ps-flow) | PS-3 rounds beyond main; carried in ps-flow |
| pi/ps4-blueprint-builder | f9b15bae | 1 | no | PRESERVE | isolated builder already in origin/main via main-release-1; later fixes carried in ps-flow |
| pi/ps5-unknown-resolution | 09b8f812 | 28 | no | MERGE (via ps-flow) | live-flow PS-5; carried in ps-flow |
| pi/ps6-scenario-suite | 9822b246 | 43 | no | CORRECT | traceability doc states RLANG09 conflict C4 wrongly (RLANG09 text exists, v1.6:5495-5498 per plan A1); the 32-journey merge was reverted on ps-flow |
| pi/ps7-problem-graph | d1a33810 | 36 | no | MERGE (via ps-flow) | pure module; not wired on ps-flow; wire edges through the existing link op |
| pi/ps8-context-memory | 822ee103 | 36 | no | MERGE (via ps-flow) | read-only bundle; already called on ps-flow brain turns; becomes the single reader |
| pi/ps9-language-script | 66b18c96 | 36 | no | MERGE (via ps-flow) | LanguagePin not wired; resolves RLANG02/RLANG09 plan item |
| pi/q-blueprint-design | dc347e44 | 0 | yes | PRESERVE | in origin/main |
| pi/q-execution-design | eee52220 | 0 | yes | PRESERVE | in origin/main |
| pi/quotes-approve-permission | 14cc8da0 | 1 | no | AUDIT | permission change (quotes.approve): security review |
| pi/r-ft01 | 60b1fa66 | 3 | no | AUDIT | erase completeness test; needed as the new-table erase gate |
| pi/s-d3-prompt-version | 25c3922b | 0 | yes | PRESERVE | in origin/main |
| pi/s-ft02 | 06caaa77 | 0 | yes | PRESERVE | in origin/main |
| pi/s-ft02-eighth-draft | 2cfe248b | 0 | yes | PRESERVE | in origin/main; plan lists FT-02 as independently audited PASS (plan FACT, not re-verified here) |
| pi/s-p6-evidence-design | 856c63cc | 1 | no | PRESERVE | design doc for evidence-backed claims (P-6); input for M6 |
| pi/s-s7a-audit | 169e4763 | 2 | no | MERGE (docs) | P-4 retention review Q1-Q4 |
| pi/safety-gap3-gap4 | b12a4cba | 12 | no | AUDIT | safety lexicon wave 5: 12 commits ahead, native-speaker review needed |
| pi/sec-1-unverified-invite | f612560b | 2 | no | AUDIT | auth change (SEC-1): security review |
| pi/spec-gaps-1 | 1653b510 | 88 | no | AUDIT | contains pi/ps-flow; wires PS-9 language decision per turn (RLANG02, RLANG09) and the pre-send guard; appeared during this session, I did not read its code; if it wires language_script, the architecture doc finding that language_script has no importer holds only for ps-flow |
| pi/stage1-architecture | 954441c4 | 0 | yes | CURRENT | this lane |
| pi/stage1-spec-extraction | 954441c4 | 0 | yes | CURRENT | sibling Stage 1 lane |
| pi/stage1-traceability | 954441c4 | 0 | yes | CURRENT | sibling Stage 1 lane |
| pi/test-scheduler-timeouts | 7bf3cdb6 | 0 | yes | PRESERVE | in origin/main; plan lists scheduler test as independently audited PASS (plan FACT, not re-verified here) |
| pi/u-b2a | d88b0ee9 | 0 | yes | PRESERVE | in origin/main |
| pi/u-b2a-problem-fields | a7352e59 | 0 | yes | PRESERVE | in origin/main |
| pi/u-erase-g1-g10 | 438e0c16 | 0 | yes | PRESERVE | in origin/main |
| pi/u-p1-schema-review | a1d084e5 | 3 | no | MERGE (docs) | memory reconciliation review; superseded in part by this Stage 1 set |
| pi/u-q6-open-items | 6560b0a7 | 0 | yes | PRESERVE | in origin/main |

## 5. Corrections to the plan found by reading the code (FACT unless marked)

| # | Plan statement | Code truth | Where |
|---|---|---|---|
| 1 | A3: `pi_problem_links` "persists PS-7 edges" as if new | the table exists and the model link op already writes it (`problems.py`, `business.py:229`); PS-7 persists nothing; table lacks basis, quote, source message | architecture 3, entities E4 |
| 2 | A4: "semantic.py pgvector exists" | embeddings are `ARRAY(Float)` cast to `VECTOR` at query time; no vector column in migrations read, so no ANN index is possible without a new column | architecture 6 |
| 3 | A3: fold `service_brief["business_profile"]` into `pi_profile_facts` | the brief key is already rewritten from the store every turn (`sync_context`); the real duplicate is `pi_memories` | gap D1 |
| 4 | A6: "118 industries have extraction cases" | script counts 116 industries with extraction cases (121 with any case) | industry matrix 2 |
| 5 | PS-9 and PS-7 "not wired" | true at `a07fe1e0`; at `1653b510` PS-9 is called per turn and PS-7 is used for wording; `current_language` is still not stored, PS-7 edges still not persisted | gap X1 |
| 6 | Plan: storage stops at in_build / S13 | `flow.State` ends at `S13_IN_BUILD`; `Box.STATES` ends at `revised`; PS-8 expects `delivered`, which nothing stores (INFERENCE) | architecture 4 |

## 6. Not verified in this stage

- I ran no unit or integration test and no model call; no pass or fail is reported for any lane.
- The plan's "independently audited PASS" list (FT-02, L1-7a, L2-2, BL-04, E2c, scheduler test, FT-A3) is the plan's statement; I only confirmed those branches are ancestors of origin/main.
- ps-flow commits after `a07fe1e0` (up to `1653b510`) were checked only for module wiring, not for memory-store changes.
- The prompt assembly (whether both `what_i_know` and the PS-8 bundle reach the model in full), the tail of `customer_profile` (export), `pi_reply_audits` erase rule, and real-database state (pgvector, data volumes, migration level) were not read or queried.
- Spec PDFs were not re-read here (the Stage 1 spec lanes own that); spec references come from the plan and CLAUDE.md.
- `pi/spec-gaps-1` appeared during the session; its code was not read.
