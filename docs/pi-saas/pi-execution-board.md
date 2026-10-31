# PI execution board (shared task and status record)

One record for every session and agent. The approved A to G plan, the three-level architecture
(Level 1 understand, Level 2 solution intelligence, owner approval gate, Level 3 controlled execution),
the seven spec PDFs (text under `docs/pi-saas/spec-text/`) and the execution addendum in
`docs/pi-saas/pi-fast-track-plan.md` stay the source of truth. This board adds no scope.

**Single writer: the integrator session.** Everyone else reports by message (branch, hash, files, results) and
never edits this file. Snapshot of 2026-10-31, `origin/main` = `eee5222`. A row is "done" only with working code, tests
that fail without it, and an independent review. A plan, schema, prompt or fixture existing is not completion.

## Rules every agent follows

- Own worktree and own branch from `origin/main`. Never touch another lane's worktree or branch. Never `git add -A`.
  No reset, clean, blind stash, force push, rebase of shared branches, or history rewrite.
- No push or merge without the integrator. FT-02 additionally needs the owner's direct confirmation.
- Tests: from `apps/api` source the verified environment (`. "E:/COMPANY-ENGINEERING-HQ/05-COMPANY-SYSTEM/Owner OS/scripts/pi-test-env.sh"`); it must print
  `127.0.0.1:55432/owner_industry_test`. Never run with an empty `DATABASE_URL` (`apps/api/.env` points at the real database).
  Integration tests take `.cache/test.lock` with a mkdir loop and never remove another process's lock. Report the printed line.
- No production migration, deploy, real-model spend or external action without the owner. Migrations are numbered by hand
  after `alembic heads` (`0053` and `0054` are on main; next free `0055` is assigned only by the integrator).
- The implementer never approves its own work: a different agent audits critical changes. Report: exact branch, commit,
  files, commands, results, limits.
- Non-negotiables in `CLAUDE.md` are never weakened or made learnable.

## Hot files (owner of the lane until it merges; nobody else edits them)

`service_conversation.py`, `problems.py`, `decisions.py`, `part19.py`, `brain_docs.py`, `box_doc.py`, `idea_filter.py`,
`expert_advisor.py`, `flow.py`, `runtime.py`. Owner today: the FT-02 lane (`pi/s-ft02-eighth-draft`). Wiring into these
files waits for FT-02 and is done by one agent at a time.

## In flight

| ID | What | Owner | Branch (worktree) | Files | Depends on | Acceptance | Status |
|---|---|---|---|---|---|---|---|
| FT-02 | Part 19, D-1 fail-closed quote gate, offer-gate recall fix | integrator agent | `pi/s-ft02-eighth-draft` (`s8draft`) | part19, decisions, service_conversation | owner confirmation to push | unit and full integration equal the 23-failure baseline; audit PASS | tip `f4b075a` + offer-gate fix in progress |
| L2-1 | Hard constraint gate, option gate, requirements read side (B2a fields) | integrator agent | `pi/l2-hard-gate` (`l21`) | new: requirements_read, constraint_check, option_gate + tests | none | failing tests first; statements never reject; hard violation rejects whatever the score; works on a DB without the 0053 columns | in progress |
| FT-A3-fix | HIGH findings of the inflection scorer, honest DISCLAIMER; offline tool only | integrator agent | `pi/e-a3-inflection` (`a3b`) | evalkit/relevance*.py + tests | none | independent re-audit PASS; Development core 66/66 | in progress |
| SAF | GAP-3, GAP-4 safety patterns, life-safety fix | owner-os-ac | `pi/safety-gap3-gap4` (`safety`) | safety.py + tests | none | independent audit PASS (adversarial emergency strings) | `8a7621a`, audit running |
| BL-04 | denied audit: per-tenant cap, semaphore, retry rule, identity-level denials | owner-os-50 | `pi/bl-04-denied-audit` (`bl04`) | audit/denials.py, exceptions.py, scope.py + tests | none | audit PASS | fixes in progress |
| L1-PLAN | Level 1 completion plan against the seven PDFs (read-only) | integrator agent | none | none | none | cited requirement list, status, order | in progress |

## Assigned this round (new, non-conflicting)

| ID | What | Owner | Branch (worktree) | Files | Depends on | Acceptance |
|---|---|---|---|---|---|---|
| L2-2 | Root-cause scripted criteria and labelled cases (supported, hypotheses apart, both sides, factors named) | owner-os-65 | `pi/l2-root-cause` (`l22`) | new: evalkit root_cause module, cases file, tests | none | negative controls fail; per-language n reported; Held-out untouched |
| L2-3 | Options record and ranking (smallest reliable first, two-option minimum, `learn_first` valid) | owner-os-6b | `pi/l2-options-record` (`l23`) | new: blueprint_models.py, blueprint_rules.py + tests | none | typed records; unit tests fail without the rules |
| E2 | Tenant isolation: two-tenant leakage tests for the by-id queries in the plan (learning_audit trace, learning_gate replay_regressions, brain_doc_routes, brain_visual_queue/routes, experience_scorer, learning_situation) | owner-os-eb | `pi/e2-tenant-scope` (`e2`) | tests first, minimal scoping fixes | none | failing reproduction per unscoped query; fix only what is really unscoped; confirmed leak reported to the owner at once (G3), no production change |

## Waiting on an owner decision (do not start)

| Item | Why it waits |
|---|---|
| FT-02 push to `origin/main` | owner's direct confirmation |
| SEC-1 (`pi/sec-1-unverified-invite`, `f612560`) | product design: every invite pending for existing accounts, no invite link, UI changes |
| `quotes.approve` (`pi/quotes-approve-permission`, `14cc8da`) | sales role loses approval of pi documents |
| Real-model replay, Neon migrations `0053` and `0054` | key, budget, owner runs the SQL (`docs/pi-saas/migrations-0053.sql`, `migrations-0054.sql`) |
| Erase R1 and G11 to G14, retention | owner |
| FT-A3 human reviewers, solar probe generator | owner |

## Next, after dependencies clear

| ID | What | Waits for |
|---|---|---|
| L2-4 / FT-C1 | relevance in code (problem link, fact reuse, constraint fit) | L2-1 merged and FT-A3-fix audited, then FT-02 (idea_filter.py is hot) |
| L2-wire | call `requirements_read` and `option_gate` from solution context and document drafting | FT-02 merged |
| B2b and `note_problems` passes the owner message | extractor fills the B2a fields; makes `owner_said` reachable | FT-02 merged (problems.py, service_conversation.py are hot) |
| GAP-1, GAP-2 | Roman Urdu correction ("10 nahi, 100"), trade words before a quote ask | FT-02 merged (box_signals, decisions) |
| L2-6 | blueprint table, migration `0055` or later, erase hook | owner decision D8 on the new table |
| `44f40b9` warm-up fix | unique commit kept on `recovery/local-main-4-commits`; integrate after FT-02 (known content conflict in service_conversation.py) | FT-02 merged |

## Merge order (fast-forward only, each after its gates and an independent audit)

1. Items with no hot file and a passing audit: SAF, BL-04, L2-1, FT-A3-fix, L2-2, L2-3, E2.
2. FT-02 (owner confirmation), then the hot-file items in the "Next" table, one at a time.
3. Owner-dependent items when the owner decides.

## Measured status today (honest)

- Verified industries: 0 of 211. Real-model verified features: none. Scripted measures only.
- Level 1: fields exist (B2a) but nothing writes them; owner_said is fail-closed and unreachable until the owner message is passed.
- Level 2: nothing reads the stored constraints, tried or cause yet (L2-1 builds the read side and the gate).
