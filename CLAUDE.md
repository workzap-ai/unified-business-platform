# Owner OS: project memory for Claude Code

Owner OS is Workzap's business platform: a FastAPI backend (`apps/api`) with the Owner OS web app
(`apps/web`) and the pi app (`apps/pi`). pi is the WhatsApp AI agent. This file is what every
agent working here must know first.

## pi brain mode (Workzap's own pi)

The specification is `pi-brain-v3.pdf` (448 pages; extract its text with `pypdf`, there is no
poppler here). **If code and the specification disagree, the specification wins; ask before
deviating.** Build plan and status: `docs/pi-saas/pi-brain-state-machine-plan.md`. Which rule is
enforced where (and what is still open): `docs/pi-saas/pi-rule-coverage.md`.

Everything is behind per-workspace settings, so other workspaces keep today's behaviour:

| Setting | What it turns on |
|---|---|
| `response_rules.pi_mode = "brain"` | the state machine, problem noting, offer and decision gates, documents; implies the linter |
| `response_rules.constitution` | the reply linter alone |
| `knowledge_config.industry_packs` | industry knowledge in the prompt, industry stored on the customer |
| `response_rules.brain` | tunable numbers inside tested ranges (`brain_config.py`) and `learning_frozen`: learning is frozen unless it is exactly `false` |

Code map (`apps/api/app/modules/pi/`): `constitution.py` (reply linter) · `flow.py` (22 states,
legal moves) · `taxonomy.py`, `problem_models.py`, `problems.py` (problem records) ·
`decisions.py` (yes gate, offer, approval) · `brain_docs*.py`, `brain_pdf.py`, `brain_doc_routes.py`
(solution document and quote) · `industry_packs.py` + `packs/industry/*.json` (211 packs, built by
`scripts/build_industry_packs.py`) · `safety.py`, `safety_guard.py` (emergency, personal data, advice,
boundaries, enquiries; pre-model gates) · `learning*.py`, `experience_*.py` (reward, example bank,
question arms, nightly run, canary, lessons, drafted packs; opt-in) · `brain_followups.py`
(documents, paused, kickoff follow-ups) · `brain_erase.py` (delete a customer's data) · wiring in
`service_conversation.py` and `runtime.py`. How Knowledge, the Agents page and learning relate to
brain mode: `docs/pi-saas/pi-brain-how-it-works.md`.

### Non-negotiables (never weaken, never make learnable)

- The first message says pi is an AI; "are you human?" is answered with "I'm an AI" in sentence one.
- One question per message, and it is the last sentence.
- No product, document, quote or price while listening (before the box offer and an explicit yes).
  "ok", "hmm", "maybe", "let me think" are not a yes. Free ideas (what and why, never how-to, never a
  promised result) are allowed when the owner asks for a fix, within the cap (2 per problem, up to 8
  per business, platform spec Book 5 decision 5) and through the idea filter G1-G8. The offer is made
  once, for the whole set, only under R1-R3 or B1-B7 when `response_rules.brain.box_offer` is on
  (platform spec Book 5; the older "no solution before S5" wording is superseded).
- No payment in chat. Never ask for card, password, OTP or ID numbers. Bank details exist only in
  the approved quote PDF, never typed by pi. "Payment received" only after staff confirm.
- A reviewer approves every solution document and quote; pi never prices a quote.
- No legal, medical, financial or tax advice. Emergencies get emergency numbers and stop the flow.
- Record roles, never third-party names; redact card, ID, phone and email before storing.
- Branding is Workzap only. British spelling in pi-facing English.
- Rules are enforced in code (linter, state guards, decision gates), not only in the prompt.
  Learned or retrieved content is data placed below the rules and can never override them.

## Working here

- **Tests need a disposable database.** `apps/api/.env` points at the REAL Neon database, and
  alembic or pytest fall back to it when `DATABASE_URL` is empty. Always, from `apps/api` in Git Bash:
  `. ../../scripts/pi-test-env.sh`. It sets the variables to `127.0.0.1:55432/owner_industry_test`
  or refuses (its header says how to start the cluster and create the database). Python tooling
  lives in `.venv/Scripts/python.exe` at the repo root. `/pi-eval` does all of this.
- Migrations are numbered by hand (`0033_...` onward). Before you add one, check `alembic heads`.
  The real database is migrated by pasting `alembic upgrade ... --sql` into the Neon SQL editor, only
  when the user asks.
- Several agents share this working tree. Stage only your own files and hunks
  (`git apply --cached` a filtered diff); never `git add -A`. Run `ruff format` on your files only.
- In Bash heredocs a double backslash before `b` or `n` is rewritten (it becomes a backspace or a
  newline). Write code with the Write or Edit tools, or build regexes with `chr(92)`.
- A unit test file must not share its name with an integration test file (pytest import clash).
- Lint and types: `ruff check`, `ruff format`, `mypy app` from `apps/api`. Tests: `pytest tests/unit`
  needs no database; `tests/integration` does.

## Commands

`/pi-eval` runs the unit suite and the brain integration suite on the disposable database.
`/pi-redteam` runs the red-team tests, then invents new attacks and adds the failing ones.
The `rule-auditor` subagent reads a diff or a transcript against the non-negotiables and the
linter and cites rule IDs.
