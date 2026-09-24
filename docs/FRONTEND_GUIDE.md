# Frontend guide

How the web app (`apps/web`) is put together, and the conventions every module follows so
the product feels like one system. Read this before adding a screen or a module.

## Architecture

```
src/
  app/(auth)/…            sign-in, registration (no shell)
  app/(app)/…             every authenticated route; thin page files only
  components/ui/          primitives (button, input, controls, overlays, display)
  components/app/         business primitives (page, states, data-table, filters,
                          metric-card, charts, record, forms, status-badge)
  components/shell/       app shell, sidebar, top bar, command menu, breadcrumbs
  features/<module>/      service.ts (live + demo adapters), components, hooks
  features/business/types.ts   Zod contracts for core business modules (mirror API)
  features/pi/types.ts    PI contracts
  demo/                   sample-data layer (demo mode only)
```

Route files in `app/(app)` stay thin: set `metadata` and render a feature component.

## Data flow

UI → TanStack Query (`useScopedQuery` / `useScopedMutation` in `src/hooks/use-scoped.ts`) →
feature service (`features/<module>/service.ts`) → live adapter (`apiRequest`) or demo adapter.

- `NEXT_PUBLIC_DATA_MODE=live` uses the platform API through the same-origin `/api/v1`
  proxy. Anything else uses in-browser sample data. The shell shows a "Sample data"
  marker in demo mode. Never present sample data as real.
- Both adapters satisfy one contract. Pages must never import from `src/demo` directly.
- Query keys are prefixed with tenant + environment by `useScopedQuery`; switching
  workspaces drops them. Use a stable key per resource, e.g. `["customers", params]`,
  and invalidate the resource prefix after mutations (`invalidate: [["customers"]]`).
- Money and quantities are decimal strings. Display with `formatMoney(value, currency)`;
  compute previews with `toCents`/`centsToString`. Never use float arithmetic for totals.
- PI's API is not deployed yet: its live adapter throws `ServiceNotConnectedError`, which
  `ErrorState` renders as an honest "not connected" message.

## Navigation

The backend navigation registry (`apps/api/app/modules/navigation/definitions.py`) is the
single source of routes, labels, icons, permissions, product/feature gates and default
order. It powers the sidebar, mobile drawer, module tabs (`<ModuleNav moduleKey=… />`),
breadcrumbs and the command menu. Demo mode uses the generated snapshot
`features/navigation/registry.generated.json`; regenerate after changing definitions:

```
cd apps/api && python -m app.modules.navigation.export
```

Adding a module: register a `NavDefinition` (+ child pages), export, build the pages, and
optionally add a manifest (quick actions, record search) in `features/modules/manifests.ts`.
Never add routes to the sidebar component.

## Page anatomy

- List page: `PageShell` → `PageHeader` (title, one-line purpose, primary action) →
  `ModuleNav` (if the module has sub-pages) → optional metric strip → `SavedViews` →
  `FilterBar` (`SearchInput`, `FilterSelect` chips, `ColumnsMenu`) → `DataTable` →
  `Pagination`. List state (search, filters, page, view) lives in the URL via `useUrlState`.
- Record page: `PageShell` → `RecordHeader` (avatar/icon, title, status, identifier, meta,
  primary + secondary actions) → `Tabs` or a two-column layout (main + side panel with
  `PropertyList`, `RelatedList`, `ActivityTimeline`). Set breadcrumbs with
  `useBreadcrumbs([{ label: record.name }], { href, kind })`.
- Create/edit: full page for multi-section forms (`FormSection` blocks + sticky
  `FormActions`, `useUnsavedChangesWarning`); `Dialog`/`SheetContent` for small edits.
  React Hook Form + Zod; show server errors with `errorMessage()`.
- Every data view handles loading (skeletons shaped like content), empty (contextual
  `EmptyState` with a next action), error (`ErrorState` with retry), permission
  (`RequirePermission` / `PermissionGate`) and not-found.
- Destructive or irreversible actions use `ConfirmDialog` with consequences listed.
- Status chips use `StatusBadge`; all statuses share one tone vocabulary.

## Visual rules

- Tokens only (see `globals.css`): `bg-surface`, `bg-surface-muted`, `text-muted-foreground`,
  `border-border`, `text-primary`, `bg-primary-soft`, `text-pi`/`bg-pi-soft` (PI only),
  `success/warning/danger/info` (+ `-soft`). No raw hex in components.
- Type scale: page title 20–22px semibold; section 15px; body 13–14px; meta 12px (`text-xs`);
  labels 11px uppercase only for small group headings. Use `tabular` for numbers in tables.
- Dense tables (compact rows), roomy forms. Cards: `rounded-xl border bg-surface shadow-sm`.
- Charts: `ChartCard` / `DistributionBar` / `Sparkline` only; series colors are the
  validated `--chart-1..5` order; one y-axis; legend for ≥2 series; table view built in.
- Responsive at 390 / 768 / 1024 / 1280 / 1440: hide secondary table columns with
  `hideBelow`, stack side panels under main content below `lg`, no horizontal page scroll.
- Accessible names on icon buttons, visible focus, labels on every input, keyboard paths
  for drag interactions.

## Checks

```
npm run format:check && npm run lint && npm run typecheck && npm run build && npm test
```
