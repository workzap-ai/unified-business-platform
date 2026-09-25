# Service-first continuation audit

Date: 2026-09-24. This records inspected implementation, not acceptance claims.

| UI route | Feature adapter | API / service | Models | Authorization / initial tests |
| --- | --- | --- | --- | --- |
| / | reports | /overview; reports service | business aggregates | overview + source permissions; no dedicated test |
| /customers | customers | /customers; CustomersService | customers, notes, activities | customers read/write; no dedicated test |
| /catalog | catalog | /catalog; CatalogService | products, variants, categories | catalog read/write; no dedicated test |
| /inventory | inventory | /inventory; InventoryService | locations, levels, movements | inventory permissions; no capability gate |
| /sales | sales | /sales; SalesService | leads with requirement JSON | sales permissions; no dedicated test |
| /quotes | documents | /quotes; QuoteService | quotes, lines | write/approve rules; no dedicated test |
| /orders | documents | /orders; OrderService | orders, lines | state machine, untracked lines supported; no dedicated test |
| /billing | billing | /billing; BillingService | invoices, payments | billing permissions; no dedicated test |
| /finance | finance | /finance; finance service | expenses, billing aggregates | finance permissions; no dedicated test |
| /hr | hr | /hr; HR service | employees | HR permissions; no dedicated test |
| /reports | reports | /reports; reports service | bounded aggregates | report + source permissions; no dedicated test |
| /settings | admin | organization, members, roles, settings, products | tenant/environment scoped records | permission gates; partial navigation tests |
| /pi | PI | live adapter disconnected | PI schema exists | runtime missing |

Frontend gaps: stock-first creation defaults and empty-state onboarding; catalog
lacks an explicit offering type; service-business navigation needs backend capability
filtering. Core live adapters exist but require integration verification. PI has
sample-only adapters. Dashboard metric permissions already limit aggregate exposure.

Backend gaps: explicit offering types, business capabilities, service delivery
metadata, dedicated business/security integration tests, shared workflow engine,
provider gateway and PI runtime. External WhatsApp/AI/object storage configuration
and container/Redis/pgvector verification remain separate from local code checks.
