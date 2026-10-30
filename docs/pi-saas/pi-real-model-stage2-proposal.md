# P-5 Stage 2: the real extractor on the Held-out set (PROPOSAL, nothing is approved or run)

2026-10-30. Status: **proposal document only.** No model call has been made, no key exists, nothing
is spent, the runner is unchanged. Stage 1 (Development, 30 calls, USD 0.50) is the only stage the
owner has approved, and it has not been run. Stage 2 needs its own explicit run approval.

Words used: **scripted** = automated test with no model; **real-model** = measured on an actual model.
Stage 2 would be the first real-model measurement on Held-out. Until it runs, no Held-out claim exists.

## 1. Purpose and the order it must follow

Measure how often the real extractor keeps what the owner said on cases it was never tuned on.
Order: Stage 1 runs first and its Development results are reviewed by the owner; D5 thresholds are
approved; only then is Stage 2 considered. Stage 2 may not start if Stage 1 found a runner defect.

## 2. Model (exact IDs, availability, deprecation)

What production uses today: the extractor calls alias `fast` (`problem_extract.py:135`), a synonym of
`router`, whose default is `gpt-4o-mini` (`app/ai/registry.py:40`). Settings (`OPENAI_MODELS`) can
pin another model, so **what production actually runs is unverified**; the owner reads the setting.

Verified from OpenAI's pages on 2026-10-30 (summarising fetch; the owner re-checks on the dashboard):

| Model ID | Input | Cached input | Output (USD per 1M tokens) | Status |
|---|---|---|---|---|
| `gpt-4o-mini` | 0.15 | 0.075 | 0.60 | deprecated: snapshot `gpt-4o-mini-2024-07-18`, shutdown "January 14, 2027", replacement `gpt-6-luna` |
| `gpt-6-luna` | 0.10 | 0.01 | 0.50 | no shutdown note found |
| `gpt-5.6-luna` | 0.20 | 0.02 | 1.20 | no shutdown note found |
| `gpt-5.4-mini` | 0.75 | 0.075 | 4.50 | no shutdown note found |

Sources: `https://developers.openai.com/api/docs/pricing` and
`https://developers.openai.com/api/docs/deprecations`, read 2026-10-30. The deprecations page does not
list `gpt-5.4-mini`, `gpt-6-luna` or `gpt-5.6-luna` as deprecated; absence is not a guarantee.

**Decision needed: which model Stage 2 uses.** It must be the same model as Stage 1, otherwise the two
results cannot be compared, and it should be the model production will use after 14 January 2027
(`gpt-6-luna` is OpenAI's named replacement). Only `gpt-4o-mini` matches what the extractor was
written and tested against; a different model needs the Stage 1 result first.

**Availability check the owner runs** (it uses your key, not mine; a model listing call costs nothing):
`curl -s https://api.openai.com/v1/models/<model-id> -H "Authorization: Bearer $OPENAI_API_KEY"` for
each candidate. A 404 or a "does not exist" answer means the key cannot use it. Also check the three
prices on the dashboard. Whether `gpt-6-luna` accepts `max_tokens`, `temperature` and JSON mode is
**not verified** (its page does not say); the Stage 1 runner sends `max_completion_tokens` and no
temperature for it, which is an assumption. An answer cut off by the token limit shows as an invalid
output.

## 3. Dataset (exact, from `evalkit/cases/extraction.json` at `origin/main` cc462c5)

| Part | Cases | Languages | Kinds |
|---|---|---|---|
| Held-out (`splits.split_of`, stable hash, 25%) | 60 | en 25, roman_ur 23, ur 8, ar 4, **hi 0** | list 18, single 21, correction 8, mixed 3, constraints 4, multi_turn 3, rant 3 |
| Regression (never removed) | 3 | en 3 | list 2, correction 1 |

Total 63 calls, one per case, as in Stage 1. 52 industries appear in Held-out. Message length: average
128 characters, at most 249; at most 3 messages per case. Development is not part of Stage 2.

Consequences, stated now so no result is oversold: Urdu script (8), Arabic (4) and Hindi (0) are below
any plausible language minimum, so those cells are reported "not yet measured", never "passing". No
industry has 10 cases. D5 sets the minimums; they are **pending** and no threshold is used here.

**Held-out use rules.** Open once. Before the run the owner approves; the access is recorded with
`splits.held_out_access(log, who, why)` next to the result file; results are never used to tune a
prompt, extractor or scorer. If the run stops early (HTTP error, cap), the partial result is reported
as partial; a re-run is a second access and needs a new approval. A change to a threshold after seeing
results needs the owner and is logged (plan, operational definition 5).

## 4. Calls, tokens and the hard budget cap

Input per call at the worst case: the extractor prompt is 2,161 characters of rules plus a 2,912-
character category list; the longest message is 249 characters. At 2 characters per token that is
ceil((2,161 + 2,912 + 249) / 2) + 60 framing = **2,721 input tokens**, plus the full
`max_tokens` of **1,500** output tokens (`problem_extract.py:142`). Cached-input discounts are ignored
(conservative). Per call = (2,721 x input rate + 1,500 x output rate) / 1,000,000.

| Model | Per call, worst | 63 calls, worst | Proposed hard cap | Calls that fit USD 0.50 |
|---|---|---|---|---|
| `gpt-4o-mini` | USD 0.001308 | USD 0.0824 | USD 0.10 | 382 |
| `gpt-6-luna` | USD 0.001022 | USD 0.0644 | USD 0.10 | 489 |
| `gpt-5.6-luna` | USD 0.002344 | USD 0.1477 | USD 0.20 | 213 |
| `gpt-5.4-mini` | USD 0.008791 | USD 0.5539 | USD 0.60 | 56 |

The cap is the worst case rounded up; a realistic run (about 1,400 tokens in, a few hundred out) costs a
fraction of it. **The cap is hard**: the runner stops before a call whose worst case would pass it, and
the spend is updated from the provider's `usage` after each call. If the owner wants a cap below the
worst case, the calls are cut (never the cap raised): for example 56 calls on `gpt-5.4-mini` at USD 0.50.
Token counts are estimates (no tokenizer is installed); the guard relies on the provider's `usage`.

## 5. Stop rules and runner changes (none made now)

Reuse every Stage 1 control (`pi/e-d6-runner`): dry run by default; a real run needs `--execute`, the
key in the shell's environment only, `--confirm-cap` repeating the plan, and `--out` as a new file under
`.cache` or the temp folder; one call at a time; refuse a call whose worst case passes the cap; stop on
any HTTP error, network error, malformed output or a different answering model than the configured one;
the client ignores proxy and certificate variables and follows no redirects; one result line per case as
it arrives; the key never appears in output.

**Required runner change before Stage 2 (not done, needs approval):** the runner refuses any split but
`development`. Stage 2 needs a `held_out` split that can only be selected together with a Held-out
approval token written by the owner (a file or argument naming the date and cap), and that writes the
access record. This is the only way Held-out gets opened, and it must have its own test.

## 6. Key handling

A new dedicated key, auto-reload off, a provider-side limit of USD 5 or less, revoked after the run. The
owner creates it and types it into the shell; Claude never sees, stores or logs it. No key is created
by this proposal.

## 7. Scoring (scripted code, reused from `evalkit`)

Recall, precision, kept figures and applied corrections per language and kind, with n; a cell under 3
cases is "not yet measured"; the `constraint_kept` scorer. Invalid outputs are counted and printed. No
pass or fail threshold is applied: **D5 is pending**. The Stage 1 Development figures are the only
comparison point.

## 8. What Stage 2 can and cannot claim

Can: how often the real extractor keeps what the owner said on 63 unseen cases, per language with its n.
Cannot: reply quality, solution relevance, creativity, plan depth, multi-turn behaviour of the whole
pipeline (those are Stage 3); anything about Urdu script, Arabic or Hindi at a useful sample size;
industry verification; any statement that production quality is acceptable.

## 9. Owner approval checklist (every box needs your explicit yes)

1. Stage 1 was run, reviewed and had no runner defect.
2. D5 thresholds and language scope approved.
3. Model ID chosen; availability checked by you; three prices checked on the dashboard.
4. Hard cap chosen (table above) and the 63-case scope accepted.
5. Runner change for the guarded Held-out split reviewed and merged by approval.
6. A new key with auto-reload off and a provider limit, created by you; revoked after.
7. A run date and who is recorded in the Held-out access log.
