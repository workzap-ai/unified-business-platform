# Architecture decision records

Records distinguish accepted design direction from implementation and runtime verification. See each record and PROJECT_STATUS.md for its current scope and evidence.

| Record | Status |
| --- | --- |
| [0001 — Modular monolith and product boundaries](0001-modular-monolith-and-product-boundaries.md) | Accepted design direction |
| [0002 — Trusted tenant context and isolation](0002-trusted-tenant-context.md) | Accepted design direction |
| [0003 — Foundation runtime and queue](0003-foundation-runtime-and-queue.md) | Accepted; Stage 1 |
| [0004 — Tenant ownership and scope](0004-tenant-ownership-and-scope.md) | Accepted; Stage 2 |
| [0005 — Environment scope, navigation registry, data modes](0005-environment-scope-navigation-and-data-modes.md) | Accepted; implemented |

Add numbered decisions with date, status, context, decision, consequences, and verification. Do not rewrite history silently; supersede records when decisions change. Queue selection is recorded in 0003; Stage 2 ownership and the decision to defer RLS activation are recorded in 0004.
