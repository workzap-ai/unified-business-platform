# D8: PostgreSQL row-level security (RLS): security assessment for review

**Status: ASSESSMENT AND PROPOSAL.** No migration written, nothing enabled, nothing decided. Written
2026-10-30 from `origin/main` `cc462c5`. Items I could not verify are marked **UNVERIFIED**.

## 1. Where things stand

- ADR 0004 (`docs/adr/0004-tenant-ownership-and-scope.md`, "RLS decision and limits"): RLS is **not enabled**.
  Isolation is explicit scoped SQL plus relational constraints (composite foreign keys). The ADR says
  privileged or raw SQL can read across tenants, and to revisit RLS with separate migration and runtime roles at
  Stage 4 and the Stage 17 security review. ADR 0002: RLS is "defense in depth ... not selected or implemented".
- `TenantScope` and `TenantRepository` (ADR 0004) check tenant and active membership on every read and write
  in the services that use them.
- Evidence of enforcement today: `tests/integration/test_pi_isolation_core.py` (6 tests, two workspaces with
  the same phone number, merged in Wave 1, `be203dc`/`6a4e4b1`) and the lane R review found no confirmed tenant
  fault; `docs/pi-saas/capability-map.md` lists no tenant leak.

## 2. How sessions and tenant ids are set today

- One engine per process (`app/core/database.py` `create_engine`); sessions come from
  `async_sessionmaker(engine, expire_on_commit=False)` in `app/main.py:311`, `app/worker.py:78` and
  `app/core/jobs.py:62`; requests get a session from `get_session` (`database.py:~128`). Nothing sets a
  tenant on the connection. The tenant is a value in the query.
- Neon pooled endpoints are treated as PgBouncer transaction pooling (`-pooler.` host,
  `database.py` `resolve_database`): prepared-statement cache off, unique statement names, and the code comment
  says "no startup parameters" there. `options` is stripped from the URL (`_LIBPQ_ONLY`). So a session-level
  `SET app.tenant_id` would leak between clients; only per-transaction `SET LOCAL` / `set_config(..., true)` is
  safe. **UNVERIFIED** here: the actual production endpoint (pooled or direct) and its pool mode.
- A separate `migration_database_url` exists but defaults to the same value as `DATABASE_URL`
  (`app/core/config.py:~34`). If one role runs both, it owns the tables and **bypasses RLS** unless
  `FORCE ROW LEVEL SECURITY` is used, which still does not bind superusers or `BYPASSRLS` roles.

## 3. Which tables

By a literal-name count over `app/**/*.py` (a heuristic, it may miss scope columns with other names):
**154 mapped tables; 109 have a `tenant_id` column; 94 have `environment_id`; 45 do not.** The 45 without
`tenant_id`: customer_faces, customer_passkeys, customer_prefs, customer_share_links,
customer_sign_in_locks, email_verification_tokens, integration_external_refs, integration_oauth_states,
integration_sync_attempts, integration_sync_conflicts, integration_sync_cursors, integration_workflows,
knowledge_sources, notification_reads, password_reset_tokens, pi_bookable_services, pi_build_fit, pi_campaigns,
pi_catalogue_proposals, pi_checkout_attempts, pi_collection_settings, pi_conversation_notes,
pi_idea_feedback, pi_knowledge_drafts, pi_learned_packs, pi_learning_changes, pi_learning_examples,
pi_learning_lessons, pi_learning_runs, pi_operator_members, pi_plans, pi_platform_invoices,
pi_platform_settings, pi_platform_state, pi_provider_connections, pi_quarantine, pi_question_arms,
pi_support_grants, platform_products, platform_users, tenants, user_credentials, user_faces, user_passkeys,
whatsapp_connections. Some are global by design (platform_users, tenants, plans, platform settings), some are
scoped through another column or a parent row (for example the pi tables use a workspace or customer link),
and some are the "customer portal" tables. RLS would need a per-table scope rule for each, so 45 tables need a
decision before any policy. Raw `text(...)` SQL appears 53 times in `app/` (each one a place an RLS policy
would also apply, and a place a forgotten filter can hide).

## 4. Threat model

| threat | today | with RLS |
|---|---|---|
| a query forgets its tenant filter (new code, by-id lookup) | caught only by review and isolation tests | database returns zero rows or denies |
| raw SQL or an injection returns other tenants' rows | not stopped | stopped for the tenant-scoped tables |
| compromised application role | reads everything | still reads whatever it can set its context to; RLS does not help if the app can set any tenant id |
| operator console, support grants, nightly learning, webhooks resolving a tenant from a phone number | need cross-tenant or pre-tenant access | need an explicit bypass path (separate role or security-definer function), which becomes the new thing to audit |
| migrations, backups, superuser | unaffected | unaffected (bypass RLS) |
| a tenant legitimately in context misusing data | app permissions | app permissions (no change) |

RLS adds a second, independent check against coding mistakes; it does not replace application permissions and
does not stop a compromised context setter.

## 5. Cost and risk

- **Roles:** needs a runtime role that does not own tables and has no `BYPASSRLS`, plus a migration role. **UNVERIFIED**
  that the Neon project supports this setup without a plan change; to be checked on the dashboard.
- **Per-request context:** every transaction must run `set_config('app.tenant_id', ..., true)` first, in
  requests, in the worker (`worker.py:88`), in inline jobs, in WhatsApp inbound (the tenant is only known after
  the number lookup), in the customer portal (cookie scope) and in the operator console. A missed one fails
  closed (no rows), which shows as outages, not leaks.
- **Pool leakage:** a context left on a pooled connection would be the worst failure; needs `LOCAL` scope and a
  test.
- **Performance:** predicates reuse existing `tenant_id` indexes; one extra statement per transaction (can be
  folded into the first statement). **UNVERIFIED** until measured on a copy; the planner can mis-estimate with
  `current_setting` in policies.
- **Rollout:** any policy on a table the app reads without context takes that feature down. 109 tables plus 45
  to classify is a long tail. Alembic migrations are hand-numbered and the real database is migrated by pasting
  SQL into the Neon editor only when the owner asks, so each step is a manual production change needing approval.

## 6. Test plan (all on the disposable database)

1. Fail-closed: with no context set, every protected table returns zero rows on read and rejects writes.
2. Two-tenant: with context A, rows of B are invisible, update and delete affect zero rows, insert with B's id
   is rejected (`WITH CHECK`).
3. Pool leakage: two clients on one pooled connection in sequence never see each other's context.
4. Every entry point sets context: requests, worker, inline queue, inbound webhook, customer portal, operator.
5. Bypass paths: operator and learning jobs work only through the named path; the runtime role cannot disable RLS.
6. Table owner and `FORCE`: prove the owner role is not used at runtime.
7. Existing suites unchanged: the unit suite, `test_pi_isolation_core.py`, the brain integration suite.
8. Performance: p95 on the heaviest pi queries before and after, on a data copy.

## 7. Proposal (mine, marked as such; the decision is the owner's)

1. **Do not enable RLS broadly now.** The current evidence shows no confirmed leak and the cost and outage risk
   are real.
2. **Stage 0 (no production change):** classify the 154 tables (tenant-scoped, workspace-scoped, global, portal),
   list every entry point that needs a context, and build the fail-closed test harness on the disposable
   database.
3. **Stage 1, only after approval:** split migration and runtime roles; check Neon support.
4. **Stage 2:** pilot on a small set of high-sensitivity pi tables (customer memory, problem book, share links)
   in the disposable database, then a copy of production, then production in a window you choose.
5. Revisit after the Stage 0 inventory shows how many tables fit one simple policy.

## 8. Decisions needed from the owner

1. RLS: not now / Stage 0 only / pilot after Stage 0.
2. Whether the Neon plan and role setup may be examined (a dashboard check by you, no change).
3. Whether operator and learning paths may use a separate bypass role.

## 9. Limitations

Table counts are a name-based heuristic. I did not measure performance, test PgBouncer behaviour or inspect
the production database or its roles. No migration was written.
