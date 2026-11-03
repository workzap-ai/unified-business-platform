# Acceptance requirements 1 to 6 against the approved roadmap (A to G)

Status: PROPOSAL for owner review, 2026-10-30. Nothing here changes approved scope. Gaps are listed as
proposed additions (P-n), each needing the owner's yes. Vocabulary: **planned** = a roadmap task exists,
nothing built; **implemented** = merged to `origin/main`; **tested** = automated tests pass (scripted, no
real model unless said); **verified** = measured on a real model or independently checked on labelled
data. At this date nothing in requirements 1 to 6 is **verified** against a real model.

Base: `origin/main` cc462c5 (unit suite 7670 passed, 2 xfailed; isolation test 6 passed).
Task ids are from `pi-fast-track-plan.md`.

## Requirement 1: complete business understanding

| Part | Roadmap task | Status |
|---|---|---|
| goals, problem, figures, since, how often, cost | B6 S1 to S3 (merged), B2b quality score (planned) | implemented, tested (scripted). Not verified on a real model |
| budget, staff, deadline, cannot-change | B2a (planned, migration 0053) | planned. Blocked behind FT-02 |
| attempted solutions and outcomes, cause with source | B2a `tried`, `cause` status/source/evidence | planned |
| already-answered questions not asked again | B6 S4 slot carry, S5 fact gate (merged, `fact_ask` opt-in, off by default), S3 short repeats | implemented, tested. Off by default; S6 extends it (planned) |
| existing systems and tools | FT-REQ sheet field | planned |
| missing critical information, one top question | FT-REQ (completeness score, top 3 missing, ask top 1) | planned |
| **workflows, entities (people, roles, systems), expected outcome** | not a named field in B2 or FT-REQ | **GAP, see P-1** |

Acceptance (existing): the 9 labelled Held-out constraints recorded at 90% or more on Development;
Artwing transcript: 8 modules in the sheet. Dependencies: FT-02, B2a, then B2b and S6, then REQ.

## Requirement 2: proactive solutions and creative ideas

| Part | Roadmap task | Status |
|---|---|---|
| ideas from the stated problem, not a repeat of the words | expert advisor, G12 idea link (opt-in), B6 gates (merged); FT-C1 relevance in code (planned) | implemented, tested (scripted); C1 planned |
| do not ask what to build when context exists | Part 19 and ART2 (Artwing), S6 | Part 19 on `pi/s-ft02`, **blocked by 4 audit findings**; ART2 planned |
| "no idea" allowed, no quota | FT-C1 | planned |
| creativity, novelty, repetition measured | FT-A3 scores relevance, fact reuse, constraint fit only | **GAP, see P-2** |

## Requirement 3: industry-specific actionable plans

| Part | Roadmap task | Status |
|---|---|---|
| industry detected without guessing | C2 (merged), FT-C3 probes (merged as tests; solar overlap strict xfail) | implemented, tested |
| pack ideas vetted | FT-C6 (merged: 58 allowlisted, review document ready, 18 proposed rewrites) | tested; owner review pending |
| depth: modules, steps, dependencies, next actions | FT-C4 (needs owner approval after C1), FT-ART2 (Solution Box per module) | planned |
| plan completeness and per-industry status | `pi-211-industry-check.csv` goal; D5 proposal | **0 industries verified.** Held-out holds 89 industries, none with 10 cases; **GAP, see P-3** |

## Requirement 4: persistent context and decisions

| Part | Roadmap task | Status |
|---|---|---|
| closed facts and asked facts across chats | B6 S4 `slot_carry` (30 days, 2 days), erased with the customer | implemented, tested |
| more stated facts across chats | FT-S6 (S6-a, reuse `memory_block`) | planned |
| constraints, corrections, tried | B2a (per problem), corrections history | planned |
| tenant isolation | FT-E2a (merged, 6 tests), learning isolation test (merged) | implemented, tested. Postgres RLS: D8 pending |
| erase and retention | `brain_erase`, FT-E2b (merged, 14 gaps recorded), G1 to G15 table | partial. Retention decisions R1 to R6 pending; share-link fix pending |
| previous decisions (offer declined, quote approved) carried to a new chat | not in the roadmap | **GAP, see P-4** (needs checking first: some of it may already be in the deal records) |

## Requirement 5: real AI quality verification

| Part | Roadmap task | Status |
|---|---|---|
| Development / Regression / Held-out | evalkit (merged): Development 69, Held-out 60, Regression 3 | implemented, tested. Regression is only 3 cases |
| real-model run | FT-REPLAY and D6 Stage 1: the **extractor only**, Development only, 30 calls, USD 0.50 | runner built (`pi/e-d6-runner`, 47 tests), **not run**, no key, model not yet chosen |
| completeness, relevance, depth, repetition, constraints, multilingual, consistency of real replies | Stage 2 (Held-out) and Stage 3 (conversations) were **not approved** | **largest gap, see P-5** |
| scorer reliability | FT-A3: 85% agreement with the `grader` on 20 hand labels | planned |

What Stage 1 can say: how often the real extractor keeps what the owner said, on Development text. It says
nothing about reply quality, solution depth or creativity. Until P-5 exists, those are unmeasured.

## Requirement 6: safe execution and verified outcomes

| Part | Roadmap task | Status |
|---|---|---|
| explicit approval, reviewer approves quotes, no payment in chat | decision gates, linter (merged); R3 decision (owner, 2026-10-30): R3 offers only, R1 may prepare | implemented; the R3 change is part of the FT-02 fix, not yet built |
| privacy and redaction | `safety.py`, redaction; Part 19 wants and board findings | partial: audit findings 2 and 3 open on FT-02 |
| auditability | F1 found denied actions never audited (B1) | planned (capability-map backlog) |
| tenant isolation, erase | see requirement 4 | as above |
| rollback | `/pi-rollback`, FT-D1, FT-E4 rehearsal | planned |
| safe execution and outcome verification ("never claim done without evidence") | B7.5 and G5 are principles; no Fast-Track task | **GAP, see P-6** |

## Proposed additions (not approved, not started)

- **P-1 requirement fields:** add workflows, entities (roles, systems) and expected outcome to FT-REQ's
  sheet and to B2's schema decision (D2), so migration 0053 is designed once.
- **P-2 FT-A4, conversation-quality scorers:** repetition, redundant question (answered in the record),
  and a creativity/novelty rubric. Creativity is judged by the `grader` agent, so it must first pass the
  same 85% agreement test on hand labels (FT-A3) before it is used for anything.
- **P-3 FT-A5, industry and plan depth:** a plan-completeness scorer (modules, steps, dependencies, next
  action) and enough cases per industry that "verified" is possible; D5 sets the minimum count.
- **P-4 FT-S7, decision ledger:** carry offer, decline, approval and attempted-action facts across chats
  (same tenant, erased with the customer). First step is a read-only check of what the deal and quote
  records already hold.
- **P-5 real-model stages 2 and 3, as proposals:** Stage 2 (Held-out extraction, once, after D5);
  Stage 3 (conversation-level: reply, solution and plan quality on Development, then Held-out once). Each
  with its own cap, model and price check, and your approval. Nothing runs before that.
- **P-6 FT-X1, evidence-backed claims:** a gate so pi never says an action was done, sent or approved
  unless a record shows it, plus an outcome-check step after delivery. Needs the after-payment journey
  records as its evidence source.

## What remains before production-ready (honest)

PI is **not** production-ready against these six requirements. In order:

1. FT-02: the four audit blockers (two questions, redaction order, board in the signed URL, R3 and
   promises) fixed, then unit, integration and rule-auditor gates on the new commit. Then B2a.
2. B2a, B2b, S6, REQ, C1, ART2 (about 12 to 15 working days as planned), with P-1 designed in.
3. The owner decisions: D5 thresholds, D6 model and key, D7 offer wording, D8 RLS, erase retention R1 to
   R6, the pack allowlist review.
4. Real-model evidence (P-5), because today no claim about reply quality rests on a model.
5. Erase and privacy fixes (G10 share links first), the two failing integration tests, FT-E4 release
   gates (Regression and Held-out per language and industry, rollback rehearsal), then a Workzap canary.
6. P-2, P-3, P-4, P-6 if approved.

No production change, spend, API call or push to a shared branch happens without your authorisation.
