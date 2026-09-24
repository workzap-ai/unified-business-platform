# 0002 — Trusted tenant context and isolation

Date: 2026-09-23

Status: Accepted design direction; implementation pending.

## Context

Shared infrastructure must not permit one tenant to access another tenant's business records. Client selectors and model-generated arguments cannot establish authority.

## Decision

Resolve tenant context through authenticated identity and active membership on the server. Require trusted tenant scope in services/repositories handling tenant-owned data. Use UUID identities, tenant ownership fields, and domain-appropriate environment/branch/department scope. Validate all referenced entities against the same ownership context and enforce compatible relational constraints.

Propagate validated scope to cache keys, jobs, events, audit records, product installations, and later semantic retrieval. Permissions remain server-side; frontend visibility does not grant access. Document per-entity environment semantics before migrations. Evaluate PostgreSQL RLS in Stage 2 as defense in depth; it is not selected or implemented here.

## Consequences

Every new module must define ownership and test negative access paths. Background processing needs an explicit authority/revocation policy. Cross-tenant administrative operations, if later required, need a separately authorized and audited path rather than bypassing ordinary scope checks.

## Verification

Beginning at Stage 2, integration tests must prove cross-tenant reads, writes, deletes, guessed IDs, and mismatched relationships fail. Later stages extend tests to permissions, environments, caches, jobs, installations, and retrieval. No isolation test has run at Stage 0.
