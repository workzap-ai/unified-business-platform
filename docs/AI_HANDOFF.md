# AI and developer handoff

## Read first

1. [PROJECT_STATUS.md](PROJECT_STATUS.md) — what exists and what is verified
2. [FRONTEND_GUIDE.md](FRONTEND_GUIDE.md) — web app conventions
3. [ARCHITECTURE.md](ARCHITECTURE.md), [SECURITY.md](SECURITY.md), [API_CONVENTIONS.md](API_CONVENTIONS.md)
4. ADRs, especially [0004](adr/0004-tenant-ownership-and-scope.md) and [0005](adr/0005-environment-scope-navigation-and-data-modes.md)

## Current stopping point

The UI-first milestone is done: every module, the PI workspace and the admin area are
built, run on sample data, and pass format, lint, typecheck, build and 16 Playwright tests
(see PROJECT_STATUS for the full verification table). The user authorized continuous
execution of the whole roadmap without stage-by-stage approval.

The next phase connects the UI to the real API and completes the backend:

1. Backend tests for auth/sessions/CSRF, RBAC, tenant + environment isolation of every new
   table, money/state-machine rules, order → stock → invoice flows.
2. Run the web app with `NEXT_PUBLIC_DATA_MODE=live` against the API on a migrated
   database; fix contract mismatches; add Playwright E2E against the real stack.
3. PI backend over the existing pi_* tables: AI gateway (provider order and model aliases
   from settings; OpenAI → Gemini → Groq → human handoff), WhatsApp webhook (verify, dedup,
   persist, enqueue, fast 200) and ARQ worker pipeline, LangGraph router + agents with
   controlled tools, memory/RAG, handoff/takeover enforcement. Implement the contracts in
   `apps/web/src/features/pi/types.ts`, then replace the PI live adapter
   (`features/pi/service.ts`, currently "not connected") with real calls.

## Rules that must hold

- Tenant and environment scope come only from the verified session, never from request
  input. Business rows are environment-scoped (composite FKs); use `WorkspaceRepository`.
- The backend is the authority for permissions; UI gating is display only.
- Money is Decimal/NUMERIC in the API and decimal strings in the UI. No float arithmetic.
- Navigation is defined once in `apps/api/app/modules/navigation/definitions.py`. After
  changes run `python -m app.modules.navigation.export`; a test fails if the web snapshot
  is stale.
- Sample data lives only in `apps/web/src/demo` and feature demo adapters; UI code never
  imports it, and it must never be presented as real data.
- PI never becomes the source of truth for prices, stock, orders or balances; it acts
  through controlled tools with confirmation for mutations.

## Environment notes

- PostgreSQL 17 portable binaries and a disposable cluster (port 55432) live in the
  ignored `.cache/`. Test credentials are in `.cache/pg-stage2/test_connection.json`; never
  print them. Start with `pg_ctl -D .cache/pg-stage2/data -o "-p 55432 -c listen_addresses=127.0.0.1" start`.
- No Docker, Redis, or pgvector locally. Redis/worker, container and semantic retrieval
  checks must run in CI or an equipped machine.
- Playwright browsers are in `.cache/ms-playwright` (`PLAYWRIGHT_BROWSERS_PATH`).
- Superseded Stage 2 frontend files were moved (not deleted) to `.cache/legacy-web-stage2/`.
