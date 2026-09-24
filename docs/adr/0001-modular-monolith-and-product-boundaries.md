# 0001 — Modular monolith and product boundaries

Date: 2026-09-23

Status: Accepted design direction; implementation pending.

## Context

The workspace is empty. The user requires a multi-tenant business platform with shared identity, business modules, and extensible installable products, delivered through explicit stage gates.

## Decision

Use a modular monolith and the specified FastAPI/Next.js monorepo stack. Separate identity/foundation, core business modules, and installable products through explicit interfaces. Keep catalog_products separate from platform_products and their installation records. The shared AI gateway is foundation infrastructure.

PI is one future product and consumes platform services through authorized tools. It has no sub-products. Do not register or implement it before a passed Stage 18 quality gate. Do not create future products or assign a public parent brand.

## Consequences

Shared operations are simpler to develop and transact initially. Boundaries require review to avoid circular dependencies and cross-module table writes. Extraction into services remains possible later but is not a current deliverable. No competing queue frameworks or redundant infrastructure will be introduced.

## Verification

Stage 0: documentation consistency only. Later stages must validate module imports, API contracts, core-module independence, product installation permissions, and the foundation gate. No code exists to verify these yet.
