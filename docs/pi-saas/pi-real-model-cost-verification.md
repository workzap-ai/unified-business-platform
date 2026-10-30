# P-5: model, price and Stage 3 cost verification (documentation only)

2026-10-30. Status: **PROPOSED for owner review.** No model call, no key, no spending, no runner or code
change. The only **APPROVED** decision on real-model work is **Stage 1: 30 calls, hard maximum USD 0.50
(D6), Development cases only, extractor only**, with the model and key still pending. Everything about
Stage 2 and Stage 3 (models, caps, variants, guard design) is **PROPOSED**.

Vocabulary used in every progress report: **documented** (this file), **implemented** (merged code),
**scripted-tested** (automated, no model), **real-model-verified** (measured on a real model). Nothing
below is implemented, scripted-tested or real-model-verified.

## 1. Roadmap check (what these documents must not change)

Checked against `pi-fast-track-plan.md` on `pi/doc-fast-track` (`git show
pi/doc-fast-track:docs/pi-saas/pi-fast-track-plan.md`):

| Roadmap item | Line | Effect of this review |
|---|---|---|
| FT-REPLAY: "Real-model sample, 30 calls first", effort 0.5 plus cost, needs approved thresholds and the owner's key and budget | 80 | unchanged; Stage 1 stays 30 calls, USD 0.50 |
| D6: "OpenAI key and a budget for the 30-call sample" | 124 | unchanged; approved for Stage 1 only |
| P-5 row: Stages 2 and 3 each need their own model verification, pricing, cap, scope and explicit run approval | 171 | unchanged; this file supplies the verification, it approves nothing |
| Conflict C9: Stage 3 cost and the need for a provider-level spend guard exceed D6; FT-REPLAY's 0.5 day is understated | consolidated review | **confirmed and sharpened** below: Stage 3's worst case rose, a new code component is needed, and retries and fallback multiply calls |
| Conflict C10: `gpt-4o-mini` is the production default for the router and is removed on 2027-01-14; no model-migration task exists | consolidated review | **confirmed** with the official deprecations table below |

No acceptance criterion of the roadmap is changed by this file.

## 2. Verified models and prices (sources, read dates)

Read on **2026-10-30** with a summarising fetch (the summariser can mis-transcribe; the owner re-checks on
the dashboard):

- Prices: `https://developers.openai.com/api/docs/pricing` (Standard tier, USD per 1M tokens).
- Deprecations: `https://developers.openai.com/api/docs/deprecations` (official page; the first fetch
  attempt returned "Unable to verify domain"; the second succeeded).
- A web search the same day found the same shutdown date for `gpt-4o-mini` on third-party pages, but its
  OpenAI excerpt did not show the `gpt-4o-mini` row; the fetch above shows it. Treat the date as read
  from the official page, not independently confirmed.

| Model ID | Input | Cached input | Output | Deprecations page (announced, shutdown, replacement) |
|---|---|---|---|---|
| `gpt-4o-mini` | 0.15 | 0.075 | 0.60 | 2026-10-14, **Jan 14, 2027**, `gpt-6-luna` |
| `gpt-6-luna` (short context, up to 272K input) | 0.10 | 0.01 | 0.50 | not listed as deprecated (appears only as a replacement) |
| `gpt-5.6-luna` (short context) | 0.20 | 0.02 | 1.20 | not listed as deprecated |
| `gpt-5.4-mini` | 0.75 | 0.075 | 4.50 | not listed anywhere on the page |
| `gpt-5.4` (short context) | 2.50 | 0.25 | 15.00 | not listed as a standalone model |
| `gpt-5.4-nano` | 0.20 | 0.02 | 1.25 | 2026-10-01, Apr 1, 2027, `gpt-6-luna` |
| `gpt-5-nano` | 0.05 | 0.005 | 0.40 | 2026-06-11, **Dec 11, 2026**, `gpt-5.6-luna` |
| `gpt-4.1-nano` | 0.10 | 0.025 | 0.40 | 2026-04-22, **Oct 23, 2026 (already past)**, `gpt-5.6-luna` |
| `gpt-5-mini` | 0.25 | 0.025 | 2.00 | 2026-06-11, Dec 11, 2026, `gpt-5.6-terra` |
| `gpt-4.1-mini` | not asked | not asked | not asked | 2026-10-14, Jan 14, 2027, `gpt-6-luna` |

Cheaper alternatives: the pricing page shows none cheaper than `gpt-6-luna` that is also still supported
past January 2027. `gpt-5-nano` is cheaper (0.05 / 0.40) but shuts down on 2026-12-11, and `gpt-4.1-nano`
has already shut down, so neither is a candidate. The page still prices `gpt-4.1-nano` after its shutdown
date, so **the pricing page lists models that are not available**; a price row is not proof of availability.

### Differences from the tables in the Stage 2 and Stage 3 proposals

| Item | Before | Now | Change |
|---|---|---|---|
| Prices of `gpt-4o-mini`, `gpt-6-luna`, `gpt-5.6-luna`, `gpt-5.4-mini`, `gpt-5.4` | as in the proposals | identical | none |
| `gpt-4o-mini` shutdown | "January 14, 2027" | Jan 14, 2027, announced 2026-10-14 | none (date and announcement now cited) |
| `gpt-5.4-mini`, `gpt-5.4` deprecation status | "no shutdown note found" | not listed anywhere on the page | wording only |
| `gpt-4.1-nano` | excluded (shut down 2026-10-23) | still shown with a price | new caveat: price rows can outlive availability |
| `gpt-5-nano`, `gpt-5.4-nano`, `gpt-5-mini` | not in the proposals | now listed with prices and dates | added for completeness, none is a candidate |

**Not verified:** whether the owner's key can use any model (the `curl` check in the Stage 3 proposal
remains the owner's step); whether production settings pin other models (`OPENAI_MODELS`); parameter
support of `gpt-6-luna` and `gpt-5.6-luna` (`max_tokens`, `temperature`, JSON mode); whether reasoning
tokens are billed as output for the "thinking" models; cached-input discounts are ignored in every
estimate here (they only lower cost).

## 3. Stage 3 prompt sizes derived from the code

Method: read the code, no prompt was built, no database was used. Constants were measured by parsing
the source text (strings only); caps were read from the code. Tokens are estimated from characters:
**worst case 2 characters per token plus 60 tokens of framing**, typical 4 characters per token (the same
rule as Stage 1). All paths are relative to `apps/api/app/modules/pi/` at `cc462c5` unless stated.

### 3.1 The reply call (`pi_brain`, default `gpt-5.4-mini`)

The call sends `Message.system(system_for(context))` and `Message.user(json.dumps(context))`
(`service_conversation.py:5967-5983`), `max_tokens=4096` (`service_conversation.py:5863`). A linter
regeneration resends the same text ("the rewrite below sends the very same system text and context
again", `service_conversation.py:5967`), up to 3 attempts as in the proposal.

System text, `system_for` (`service_conversation.py:1175-1196`):

| Part | Chars | Where | Always? |
|---|---|---|---|
| `BRAIN_SYSTEM = brain_prompt.cut(SYSTEM)` | at most 35,455 (`SYSTEM`, line 482; the cut only removes text, `brain_prompt.py:96`) | `service_conversation.py:933` | yes |
| `BRAIN_PROBLEMS` | 3,937 (raw lines 936 to 985) | `service_conversation.py:936` | yes |
| `BRAIN_DECISIONS` | 1,041 | `service_conversation.py:986` | yes |
| `BRAIN_VOICE` | 9,601 | `service_conversation.py:1002` | yes |
| `BRAIN_ASK` | 3,192 | `service_conversation.py:1119` | when a solution is asked |
| `expert_advisor.VOICE_RULE` / `PROMPT_RULE` | 585 / 965 | `expert_advisor.py:177`, `163` | when the expert is on / a main problem exists |
| `owner_asks` rules (six) | 585 + 669 + 274 + 385 + 431 + 381 = 2,725 | `owner_asks.py:94-135` | each only when its flag is set |
| `memory_block.SYSTEM_LINE` | 396 | `memory_block.py:109` | when memory is shown |
| `think_prompt.block` | at most the file size, 12,519 (a loose bound; the block is built from f-strings I could not measure) | `think_prompt.py:228-233` | only with the thinking flag |

System text: **always-present 50,034 chars** (35,455 + 3,937 + 1,041 + 9,601, the 35,455 being a maximum
before the cut), **maximum 70,416 chars** (everything on, think block bounded by the file size).

Context JSON (`prepare_context`, `service_conversation.py:4140-4205`):

| Key | Bound | Where |
|---|---|---|
| `spec_guidance` | 46,000 chars (`MAX_CHARS`) plus golden examples, at most the two largest of 15 sections: 899 + 782 = 1,681 (measured in `spec/handbook.json`; the state tables pick 1 to 2 ids) | `spec_handbook.py:27`, `:258-273`, `:139-155`; assembled at `service_conversation.py:1701` |
| `industry_knowledge` | 10,500 chars (`DEFAULT_BUDGET`; primary 5,200, others 2,000 each) | `industry_packs.py:687-689`; call at `service_conversation.py:3730` |
| `history` | 20 messages (`limit(20)`) at up to 1,500 chars each, about 120 chars of keys, plus link notes (not bounded in code): 32,400 | `service_conversation.py:3878`, `:4166` |
| `latest_customer_message` | 4,000 | `service_conversation.py:4180` |
| other keys (summary, brief, flow, noted problems, slots, deals, team, notes, tone, dates) | **not bounded by one cap in the code; allowance 8,000 (an assumption)** | `service_conversation.py:4140-4205` |

Context JSON: **maximum about 102,700 chars** (47,800 + 10,500 + 32,400 + 4,000 + 8,000). **Typical about
55,800 chars** (spec guidance near its 46,000 cap, because sections are added until the cap; industry
5,200; six messages at about 400 chars; short latest message; 2,000 for the rest). The typical spec
guidance being near the cap is an assumption about which sections match, not measured.

Reply call totals:

- **Maximum**: 70,416 + 102,700 = **173,116 chars** -> 173,116 / 2 + 60 = **86,618 input tokens**.
- **Typical**: about 51,500 system + 55,800 context = about 107,300 chars -> / 4 = **about 26,800
  tokens**. This agrees with the "about 26,000 tokens" comment at `problem_extract.py:7`; I did not
  verify that comment.
- **Minimum** (not derivable exactly, depends on which guidance sections match): at least the always-present
  50,034 chars of system text plus `FRAME` 272 (`spec_handbook.py:157`), about 52,000 chars, about 13,000
  tokens at 4 chars per token.

The old proposal assumed 52,000 input tokens for the worst case. The code gives **86,618**, so the old
reply worst case was too low.

### 3.2 The other model calls in a turn

| Step | Model (default) | System chars | Payload bound | Input tokens, worst | Output max | Where |
|---|---|---|---|---|---|---|
| language rewrite | reply alias | about 1,000 (text at `service_conversation.py:5227-5242`) | the reply, at most 4,000 chars (`ReplyOnlyTurn`, line 5834) | 5,000 / 2 + 60 = **2,560** | 1,200 | `service_conversation.py:5243` |
| expert diagnosis | reply alias (`gpt-5.4-mini`) | `PERSONA` 442 + `DIAGNOSE_RULES` 5,059 + unconfirmed-trade rule 258 + `NL2` (not measured, allowance 300) = 6,059 | owner messages 8 x 500 = 4,000; first message 600; problems 4 x 120; "already said" 8 pi replies **with no per-item cap in the code**, bounded by 4,000 chars each = 32,000; never-say 1,600 (allowance); currency block 1,800 (`currency_notes.py:80`); examples 1,200 (allowance); steer 2,720; JSON overhead 600 = 45,200 | 51,259 / 2 + 60 = **25,690** | 4,000 (1,500 when light) | `expert_advisor.py:574-606`, `:287-300` |
| judge | router (`gpt-4o-mini`) | `JUDGE_RULES` 1,134 | owner messages 4,000; causes 360; currency 1,800; candidates up to 8 x 800 = 6,400 (count and size are an assumption); overhead 400 = 13,160 | 14,294 / 2 + 60 = **7,207** | 1,500 | `expert_advisor.py:622-647` |
| extraction | router (`gpt-4o-mini`) | 1,761 (`problem_extract.py:27`) plus category list | as sized in the Stage 2 proposal | **2,721** (unchanged) | 1,500 | `problem_extract.py:135-142` |

### 3.3 Recomputed worst case per turn

Rate used: USD per 1M tokens, from section 2. Cost = (input tokens x input rate + output max x output
rate) / 1,000,000, cached discount ignored.

| Step | Arithmetic | Cost, worst |
|---|---|---|
| extraction (`gpt-4o-mini`) | unchanged from Stage 2 | USD 0.001308 |
| reply attempt (`gpt-5.4-mini`) | 86,618 x 0.75 = 64,963.5; 4,096 x 4.50 = 18,432; sum 83,395.5 / 1e6 | USD 0.0833955 |
| reply, 3 attempts | 3 x 0.0833955 | USD 0.2501865 |
| language rewrite (`gpt-5.4-mini`) | 2,560 x 0.75 = 1,920; 1,200 x 4.50 = 5,400; sum 7,320 / 1e6 | USD 0.00732 |
| expert diagnosis (`gpt-5.4-mini`) | 25,690 x 0.75 = 19,267.5; 4,000 x 4.50 = 18,000; sum 37,267.5 / 1e6 | USD 0.0372675 |
| judge (`gpt-4o-mini`) | 7,207 x 0.15 = 1,081.05; 1,500 x 0.60 = 900; sum 1,981.05 / 1e6 | USD 0.001981 |
| **one turn, 7 logical calls** | 0.001308 + 0.2501865 + 0.00732 + 0.0372675 + 0.001981 | **USD 0.298063** |

Before (Stage 3 proposal): USD 0.2699. The reply attempt rose from 0.057432 to 0.0833955; the rewrite
fell from 0.0444 to 0.00732 (it sends only the reply, not the whole context); the diagnosis fell from 0.048
to 0.0372675; the judge fell from 0.0039 to 0.001981.

**Extra call paths found in the code that the proposal did not count:**

1. **Shape-fallback call.** When every provider fails only because the output or schema was rejected,
   `structured_turn` makes one more call for the reply alone, `max_tokens=2048`
   (`service_conversation.py:5866-5896`). Worst case per attempt: 86,618 x 0.75 = 64,963.5 plus 2,048 x 4.50
   = 9,216, sum 74,179.5 / 1e6 = USD 0.0741795; three attempts add USD 0.2225385. Turn worst with it:
   **USD 0.5206015, 10 logical calls**.
2. **Same-provider retry.** `llm_max_retries` defaults to 1 (`app/core/config.py:105`; the loop is
   `app/ai/manager.py:451`), so a transient error is retried once: up to twice the HTTP attempts per
   logical call. Whether a failed attempt is billed is unknown. If all were billed the bounds double to
   USD 0.5961 and USD 1.0412.
3. **Provider fallback.** `FallbackPolicy` tries the other configured providers in order, and
   `ai_failover_all_configured` adds every provider that has a key (`app/ai/manager.py:88-110`). A run
   could silently be answered by another vendor and model. Stage 1's rule (stop when the answering model is
   not the expected one) must hold for Stage 3.

Recommendation for the run (PROPOSED): set the retries to 0 and failover off for the evaluation process
only (`LLM_MAX_RETRIES=0`, failover not enabled, provider order limited to OpenAI), so a call is exactly
one HTTP attempt; the bounds below then apply.

### 3.4 Variants and hard caps, recomputed (PROPOSED, none approved)

| Variant | Conversations x turns | Worst case, 7 logical calls per turn | Proposed hard cap | Calls, at most | Worst case if the shape-fallback fires every attempt (10 calls) |
|---|---|---|---|---|---|
| Minimal | 6 x 3 = 18 turns | 18 x 0.298063 = USD 5.3651 | **USD 5.50** (was 5.00) | 126 | USD 9.37, 180 calls |
| Lower | 10 x 4 = 40 turns | 40 x 0.298063 = USD 11.9225 | **USD 12.00** (was 11.00) | 280 | USD 20.82, 400 calls |
| Full | 20 x 6 = 120 turns | 120 x 0.298063 = USD 35.7676 | USD 36.00 (was 33.00; not recommended first) | 840 | USD 62.47, 1,200 calls |

The earlier caps (5.00, 11.00, 33.00) are **below** the new worst case. The typical cost is far lower:
about USD 0.033 per turn (one reply attempt of about 26,800 input tokens and about 500 output tokens
USD 0.02235; diagnosis USD 0.009375; judge USD 0.00075; extraction USD 0.00039; no rewrite; the typical
output sizes are assumptions), which gives about USD 0.59, 1.31 and 3.94 for the three variants (the old
typical figure was USD 0.11). A hard cap near the typical figure would stop an unlucky run early and
keep the partial results; the owner chooses between "cap at the worst-case bound" (never stops early)
and "cap at a multiple of typical" (stops early). Per the owner's rule the answer to an over-cap estimate
is fewer conversations or turns, never a higher cap.

## 4. Conflicts and assumptions that remain

1. Stage 3 spend exceeds D6 by two orders of magnitude (USD 5.50 to 36.00 against 0.50); it needs its
   own explicit approval and the spend guard (see `pi-real-model-spend-guard-design.md`).
2. The code gives several call paths (shape fallback, retry, failover) the proposal did not count;
   the retry and failover settings are the owner's or the run's configuration, not decided here.
3. Assumptions: 8,000 chars for unbounded context keys; judge candidate count and size; diagnosis
   examples and never-say sizes; typical output sizes; spec guidance near its cap. A measured dry run on the
   disposable database with the scripted model (no API call) is still the proper replacement and needs
   approval.
4. `think_prompt.block` is bounded by the file size, not measured.
5. Prices and dates were read through a summarising fetch; `gpt-4.1-nano` shows that a priced row can be a
   shut-down model.
6. Whether the 85% creativity test is met remains P-2's open question; Stage 3 does not score creativity
   before it.
