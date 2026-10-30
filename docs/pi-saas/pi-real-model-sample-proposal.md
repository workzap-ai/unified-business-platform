# D6: the real-model sample (stage 1 approved with conditions; nothing has been run)

2026-10-30. Owner decision on D6: **stage 1 only, a hard maximum of 30 calls and USD 0.50, conditional
on verifying real provider pricing and the token estimate first; if the estimate exceeds the cap,
reduce calls and never raise the budget.** Stages 2 and 3 are **not approved**. No key has been
created or used. The runner is finished, tested and waiting for the owner's review
(`scripts/pi_real_eval.py`, `tests/unit/test_pi_real_eval.py`).

## 1. Verified pricing (looked up, not assumed)

Source: OpenAI's model page for GPT-4o mini (`developers.openai.com/api/docs/models/gpt-4o-mini`),
read 2026-10-30; the launch announcement gives the same figures.

| | per 1M tokens |
|---|---|
| input | USD 0.15 |
| cached input | USD 0.075 |
| output | USD 0.60 |

Limits on the page: context 128,000, max output 16,384. **The page marks the model "Deprecated"**
with no shutdown date and no named replacement. The registry maps the extractor's `fast` alias to
`gpt-4o-mini`. Consequences, handled in the runner and to be confirmed by you:
- the provider may refuse the model or answer with another one; the runner stops at the first HTTP
  error and stops if the answering model is not `gpt-4o-mini`; it never switches model silently;
- a replacement model would need its own verified rates and your approval before any run.
The page is read through a summarising fetch; please check the three prices on your dashboard.

## 2. Token estimate and worst case (measured, then made pessimistic)

- The extractor's prompt is 2,161 characters of rules plus a 2,912-character category list, plus the
  owner's message (the evaluation cases average 128 characters, at most 249) and a small JSON wrapper.
- The runner builds the exact request for each case without sending it (a dry run), then prices the
  worst case: input at **2 characters per token** (English needs about 4, so this is about double)
  plus 60 tokens of framing, plus the **whole** output allowance of 1,500 tokens (`max_tokens`).
- Dry run on the 30 Development cases chosen (English 14, Roman Urdu 13, Urdu script 3):
  worst case **USD 0.001286 per call and USD 0.038398 for all 30 calls**, against the USD 0.50 cap.
  The estimate does not exceed the cap, so no call is dropped. A realistic run (about 1,400 tokens
  in, a few hundred out) is a fraction of the worst case.
- `tiktoken` and the `openai` package are not installed here, so token counts are not exact; the
  runtime guard below uses the provider's own `usage` and so does not depend on this estimate.

## 3. What the runner does and refuses

- **Dry run by default**: builds the plan, prints the numbers, makes no network call and reads no key.
- A real run needs all of `--execute`, `OPENAI_API_KEY` in the environment of the shell that runs it
  (never an argument or a file; the runner reads no `.env`, imports no settings, touches no database),
  `--confirm-cap` repeating the plan (for example `"30 calls USD 0.50"`), and `--out`.
- **Development only**: `--split` accepts nothing else; there is no flag to open Held-out or
  Regression. `--max-calls` above 30 or `--max-usd` above 0.50 is refused. The token prices are
  required arguments with no default.
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
