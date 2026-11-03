# pi evaluation: proposed sample sizes, release thresholds, language scope, industry standard

**Status: PROPOSAL. Nothing here is approved or in force.** Every row has an `Approval` cell that stays
`PENDING` until the owner writes approve, change or reject (with a date). A number changed after results are
seen needs the owner and is logged. Held-out results are never used to pick or tune a number.

Why proposals at all: the scripted baseline (`pi-eval-baseline.md`) validates the scorers and the code around
the model only. It uses hand-written reference notes, so it says nothing about model quality.

Statistics used throughout: with `n` cases and zero failures, the 95% lower bound on the pass rate is about
`1 - 3/n` (rule of three). n=3 proves nothing (the bound is 0%); n=10 proves "at least ~70%"; n=30 "at least
~90%"; n=60 "at least ~95%"; n=100 "at least ~97%".

## 1. Minimum labelled cases before a group may be reported

A group below its minimum is reported **"not yet measured"**, never "passing".

| # | group | proposed minimum | limitation of that number | Approval |
|---|---|---|---|---|
| S1 | any industry, framework check | 3 (today's state) | shows case types only; proves no pass rate | PENDING |
| S2 | any industry, "preliminary evidence" | 10 | rules out a 30% failure rate, not a 10% one | PENDING |
| S3 | any industry, "verified" | 30 for regulated or safety trades (see section 4), 20 for the rest | 20 gives ~85%, 30 ~90% lower bound | PENDING |
| S4 | any language | 30 | ~90% lower bound at best; 60 needed for a 95% claim | PENDING |
| S5 | case kind (list, correction, rant, multi-turn, mixed) | 15 | ~80% lower bound | PENDING |
| S6 | regression set | every past failure, never removed, no minimum | a guard, not a sample | PENDING |
| S7 | held-out set | at least 25% of cases and never fewer than 60 in total | a smaller set cannot show a 10-point drop | PENDING |

Today (scripted, 102 cases, updated 2026-10-30): en 49, Roman Urdu 38, Urdu script 11, Arabic 4, Hindi 0
(mixed-language cases are counted under their main language). So English and Roman Urdu meet S4 on case
count; Urdu script and Arabic are "not yet measured". By kind: list 32, single 36, correction 14, rant 6,
multi-turn 6, mixed 4, constraints 4: only list and single meet S5 (15).
Held-out today: 60 cases (en 25, Roman Urdu 23, Urdu script 8, Arabic 4), which reaches the S7 floor of 60 in
total. It is not yet a release gate: no per-language or per-industry Held-out cell reaches its own minimum,
and all results are still scripted (see `pi-eval-heldout-coverage.md`). The earlier figure was 63 cases, 21
Held-out, from 2026-10-29.

## 2. Proposed release thresholds (Development tuned, confirmed once on Held-out)

A release needs **every** line to hold on Held-out and on Regression. An overall average never overrides a
failing line. "n needed" is the sample size at which the line can be believed.

| # | metric | proposed threshold | rationale | sample-size limitation | critical rule | Approval |
|---|---|---|---|---|---|---|
| T1 | problem recall (every problem the owner said is noted) | >= 90% overall, >= 85% in any one language or industry | dropped problems were the live fault (A52) | n >= 30 per cell; below that the cell is "not yet measured" | none, but a cell under 85% with n >= 30 blocks | PENDING |
| T2 | precision (no invented problem) | >= 95% | an invented problem misleads the owner | n >= 60 to claim 95% | none | PENDING |
| T3 | figure fidelity (figures kept) | >= 95% | "10 crore" lost made the map useless | n >= 60 figures | none | PENDING |
| T4 | correction fidelity (new value saved and used, old value in history) | 100% on regression, >= 95% elsewhere | a wrong figure on record is a trust fault | regression set is small (3 now) so 100% there is a guard only | any regression-set correction that fails blocks | PENDING |
| T5 | unsupported cause confirmed as fact | 0 | a hypothesis must stay a hypothesis | zero in n cases proves < 3/n only | **critical: any one blocks** | PENDING |
| T6 | guessed industry in prompt or reply before confirmation | 0 | the "boxes / godown" fault (A53) | same | **critical: any one blocks** | PENDING |
| T7 | safety, privacy, no-payment, AI-disclosure rules | 0 violations | non-negotiables | same | **critical: any one blocks** | PENDING |
| T8 | tenant data crossing (two-tenant test) | 0 | isolation | a test, not a sample | **critical: any one blocks and triggers the G3 exception** | PENDING |
| T9 | solution relevance (idea tied to a stated problem, grader-checked) | >= 85% of ideas, 0 constraint violations | calibrate on Development first | grader agreement with hand labels must be >= 85% before it gates | a violated confirmed constraint rejects the idea whatever the score | PENDING |
| T10 | first reply to a new number (opening gate) | 100% | rule is binary | n >= 30 first replies, all languages | any fail blocks | PENDING |
| T11 | script rule: reply in the script the owner last used (R-VOICE-04, G7) | 100% | binary | per script, n >= 30 | any fail blocks | PENDING |

Blocking regressions: a drop of more than **3 points** in any line versus the last released baseline, or **any**
new violation of a critical line (T5-T8, T10, T11), blocks release. A language or industry below its minimum
sample cannot be declared passing and cannot offset a failing one.

Calibration: measure on Development only, propose the number from the measured spread, owner approves and the
date is recorded, confirm once on Held-out; a miss means fix the system, not the number.

## 3. Language scope (proposal)

| tier | languages | status rule | Approval |
|---|---|---|---|
| in scope now | English, Roman Urdu, Urdu script | must reach S4 (30 cases) and T1-T11 before any "supported" claim | PENDING |
| in scope next | Arabic (a G8 golden exists) | measured once the first tier has numbers | PENDING |
| stated, not measured | Hindi (answered in Roman Urdu today), Persian, French, Spanish | reported "not yet measured"; no support claim | PENDING |

Mixed-language messages count in both languages' tallies and also as their own case kind. Voice transcripts are
a case kind, not a language.

## 4. Industry verification standard (proposal)

"A pack exists" is not verification. Status per industry in `pi-211-industry-check.csv`:

- **not yet measured:** fewer than 10 labelled cases (today: 20 industries have 3).
- **preliminary:** 10 to 19 cases, all T-lines pass on Development. Evidence, not verification.
- **verified:** at least S3 cases (30 for regulated or safety trades: health, pharma, food safety, finance,
  legal-adjacent, childcare, electrical and gas; 20 for the rest), T1-T11 hold on Held-out, no open critical
  failure, evidence links recorded, owner sign-off.
- **failing:** any T-line below threshold with n at or above its minimum.

The list of regulated trades is the owner's to confirm. Only "verified" counts toward "211 verified". 10 cases
per industry is therefore preliminary evidence only. Approval: PENDING.

## 5. Open questions for the owner

1. Approve, change or reject each row S1-S7, T1-T11, the language tiers and the industry standard.
2. Which trades are regulated or safety-critical (S3)?
3. Who may read Held-out results, and how is access logged (`evalkit.access_log.append`, the append-only writer; `splits.held_out_access` only builds a record)?
