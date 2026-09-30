# Pi WhatsApp SaaS: implementation status (working file)

Started 2026-09-29 from `docs/PI_WHATSAPP_SAAS_CLAUDE_PROMPT.md`. The full handoff,
including diagrams, permission matrices, setup and the requirement matrix, is
**[PI_SAAS.md](PI_SAAS.md)**.

## Current state (30 September 2026)

- **Backend:** 576 passed, 1 skipped, 0 failed on a disposable PostgreSQL 17 DB; mypy
  and ruff format clean. One ruff I001 remains in migration 0008 (billing peer's file).
- **`apps/pi`:** build, lint, typecheck and Playwright 16/16.
- **`apps/web`:** lint and typecheck clean; demo Playwright 43/43.
- **Live local journey** (`.cache/pi-saas/live/journey2.mjs`, mock Kapso): customer
  payments (PKR, Meezan IBAN, JazzCash, cash, verify) and the operator console, including
  Agenta. It passed three runs in a row after the test's click-before-hydration fix.

## Added in this round

- Operator console in `apps/web` `/operator/*`: businesses, workspaces, plans, failed
  work, team, grant-gated conversations.
- Pi (Agenta) Q&A on the Overview, over the same scoped operator services.
- Customer payments: business's own Stripe, Pakistani banks, wallets, cash;
  staff-verified.
- Fixes from the independent review (price P1s) and from the peer code review (payments
  and operator team).

## Remaining

Live credentials (Kapso, Stripe, AI) and approval to migrate Neon. Campaigns, Flows,
file teaching, weekly summaries, calendar invites and caps were added on 30 Sept (see
PI_SAAS.md section 5). Remaining: see PI_SAAS.md section 10.

## How to resume

Test DB: `.venv/Scripts/python.exe .cache/pi-saas/setup_db.py`, then from `apps/api`
`source ../../.cache/pi-saas/env.sh`. Never use the `.env` Neon database. Live journey:
`bash .cache/pi-saas/live/rerun.sh` (API 8001, Pi app 3220, web 3300, mock Kapso 8765).
