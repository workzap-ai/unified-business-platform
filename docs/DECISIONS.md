# Current implementation decisions

Updated 2026-09-24. Historical architecture decisions remain in `docs/adr/`.

1. Preserve the modular monolith, shared service layer, scoped repositories,
   PostgreSQL/Decimal money, session authentication and registry-driven navigation.
2. PI is an installable product. The parent platform remains unnamed.
3. Extend the existing catalog with an explicit offering type; retain existing
   product/variant IDs and API paths so quotes and orders remain compatible.
   Services use pricing options and never require inventory or warehouses.
4. Business type is environment-scoped business configuration, controlled by the
   backend. New workspaces default to services; migrate existing workspaces without
   disabling physical inventory unexpectedly.
5. The current source and verified tests supersede historical stage-gated plans.
   External credentials and infrastructure must never be replaced by fake success.
