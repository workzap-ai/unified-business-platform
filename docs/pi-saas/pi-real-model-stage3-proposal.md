# P-5 Stage 3: conversation-level real-model evaluation (PROPOSAL, nothing is approved or run)

2026-10-30. Status: **proposal document only.** No model call, no key, no spending, no runner or code
change. Stage 3 needs its own model verification, price check, cap, test scope and explicit run
approval, and comes after Stages 1 and 2.

Words used: **scripted** = automated test with no model; **real-model** = measured on an actual model.
Nothing in Stage 3 exists yet as code; this is the plan to review.

## 1. Purpose

Stages 1 and 2 test one component, the extractor. Stage 3 tests what the owner actually meets: pi's
whole reply path over a short conversation. It measures requirement completeness and preservation,
relevance, creativity, solution and plan depth, repetition, redundant questions, constraint violations,
multilingual quality and consistency, on real model output. Development conversations first, Held-out
once.

## 2. Models (exact IDs, availability, deprecation)

From the registry (`app/ai/registry.py`) and the call sites; **what production pins in settings is
unverified**.

| Step | Alias | Default model | Where |
|---|---|---|---|
| extraction, judge | `fast` (= `router`) | `gpt-4o-mini` | `problem_extract.py:135`, `expert_advisor.py:57` |
| reply (brain mode) | `pi_brain` | `gpt-5.4-mini` | `registry.py:45`, `service_conversation.py:4615` |
| expert diagnosis | the reply alias | `gpt-5.4-mini` | `expert_advisor.py:600` |

Verified from OpenAI's pages on 2026-10-30 (summarising fetch; the owner re-checks):

| Model ID | Input | Cached input | Output (USD per 1M tokens) | Status |
|---|---|---|---|---|
| `gpt-4o-mini` | 0.15 | 0.075 | 0.60 | deprecated; shutdown "January 14, 2027"; replacement `gpt-6-luna` |
| `gpt-6-luna` | 0.10 | 0.01 | 0.50 | no shutdown note found |
| `gpt-5.4-mini` | 0.75 | 0.075 | 4.50 | no shutdown note found |
| `gpt-5.4` | 2.50 | 0.25 | 15.00 (short context, under 272K tokens) | not on the deprecations page |

Sources: `https://developers.openai.com/api/docs/pricing` and
`https://developers.openai.com/api/docs/deprecations`, read 2026-10-30. The registry note says
`gpt-5.4-mini` was chosen on 2026-10-24 after a live comparison (gpt-5.5 failed on the key then); its
availability to the owner's key **today is unverified**. The owner runs
`curl -s https://api.openai.com/v1/models/<model-id> -H "Authorization: Bearer $OPENAI_API_KEY"` for
`gpt-5.4-mini` and the router model; a 404 means the key cannot use it.

**Decision needed:** the Stage 3 generator should be the model production uses (`gpt-5.4-mini`), and the
router model should be the one production will use after 14 January 2027 (the same choice as Stages 1
and 2). Testing a different model measures that model, not production.

## 3. What a run does (and what it needs that does not exist yet)

Each case is a short owner conversation from the evaluation cases. The owner messages are **scripted
text**; pi's replies are **real**. Limitation, stated up front: a scripted owner does not react to pi's
replies, so this is not a free dialogue. A simulated owner (a second model) would be more realistic but
adds cost and a second source of error; it is not proposed here.

Each turn runs the real pipeline on the **disposable database** (never `apps/api/.env`): extraction,
reply (up to 3 attempts when the linter asks for a regeneration), a language rewrite when needed, the
expert diagnosis, and the judge. Per turn that is at most 1 + 3 + 1 + 1 + 1 = **7 model calls**.

**Required before any run (not built, needs approval):** a spend guard at the provider layer, so every
call the pipeline makes goes through one wrapper that applies the Stage 1 controls: dry run by default,
refuse a call whose worst case passes the cap, update spend from the provider's `usage`, stop on any
HTTP error, malformed output or a different answering model, one result line per turn as it arrives,
the key only in the environment, proxy and certificate variables ignored, no redirects. The Stage 1
runner covers one call type only, so this is new code with its own tests.

**Prompt sizes now derived from the code** (2026-10-30, `pi-real-model-cost-verification.md` section 3,
no prompt built, no database): the reply call sends a system text of 50,034 chars always (70,416 at most)
and a context JSON of about 55,800 chars typically (about 102,700 at most), so about 26,800 input tokens
typically (matching the "about 26,000 tokens" comment at `problem_extract.py:7`, not verified) and
**86,618 at the worst-case rule** (2 characters per token plus 60). A measured dry run with the scripted
model on the disposable database still replaces the remaining assumptions (unbounded context keys, judge
candidates, diagnosis examples) and needs approval. The spend-guard design is in
`pi-real-model-spend-guard-design.md`.

## 4. Datasets

| Part | Source | Count and rule |
|---|---|---|
| Development | `evalkit/cases/extraction.json` (69 Development; 6 `multi_turn`, 5 `constraints`, 9 `correction`, 17 `list`) | selected by a rule fixed before the run (case id order within the kind), written to a manifest file; the full variant uses 20, the lower variant 10, the minimal variant 6 |
| Held-out | same file (60, of which 3 `multi_turn`) | **not enough conversation cases today** (D5 sets the minimum); new Held-out conversation cases would be written first (FT-A3 plans 30 scripted solution cases), kept away from every tuning step, opened once |
| Regression | 3 cases | included in the Held-out run |

Languages in Development: en 24, roman_ur 18, ur 11, ar 8, hi 8; Held-out: en 25, roman_ur 23, ur 8,
ar 4, hi 0. Each result is reported per language with its n; a cell under 3 is "not yet measured".
Held-out access uses `splits.held_out_access(log, who, why)`, once, no tuning afterwards, a re-run is a
second access that needs approval.

## 5. Calls, tokens and the hard budget cap (PROPOSED, recomputed 2026-10-30 from the code sizes)

Worst-case rule per step: input at 2 characters per token plus 60 tokens, plus the full `max_tokens`;
cost = (input x input rate + output max x output rate) / 1,000,000, cached discount ignored; prices as
in section 2 (unchanged on re-verification). Sizes and arithmetic are in
`pi-real-model-cost-verification.md` section 3.

| Step | Model | Input tokens, worst | Output max | Cost, worst |
|---|---|---|---|---|
| extraction | `gpt-4o-mini` | 2,721 | 1,500 | USD 0.001308 |
| reply, up to 3 attempts | `gpt-5.4-mini` | 86,618 | 4,096 | 3 x USD 0.0833955 = USD 0.2501865 |
| language rewrite | `gpt-5.4-mini` | 2,560 (it sends only the reply) | 1,200 | USD 0.00732 |
| expert diagnosis | `gpt-5.4-mini` | 25,690 | 4,000 | USD 0.0372675 |
| judge | `gpt-4o-mini` | 7,207 | 1,500 | USD 0.001981 |
| **one turn, worst, 7 logical calls** | | | | **USD 0.298063** (was 0.2699) |

A typical turn (one reply attempt, no rewrite) is about USD 0.033 (was 0.11). Two further paths exist in
the code and were not counted before: the shape-fallback call (`service_conversation.py:5866-5896`,
turn worst USD 0.5206015, 10 logical calls) and the default one-retry setting (`app/core/config.py:105`,
up to double the HTTP attempts). The run therefore sets retries to 0 and failover off (see the spend-guard
design); with that, one logical call is one HTTP attempt.

| Variant | Conversations x turns | Worst case (7 calls per turn) | Proposed hard cap | Calls, at most | Worst case with the shape fallback each attempt |
|---|---|---|---|---|---|
| Minimal | 6 x 3 = 18 turns | USD 5.3651 | **USD 5.50** (was 5.00) | 126 | USD 9.37, 180 calls |
| Lower | 10 x 4 = 40 turns | USD 11.9225 | **USD 12.00** (was 11.00) | 280 | USD 20.82, 400 calls |
| Full | 20 x 6 = 120 turns | USD 35.7676 | USD 36.00 (was 33.00; not recommended first) | 840 | USD 62.47, 1,200 calls |

The earlier caps are below the new worst case. Typical cost for the same variants is about USD 0.59, 1.31
and 3.94. The owner chooses a cap at the worst-case bound (the run never stops early) or at a multiple of
the typical cost (an unlucky run stops early and keeps its partial results). The cap is hard: the guard
stops before a call that would pass it and spend is updated from the provider's `usage`; if the owner
wants a smaller cap, conversations or turns are cut, never the cap raised. If the generator were
`gpt-6-luna` the same turn costs a fraction, but that measures a model production does not run. These caps
are far above Stage 1 (USD 0.50, the only approved cap) and need a deliberate yes. The earlier real-model
sweeps charged the owner's auto-reload balance quickly (memory note 2026-10-26), which is why auto-reload
must be off.

## 6. Key handling

A new dedicated key, auto-reload off, a provider-side limit not above the chosen cap, revoked after the
run; the owner creates it and types it into the shell. Claude never sees, stores or logs it.

## 7. Scoring and grader independence

Scripted scorers (code, no model), reused or to be written: requirement preservation (the Stage 1 recall
and `constraint_kept` read from the saved record **and** from the reply text: "10 nahi, 100" must show
in both), repetition (the same question or sentence twice), redundant question (a question the stored
record already answers), one question last, language match, no payment or price while listening,
constraint violation (a confirmed constraint broken by an idea).

Model-judged measures: relevance to the stated problem, solution and plan depth, creativity,
consistency. **The grader is never the generator and never the same call.** Proposed: the `grader`
agent (a Claude subagent of this tool, a different vendor from the OpenAI generator, reading the saved
transcripts afterwards; no OpenAI spend). Fallback only if the owner prefers an API grader:
`gpt-5.4` at about USD 0.0525 per conversation worst case (12,000 in, 1,500 out), which is the same
vendor as the generator and therefore less independent. Neither is human truth.

**Creativity, repetition-by-meaning and depth stay unscored claims until the 85% agreement test passes**
(P-2): at least 20 human-labelled samples, agreement of at least 85% between the grader and the human
labels. That threshold is still a **proposal** until the labelling method and samples are reviewed.
Scripted scorer results are labelled "scripted" and never reported as AI quality. No pass or fail
threshold is used: **D5 is pending**.

## 8. What Stage 3 can and cannot claim

Can: how the real pipeline behaved on 6 to 20 Development conversations (then Held-out once) on each
measure above, per language with its n, compared with the scripted baseline.
Cannot: free-dialogue behaviour (the owner is scripted); production traffic quality; any language or
industry cell below its minimum; industry verification; creativity before the 85% test; outcome
verification of real actions (P-6); anything about the models after a silent provider change (a different
answering model stops the run).

## 9. Dependencies

Stage 1 run and reviewed; Stage 2 run if approved; D5; the provider-layer spend guard built and tested
(new code, separate approval); the measured prompt sizes; new Held-out conversation cases; the
labelled sample set for P-2; FT-02 integrated, so the replies tested are the replies that ship.

## 10. Owner approval checklist (every box needs your explicit yes)

1. Stages 1 and 2 reviewed.
2. D5 thresholds, language scope and industry criteria approved.
3. Generator and router model IDs chosen; availability checked by you; prices checked on the dashboard.
4. Variant and hard cap chosen (minimal USD 5.50, lower USD 12, full USD 36, from the recomputed worst
   case), after a measured dry run replaces the remaining assumptions and the arithmetic is redone.
5. The spend-guard code reviewed and merged by approval; tests show no call passes the cap.
6. Held-out conversation cases written and sealed; access logged.
7. Grader choice and the 85% labelling method reviewed.
8. A new key with auto-reload off and a provider limit, created by you, revoked after.
9. A run date and who is recorded.
