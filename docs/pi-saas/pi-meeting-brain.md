# PI Meeting Brain (PMB)

Meeting Intelligence built inside the existing pi codebase. It feeds the same brain
(Customer Memory, Problem Map, approval desk) that WhatsApp uses. There is no second memory system.

Branch: `pi/meeting-brain`. Flag: `response_rules.brain.meeting_intel` (default off, needs `pi_mode = "brain"`).

## Phases

| Phase | Scope | Status |
|---|---|---|
| PMB-0 | Stabilise: fix stale tests, record baseline | Done (see below) |
| PMB-1 | Meeting-to-Brain core: tables, ingest, transcribe, analyse, approve, apps/web UI | Not started |
| PMB-2 | Brain strengthening: speaker-to-owner mapping, contradiction detection | Not started |
| PMB-3 | Zoom and Google Meet via platform APIs (no bot) | Not started |
| PMB-4 | Native video (LiveKit) | Not started |

## Decisions (owner, 2026-11-05)

- Native video: hosted SDK (LiveKit by default).
- Zoom and Meet: platform APIs after the meeting, no bot.
- Recordings: S3 or R2 with presigned URLs.
- Phase 1: Meeting-to-Brain core.
- UI: `apps/web` first; `apps/pi` later as a thin view over the same API.

## Baseline (2026-11-05, origin/main dc909471, disposable Postgres on :55432)

- Unit suite on clean main: 20,009 passed, 3 failed. All 3 were stale tests after commit 5e4eef66:
  - `test_pi_flow`: `advance_flow` reads `turn._exploration`.
  - `test_pi_live_fixes`: `without_repeats` returns `""` when nothing new is left.
  - `test_pi_roman_urdu_noted`: `solution_context.build` returns `{}` early for practical solution requests.
  Fixed in tests only (commit bdf372f3); the 3 files now pass (99 tests).
- Brain integration (`tests/integration/*brain*.py`, 10 files): 81 passed in 254 s.
- Full integration suite (193 files): not yet run.
- Production: alembic 0056. Migration for PMB-1 will be 0057 (check `alembic heads` first).

## Reuse (no duplicates)

- Memory writes: `pi/memory_ledger.py` (`record_decision`, `redacted`); meeting facts use a namespaced
  `subject_ref` such as `meeting:<id>:...` because `pi_decisions.kind` is fixed in production.
- Problem Map: `pi/problems.py` (`apply_ops`, `check_ops`). Lines from a speaker not mapped to the
  customer land as `draft` / `pi_inferred`.
- Approval desk: `pi_saas/requests.py raise_request`.
- Jobs: ARQ (`worker.py`, `core/jobs.py`), idempotent job ids `meeting:<id>:<stage>`, resumable after a restart.
- Storage: `integrations/providers/s3.py` with `scoped_key`.
- Erase and export: every new table must be added to `brain_erase.py` and the customer export.

## Rules that apply to meetings

- AI conclusions are stored with a `basis` (stated, inferred, estimate, recommendation) and never
  written to memory as customer facts without approval.
- Redact card, ID, phone and email before storing; roles, not third-party names.
- Audit records hold ids only, never transcript text (audit truncates at 300 chars).
- Recording needs explicit consent per meeting. Proposed default: audio kept 90 days, transcript until customer erase.
- A quote or document derived from a meeting still needs reviewer approval; the module never prices.

## Needed from the owner before activation

S3 or R2 bucket and keys, STT provider keys and budget, consent and retention decision, and (for
production) the migration pasted by the owner. Phase 3 needs a Zoom app and Google OAuth verification.
