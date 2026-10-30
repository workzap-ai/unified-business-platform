# D6: the real-model sample (stage 1 approved with conditions; nothing has been run)

2026-10-30. Owner decision on D6: **stage 1 only, a hard maximum of 30 calls and USD 0.50, conditional
on verifying real provider pricing and the token estimate first; if the estimate exceeds the cap,
reduce calls and never raise the budget.** Stages 2 and 3 are **not approved**. No key has been
created or used. The runner is finished, tested and waiting for the owner's review
(`scripts/pi_real_eval.py`, `tests/unit/test_pi_real_eval.py`).

## 1. Verified models and pricing (looked up 2026-10-30, not assumed)

Sources (OpenAI developer docs, read 2026-10-30 through a summarising fetch):
`developers.openai.com/api/docs/pricing`, `.../api/docs/deprecations`, `.../api/docs/models/gpt-4o-mini`,
`.../api/docs/models/gpt-6-luna`. Please check the prices on your dashboard.

| Model | Input / 1M | Cached input / 1M | Output / 1M | Status on the deprecations page |
|---|---|---|---|---|
| `gpt-4o-mini` (the extractor's `fast` alias) | 0.15 | 0.075 | 0.60 | **Deprecated; removed 2027-01-14**; replacement `gpt-6-luna` |
| `gpt-6-luna` | 0.10 | 0.01 | 0.50 | none; the named replacement |
| `gpt-5.6-luna` | 0.20 | 0.02 | 1.20 | none |
| `gpt-5.4-mini` (pi's brain model) | 0.75 | 0.075 | 4.50 | none |

Not offered: `gpt-4.1-nano` (shut down 2026-10-23, already gone), `gpt-5-nano` and `gpt-5-mini`
(shut down 2026-12-11), `gpt-4.1-mini` (2027-01-14), `gpt-5.4-nano` (2027-04-01).

The registry maps the extractor's `fast` alias to `router`, whose default is `gpt-4o-mini`
(`app/ai/registry.py:30,40`); an operator setting can pin another model, so the model really in use
in production must be read from settings by you. `gpt-4o-mini` still works until 2027-01-14.

What could **not** be verified: whether `gpt-6-luna` and `gpt-5.6-luna` accept `max_tokens`,
`temperature` and JSON mode (the model page does not say; it lists structured outputs and reasoning
tokens, and says nothing on whether reasoning tokens are billed as output). The runner therefore sends
the classic fields only to `gpt-4o-mini` and `max_completion_tokens` with no temperature to the other
models; that is an assumption, and one HTTP error ends the run at once. `gpt-4o-mini` is the only model
whose request fields match what the extractor was tested with.

## 2. Token estimate and worst case (dry runs, nothing sent)

- The extractor's prompt is 2,161 characters of rules plus a 2,912-character category list, plus the
  owner's message (evaluation cases average 128 characters, at most 249).
- The runner builds each request without sending it and prices the worst case: input at **2 characters
  per token** (about double what English needs) plus 60 framing tokens, plus the **whole** output
  allowance of 1,500 tokens. Same 30 Development cases for every model.

| Model | Worst case per call | Worst case, all 30 calls | Cap |
|---|---|---|---|
| `gpt-4o-mini` | USD 0.001286 | **USD 0.038398** | USD 0.50 |
| `gpt-6-luna` | USD 0.001007 | **USD 0.030098** | USD 0.50 |
| `gpt-5.6-luna` | USD 0.002315 | **USD 0.069197** | USD 0.50 |
| `gpt-5.4-mini` | USD 0.008681 | **USD 0.259488** | USD 0.50 |

All four fit under the cap with all 30 calls, so no call is dropped. For reasoning models
`max_completion_tokens` bounds reasoning plus visible output, so the worst case still holds, but an answer
may be cut off (it then counts as an invalid output). `tiktoken` is not installed, so token counts are
estimates; the runtime guard uses the provider's own `usage`.

## 3. What the runner does and refuses

- **Dry run by default**: builds the plan, prints the numbers, makes no network call and reads no key.
- A real run needs all of `--execute`, `OPENAI_API_KEY` in the environment of the shell that runs it
  (never an argument or a file; the runner reads no `.env`, imports no settings, touches no database),
  `--confirm-cap` repeating the plan (for example `"30 calls USD 0.50"`), and `--out`.
- **Development only**: `--split` accepts nothing else; there is no flag to open Held-out or
  Regression. `--max-calls` above 30 or `--max-usd` above 0.50 is refused. `--model` defaults to
  `gpt-4o-mini`; a model outside the verified table is refused, and the token prices are required
  arguments that must be at least that model's verified rates. The answering model must match the
  configured one or the run stops.
- One process, one call at a time. Before each call: refused if the spend so far plus that call's
  worst case would pass the cap. After each call: the spend is updated from the provider's `usage`
  (no `usage` counts as the worst case). A failed call counts as a call.
- Any HTTP error (401, 429, 5xx), a network error, a different model than expected, or reaching the
  call cap ends the whole run at once. The stop is a `BaseException`, so the extractor's own
  `except Exception` cannot swallow it and carry on.
- The request asks for JSON mode, so the system message gets one added line, "Reply with a JSON
  object." That is the only change to the extractor's prompt and it is stated here.
- Inputs are the evaluation cases only (text written for the evaluation); no real customer message
  is sent. The raw model output goes to the `--out` file you name (keep it out of git); the key
  never appears in the output or the file (a test checks this).
- Scoring reuses `evalkit` (recall, precision, kept figures, applied corrections per language and
  kind, with n; a cell under 3 cases is "not yet measured").

## 4. What this run can and cannot tell

It can tell how often the real extractor keeps what the owner said on Development text. It cannot
tell reply quality, solution relevance, or anything about Held-out, and no threshold is used as a gate
until D5 is approved.

## 5. Before any key exists (needs your approval)

1. Review the runner and its tests (an independent read-only security review is recorded in the
   branch report).
2. Check the three prices on your dashboard and tell me whether `gpt-4o-mini` is still available to
   your key.
3. When you approve, you create a new dedicated key, auto-reload off, provider-side limit of USD 5,
   revoked after the run, and type it into the shell yourself; I never see or store it.

## 6. Independent security review and what changed because of it

A separate read-only reviewer examined the runner at commit 5f67625 without my conclusions. Its verdict:
no way found to leak the key, open Held-out or Regression, or pass 30 calls or USD 0.50. It listed
hardening gaps, all fixed in the second commit and each now covered by a test:

| Finding | Fix |
|---|---|
| A proxy or certificate environment variable could redirect the key (the HTTP client trusted the environment) | the client ignores proxy and certificate variables and follows no redirects |
| NaN or a mistyped low price switches the dollar guard off | prices and the cap must be finite; prices must be at least the verified rates (0.15 in, 0.60 out) |
| A paid run could lose all its results (written only at the end; a malformed answer or an unwritable `--out` crashed it) | one line per case as it arrives; `--out` must be a new file under `.cache` or the temp directory, checked before any call; a malformed or non-object answer, bad `usage` or any unexpected error ends the run with the report and file kept |
| The spend could be understated on a stop (a call that failed after it was sent) | every failure after a send is charged the worst case; negative usage cannot lower the spend |
| Invalid model output looked like a miss | counted and printed as `invalid_outputs` |
| The call-cap stop was unreachable in a normal run and untested | tested on the manager directly |
| `--confirm-cap` is a typo guard, not an authorisation | stated: the owner's approval is the authorisation; a dead `if True` removed |

Remaining limits, stated: token counts are an estimate (no tokenizer installed), so the spend guard
relies on the provider's `usage` and the worst-case bound; the evaluation cases are text written for
the evaluation but were not proven free of real identifiers beyond a pattern search; the provider's
real behaviour (billing on a timeout, availability of `gpt-4o-mini`) is not verified. 40 tests, no
network.

## 7. Model made configurable (2026-10-30)

`--model` selects a model from the verified table; the table holds the lowest accepted rates per
model; the stop on a different answering model uses the configured one; the report names it. Tests
(47 in all, 7 new): default model, unknown model refused, per-model price floor, caps hold for every
model (31 calls and USD 0.51 refused, worst case at most USD 0.50), the configured model is sent with
the reasoning-model fields, a mismatching answer stops the run, the report names the model.
