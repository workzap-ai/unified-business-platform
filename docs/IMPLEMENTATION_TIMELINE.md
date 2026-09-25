# Implementation timeline

## Historical foundation — 2026-09-23 to 2026-09-24

The repository began with an architecture audit, a modular monolith decision,
tenant isolation design, backend/frontend foundations, authentication, RBAC,
environments, business modules, and product/navigation registries. The historical
stage gates are superseded by the authorized continuous continuation.

## Continuation starting point — 2026-09-24

Inspected source, migrations 0001/0002, tests, deployment configuration and the
existing project documentation. The web application has substantial sample-backed
screens and live adapters for core modules. The backend implements core business
services, including untracked order items. PI and AI usage tables exist, but PI
services, the gateway and workflow runtime do not exist at this starting point.
The requested DECISIONS.md was absent; architecture and security documents contain
stale Stage 2 claims. Pre-existing permission/navigation edits and
docs/contracts/integrations-api.md are preserved.

Initial verification: backend unit suite 23 passed; 14 integration tests skipped
without configured test services. This is not full backend verification.

## Service-first frontend milestone — in progress

Offering creation now distinguishes service, product, hybrid and package. Services
default to untracked pricing options. Catalog and onboarding emphasize services,
quotes and delivery. Business settings expose an environment business type.
The existing routes, document builders and navigation registry remain in place.
Build, browser and backend contract verification are tracked in PROJECT_STATUS.md.
