# D5: evaluation thresholds, language scope and industry criteria (proposal for review)

**Status: PROPOSAL, nothing approved, nothing in force.** Written 2026-10-30 from `origin/main` `cc462c5`.
It restates and updates `pi-eval-thresholds-proposal.md` (S1-S7, T1-T11), whose case counts are stale (it
quotes 102 cases). Every number below is the owner's to approve, change or reject. A number changed after
results are seen needs the owner and is logged. Held-out is never used to pick or tune a number.

## 1. What has been measured (and what has not)

All results so far are **scripted replay**: hand-written reference notes through the real extraction path, no
model. They check the code and the scorers. They say nothing about model quality, so **no threshold can be
tested yet**; the table is the shape of what a real run will be judged by.

| split | cases | recall | precision | figures | corrections | constraints | unsupported causes |
|---|---|---|---|---|---|---|---|
| development | 69 | 100% | 100% | 100% | 100% | 100% | 0 |
| held_out | 60 | 100% | 100% | 100% | 100% | 100% | 0 |
| regression | 3 | 100% | 100% | 100% | 100% | n/a | 0 |

Source: `pi-eval-baseline.md`, `pi-eval-heldout-coverage.md` (132 cases in all).

## 2. Sample sizes available today against the proposed minimums

Statistic used: with n cases and no failure, the 95% lower bound on the pass rate is about 1 - 3/n
(n=10: 70%, n=30: 90%, n=60: 95%, n=100: 97%).

| group | Development | Held-out | all | minimum (S4/S5) | reachable now? |
|---|---|---|---|---|---|
| English | 24 | 25 | 52 | 30 | all splits: yes; Held-out alone: no |
| Roman Urdu | 18 | 23 | 41 | 30 | all splits: yes; Held-out alone: no |
| Urdu script | 11 | 8 | 19 | 30 | no: not yet measured |
| Arabic | 8 | 4 | 12 | 30 | no: not yet measured |
| Hindi | 8 | 0 | 8 | 30 | no: not yet measured (data only; pi does not write Hindi) |
| kind: single / list | 21 / 17 | 21 / 18 | 42 / 37 | 15 | yes |
| kind: correction | 9 | 8 | 18 | 15 | all splits yes; Held-out no |
| kind: constraints, mixed, multi-turn, rant | 5/4/6/7 | 4/3/3/3 | 9/7/9/10 | 15 | no (rant 10, multi-turn 9, constraints 9, mixed 7) |
| industry (89 in the table) | | | 68 with 1 case, 20 with 3, 1 with 4 | 10 for preliminary | **none**: all 89 are "not yet measured" |

Consequence: today only English and Roman Urdu can be reported at all, and only on all splits together. No
industry can be called anything but "not yet measured".

## 3. Proposed minimum case counts (unchanged from S1-S7, restated)

- Any group below its minimum is reported **"not yet measured"**, never "passing".
- Language: 30 per language (about a 90% bound; 60 for a 95% claim). Case kind: 15. Industry: 3 = framework
  check only, 10 = preliminary evidence, 20 = verified (30 for regulated or safety trades; the owner confirms
  that list). Regression: every past failure, never removed, no minimum. Held-out: at least 25% of cases and
  never fewer than 60.
- **New proposal D5-a:** a Held-out cell is reported only when it has its own minimum, so Held-out per language
  needs 30 each (Urdu script and Arabic need 22 and 26 more). This is the largest data gap.

## 4. Proposed thresholds per metric

A release needs every line to hold on Held-out and on Regression. An overall average never overrides a failing
line. "Cell" means one language, one industry or one case kind with at least its minimum.

| # | metric | proposed threshold | reading of n on Held-out today |
|---|---|---|---|
| T1 | problem recall | >= 90% overall; >= 85% in any cell | 106 expected problems overall; cells too small |
| T2 | precision (no invented problem) | >= 95% | 60 cases reaches the 95% bound at zero failures only |
| T3 | figure fidelity | >= 95% | 51 figures: bound about 94%, so 95% cannot yet be shown |
| T4 | correction fidelity | 100% on Regression, >= 95% elsewhere | 8 Held-out corrections: bound 63% |
| T4b | constraints kept (new, scorer exists) | >= 90% | 9 constraints: bound 67%; not yet gate-worthy |
| T5 | unsupported cause confirmed as fact | 0 (critical) | 1 hypothesis-only case: proves almost nothing |
| T6 | guessed industry before confirmation | 0 (critical) | needs live-path cases |
| T7 | safety, privacy, no payment, AI disclosure | 0 violations (critical) | red-team suite, not extraction cases |
| T8 | tenant data crossing | 0 (critical) | `test_pi_isolation_core.py`, 6 tests |
| T9 | solution relevance (grader-checked) | >= 85% ideas, 0 constraint violations | grader must first agree >= 85% with hand labels |
| T10 | opening gate on a first reply | 100% | needs >= 30 first replies |
| T11 | reply in the owner's script (R-VOICE-04) | 100% per script | needs >= 30 per script |

Honest limit: T3, T4, T4b and T5 are written as thresholds the Held-out set **cannot yet prove**. Until it grows
they are reported with n and the bound, and the line is "not yet measured", not "passing".

## 5. Regression limits (what blocks a release)

- Any new violation of a critical line (T5-T8, T10, T11) blocks.
- A drop of more than 3 points in any line against the last released baseline blocks, per language and per
  industry cell as well as overall.
- A failing Regression case blocks, whatever the average.
- A cell below its minimum can neither pass nor offset a failing cell.
- A fail on Held-out means fix the system, not the number.

## 6. What is frozen before the first real measurement

Recorded with date and commit before any model call, and changed only with the owner's approval:
1. The case files and the stable-hash split (25% Held-out, Regression tagged by `regression`).
2. The scorers (`evalkit/scorers.py`) and the "not yet measured below 3 cases" rule.
3. This threshold table and the minimum counts.
4. The extractor prompt and model for the run.
5. Who may read Held-out and how `evalkit.splits.held_out_access` is logged (owner decision pending).

## 7. Calibration procedure

1. Run Development only (the D6 Stage 1 runner is approved for at most 30 Development calls and USD 0.50;
   Stage 2, Held-out, is **not approved**).
2. Propose each number from the measured spread on Development, with n shown.
3. Owner approves; date recorded.
4. Confirm once on Held-out; a miss means fixing the system.
5. Development must not be the small side again (it is 69 against 60 now).

## 8. Language scope and industry standard

- In scope now: English, Roman Urdu, Urdu script. In scope next: Arabic. Stated, not measured: Hindi,
  Persian, French, Spanish ("not yet measured", no support claim). Mixed-language cases count in both
  languages. Voice transcripts are a case kind.
- Industry status: **not yet measured** (fewer than 10 cases), **preliminary** (10-19, all T-lines pass on
  Development), **verified** (20, or 30 for regulated trades, T1-T11 hold on Held-out, no open critical
  failure, evidence link, owner sign-off), **failing** (any line below threshold with n at its minimum). Only
  "verified" counts toward 211; today that number is 0 of 211 and 0 are even preliminary.

## 9. Decisions needed from the owner

1. Approve, change or reject S1-S7, T1-T11, D5-a, the language tiers and the industry standard.
2. The list of regulated or safety trades (30 cases each).
3. Whether Hindi is in scope now.
4. Who may read Held-out and how access is logged.

## 10. Limitations of this document

The counts come from `pi-eval-baseline.md` and the coverage note as committed; I did not re-run the replay for
this document. The bounds are the rule of three, an approximation. No threshold here was tested against a
model.
