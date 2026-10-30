# P-5: provider-level spend guard for Stage 3 (design only, no code)

2026-10-30. Status: **PROPOSED design, nothing implemented or tested.** No model call, no key, no
spending, no code, no runner change. The only **APPROVED** real-model decision is Stage 1 (30 calls, hard
maximum USD 0.50, Development, extractor only). This guard is the new component that Stage 3 needs
(roadmap conflict C9); building it is **not approved** and needs a separate decision. Status words:
documented (this file), implemented (none), scripted-tested (none), real-model-verified (none).

## 1. Why a guard at this layer

The Stage 1 runner calls one endpoint from one script. Stage 3 runs the real reply pipeline, which makes
up to 7 logical model calls per turn (10 with the shape fallback) through `LLMManager`, with retries and
provider failover (`pi-real-model-cost-verification.md` section 3.3). Controls therefore have to sit
where every HTTP attempt passes, not in a script that sees only its own calls.

## 2. What already exists in `app/ai` (reuse, do not duplicate)

| Existing piece | Where | What it does | Why it is not enough alone |
|---|---|---|---|
| `BudgetGuard` | `app/ai/usage.py:165-191`; called at `app/ai/manager.py:416` | before each call, refuses when the **tenant's UTC-day** token or cost total, summed from stored usage events, is at or over `ai_tenant_daily_cost_limit` / `ai_tenant_daily_token_limit` (`app/core/config.py:124`) | it checks spend **already recorded**, not the next call's worst case ("a single in-flight call can overshoot by its own usage", `usage.py:168`); it needs a database; the limit is per day and per tenant, not per run; default off |
| `PriceTable.estimate` | `app/ai/registry.py:81-104` | cost from token counts | `DEFAULT_PRICES` is "approximate list prices; UNVERIFIED" (`registry.py:82`); the guard must use the owner-verified table instead, not this one |
| `UsageTracker` / `UsageRecord` | `app/ai/usage.py:147-160`, `:197` | one `ai_usage_events` row per attempt, "never contain prompts, outputs, media or keys" | good model for the audit log; it writes to the database, so the evaluation run keeps its own file log |
| `FallbackPolicy` | `app/ai/manager.py:88-110`; `llm_max_retries` default 1 at `app/core/config.py:105` | retries and tries other providers | multiplies calls and can change the answering vendor and model |
| `LLMResponse.provider`, `.model`, `.usage` | `app/ai/types.py:157-167` | what answered and how many tokens | usable for the settle step and the model check |
| `follow_redirects=False` | `app/ai/providers/base.py:148` | no redirects | `trust_env` was not found in a grep of `app/ai`; the httpx default is to read proxy variables, so the run must pass its own client with `trust_env=False` (to be confirmed in code) |

Decision for the design: the existing `BudgetGuard` is kept as a **second line of defence** (set
`AI_TENANT_DAILY_COST_LIMIT` for the evaluation tenant to the same cap), and the new guard is the
**first line**, because only the new guard pre-charges the worst case.

## 3. Where it sits

One small object, `SpendGuard`, owned by the evaluation process only (never constructed in production
code paths). It wraps each provider adapter inside `ProviderRegistry.providers`
(`app/ai/registry.py:107-135`, used at `app/ai/manager.py:420`, `:433`, `:470`) so that
`adapter.complete(request)` becomes `guard.call(adapter.complete, request)`. This is below `LLMManager`,
so every retry and every fallback attempt is counted, and above the HTTP client, so the request's size
and `max_tokens` are known before it is sent. Production code is unchanged; the wrapper is applied by the
evaluation entry point after the registry is built.

The guard must raise a `BaseException` subclass (`RunStopped`), as in the Stage 1 runner. The manager
contains adapter failures with `except Exception` (`app/ai/manager.py:473`) and would otherwise swallow a
stop and carry on to the next provider.

## 4. Controls (each is a hard rule in the design)

1. **Dry run by default.** With no `--execute` the process builds the plan and the per-step worst-case
   table and prints them; it constructs no HTTP client and reads no key.
2. **Per-call worst-case pre-charge.** Before the call: input tokens = (characters of all message text)
   / 2 + 60, plus `request.max_tokens` as the output allowance; price from the **owner-verified table
   passed on the command line** (`pi-real-model-cost-verification.md` section 2), never `DEFAULT_PRICES`.
   Refuse (raise `RunStopped`) if spent so far plus this worst case would exceed the hard cap.
3. **Usage-based settle.** After the call: spent += cost from `response.usage` at the verified rate. No
   `usage` counts as the worst case. A call that failed after it was sent counts as the worst case.
   Negative usage cannot lower the total.
4. **Hard stop.** Any HTTP error, a malformed output, a model other than the configured one
   (`response.model`), a different provider, reaching the call cap, or reaching the dollar cap ends the
   whole run at once; the stop is not retried or skipped.
5. **One attempt per call.** The evaluation process sets `LLM_MAX_RETRIES=0`, does not enable
   `ai_failover_all_configured`, limits the provider order to OpenAI, and pins `OPENAI_MODELS` to the
   chosen IDs, so a call is exactly one HTTP attempt on the intended model. The guard asserts these
   settings at start and refuses to run otherwise.
6. **Kill switch.** The guard checks, before every call, an environment variable and a flag file (a
   path under `.cache`, created by the owner with one command). Either stops the run before the next call.
   A wall-clock limit and a maximum number of turns also stop it.
7. **One call at a time.** No concurrency, so the pre-charge and the settle are exact.
8. **Audit log without message text.** One JSON line per attempt appended as it happens (so a crash loses
   nothing): sequence number, UTC time, purpose, alias, provider, model, input and output character
   counts, token counts, worst-case charge, settled cost, running total, status, stop reason. **Never**
   message text, prompts, outputs, names, phone numbers or the key. The output file must be new and under
   `.cache` or the temp directory, checked before the first call.
9. **Key handling.** The key exists only in the environment of the owner's shell (a new dedicated key,
   auto-reload off, a provider-side limit not above the cap, revoked after the run); the process reads
   no `.env`, imports no settings file with a key, and never prints, logs or stores it. The HTTP client is
   built with `trust_env=False` and no redirects, so proxy and certificate variables cannot redirect it.
10. **Disposable database only.** The run refuses to start unless the database URL is the disposable
    one (the `pi-test-env.sh` recipe); `apps/api/.env` is the real database and is never used.
11. **Held-out access.** The Held-out split opens only with an owner approval token and is logged once
    (`splits.held_out_access`), as in the Stage 3 proposal.

## 5. Tests (scripted, with a mock transport; no network)

Written first and seen failing, run under `httpx.MockTransport` and a fake adapter:

1. A call whose worst case passes the cap is refused before it is sent (counter shows zero sends).
2. Spend is settled from `usage`; a response without `usage` is charged the worst case; negative usage
   does not lower the total.
3. A failed or timed-out call is charged the worst case.
4. A 401, 429 and 5xx each stop the whole run; with retries 0 there is exactly one HTTP attempt per call.
5. A different answering model or provider stops the run.
6. The stop cannot be swallowed by the manager's `except Exception` (`RunStopped` is a `BaseException`).
7. Reaching the call cap stops the run; the call cap and dollar cap cannot be raised above the approved
   maximum by arguments.
8. The kill-switch variable and the flag file each stop the run before the next call.
9. The audit log never contains message text, a phone number or the key (assert on the file contents).
10. The settings assertions (retries 0, failover off, provider order, pinned models) refuse a bad
    configuration.
11. Proxy and certificate environment variables do not change the target host (`trust_env=False`).
12. A dry run makes no client and reads no key.
13. A prompt-size drift test: the guard's pre-charge for a recorded request is not below the usage
    reported for it (guards against the 2 characters per token rule being too optimistic for Urdu or
    Arabic script).

## 6. Dry-run procedure the owner can approve before any run

All steps are free and need no key.

1. Start the disposable database (the `pi-test-env.sh` recipe); confirm the database URL is the
   disposable one.
2. Run the evaluation entry point **without** `--execute`, with the verified price table and the chosen
   variant (minimal, lower or full). It uses the **scripted model** (the existing replay path), so no
   HTTP call is made.
3. For each scripted turn it renders the real system text and context for every step, prints the
   character and estimated token count per step (replacing the assumptions in
   `pi-real-model-cost-verification.md` section 3), the per-turn and per-run worst case, and the number
   of calls.
4. The owner reads the table, compares the run's worst case with the proposed hard cap, and either
   reduces conversations or turns, or approves. The cap is never raised to fit.
5. Only then, in a separate message, the owner approves the run, creates the key, sets the provider
   limit, and starts the run in their own shell.

## 7. Dependencies, conflicts and open decisions (all PROPOSED)

- **Depends on:** FT-02 integrated (so the replies tested are the replies that ship); Stage 1 run and
  reviewed; D5 approved; the P-2 conversation case format and labelled samples; Held-out conversation
  cases (only 3 multi-turn Held-out cases exist today).
- **Roadmap conflict C9 confirmed:** FT-REPLAY is budgeted at 0.5 day for 30 calls; this guard and a
  dry-run harness are new code with their own tests and review, so FT-REPLAY's effort for Stage 3 is
  understated. Not changed here; for the owner.
- **Open:** where the evaluation entry point lives (`apps/api/scripts/`, next to the Stage 1 runner, is
  proposed); whether `trust_env` is already disabled in the provider HTTP client; which retry and failover
  settings the owner wants for the run; who reviews the guard code before any key exists.
- **Not verified:** nothing here was run; the line references were read from `cc462c5`; whether a
  provider response always carries `usage` was not checked in the adapters.
