"use client";

import { useCallback, useMemo } from "react";
import Link from "next/link";
import {
  ArrowRight,
  Bot,
  Clock3,
  MessageCircle,
  Plug,
  PlugZap,
  ScrollText,
  SearchX,
  TriangleAlert,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { pluralize } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, Skeleton } from "@/components/ui/display";
import { RequirePermission, SectionHeader } from "@/components/app/page";
import { MetricCard, MetricGrid } from "@/components/app/metric-card";
import { FilterBar, FilterSelect, SearchInput } from "@/components/app/filters";
import { DataTable, type Column } from "@/components/app/data-table";
import { EmptyState, ErrorState } from "@/components/app/states";
import { useScopedQuery } from "@/hooks/use-scoped";
import { useUrlState } from "@/hooks/use-url-state";
import { useSession } from "@/features/auth/session-provider";
import { integrationsService } from "./service";
import {
  GatedButton,
  IntegrationGlyph,
  IntegrationsFrame,
  StateBadge,
  When,
  useDefinitions,
} from "./components";
import {
  CATEGORIES,
  type Connection,
  type IntegrationDefinition,
} from "./types";
import { CATEGORY_LABELS } from "./lib";

export function IntegrationsDirectoryPage() {
  return (
    <RequirePermission permission="integrations.read" area="integrations">
      <Directory />
    </RequirePermission>
  );
}

function Directory() {
  const [state, setState, reset] = useUrlState({
    q: "",
    category: "",
    availability: "",
  });
  const definitions = useDefinitions();
  const connections = useScopedQuery(
    ["integrations", "connections", "directory"],
    () => integrationsService.connections({ pageSize: 100 }),
  );

  const byKey = useMemo(
    () => new Map((definitions.data ?? []).map((d) => [d.key, d])),
    [definitions.data],
  );
  const filtered = useMemo(() => {
    const q = state.q.trim().toLowerCase();
    return (definitions.data ?? []).filter(
      (d) =>
        (!state.category || d.category === state.category) &&
        (!state.availability || d.availability === state.availability) &&
        (!q ||
          [d.name, d.provider, d.description, d.category, ...d.capabilities]
            .join(" ")
            .toLowerCase()
            .includes(q)),
    );
  }, [definitions.data, state]);
  const groups = CATEGORIES.map((category) => ({
    category,
    items: filtered.filter((d) => d.category === category),
  })).filter((g) => g.items.length > 0);

  const live = (connections.data?.items ?? []).filter(
    (c) => c.status !== "revoked",
  );
  const attention = live.filter((c) =>
    ["degraded", "error", "expired"].includes(c.status),
  ).length;
  const onSearch = useCallback((q: string) => setState({ q }), [setState]);
  const activeFilters = [state.category, state.availability].filter(
    Boolean,
  ).length;

  return (
    <IntegrationsFrame
      title="Integrations"
      description="Connect providers to this workspace environment, and monitor their health, events and sync work."
    >
      <MetricGrid className="mb-6">
        <MetricCard
          label="Connected"
          icon={PlugZap}
          tone="success"
          loading={connections.isPending}
          value={live.filter((c) => c.status === "connected").length}
          detail={`of ${pluralize(live.length, "connection")}`}
        />
        <MetricCard
          label="Need attention"
          icon={TriangleAlert}
          tone={attention ? "warning" : "default"}
          loading={connections.isPending}
          value={attention}
          detail="Degraded, expired or in error"
          href="/settings/integrations/health"
        />
        <MetricCard
          label="Available integrations"
          icon={Plug}
          loading={definitions.isPending}
          value={
            (definitions.data ?? []).filter((d) => d.availability !== "planned")
              .length
          }
          detail="Including beta"
        />
        <MetricCard
          label="Planned"
          icon={Clock3}
          loading={definitions.isPending}
          value={
            (definitions.data ?? []).filter((d) => d.availability === "planned")
              .length
          }
          detail="Not connectable yet"
        />
      </MetricGrid>

      <section aria-labelledby="connections-heading" className="mb-8">
        <SectionHeader
          title={<span id="connections-heading">Your connections</span>}
          description="Connections belong to the current workspace and environment only."
        />
        <ConnectionsTable
          rows={connections.data?.items}
          loading={connections.isPending}
          error={connections.error}
          onRetry={() => void connections.refetch()}
          byKey={byKey}
        />
      </section>

      <section aria-labelledby="directory-heading">
        <SectionHeader
          title={<span id="directory-heading">Directory</span>}
          description="Available integrations can be connected now. Beta integrations work but may change. Planned integrations are listed for visibility and can't be connected yet."
        />
        <FilterBar activeCount={activeFilters} onClear={reset}>
          <SearchInput
            value={state.q}
            onChange={onSearch}
            placeholder="Search integrations…"
            className="w-full md:w-72"
          />
          <FilterSelect
            label="Category"
            value={state.category}
            onChange={(category) => setState({ category })}
            options={CATEGORIES.map((c) => ({
              value: c,
              label: CATEGORY_LABELS[c],
              count: (definitions.data ?? []).filter((d) => d.category === c)
                .length,
            })).filter((o) => o.count > 0)}
          />
          <FilterSelect
            label="Availability"
            value={state.availability}
            onChange={(availability) => setState({ availability })}
            options={[
              { value: "available", label: "Available" },
              { value: "beta", label: "Beta" },
              { value: "planned", label: "Planned" },
            ]}
          />
        </FilterBar>

        {definitions.isPending ? (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {Array.from({ length: 6 }, (_, i) => (
              <Skeleton key={i} className="h-44 rounded-xl" />
            ))}
          </div>
        ) : definitions.isError ? (
          <Card>
            <ErrorState
              error={definitions.error}
              onRetry={() => void definitions.refetch()}
            />
          </Card>
        ) : groups.length === 0 ? (
          <Card>
            <EmptyState
              icon={SearchX}
              title="No integrations match"
              description="Try a different search or clear the filters."
              action={
                <Button variant="secondary" onClick={reset}>
                  Clear filters
                </Button>
              }
            />
          </Card>
        ) : (
          <div className="grid grid-cols-1 gap-x-3 gap-y-6 sm:grid-cols-2 xl:grid-cols-3">
            {groups.map((group) => (
              <div
                key={group.category}
                data-category={group.category}
                className="min-w-0"
              >
                <h3 className="mb-2 text-2xs font-semibold tracking-wide text-muted-foreground uppercase">
                  {CATEGORY_LABELS[group.category]}
                </h3>
                <ul className="space-y-3">
                  {group.items.map((d) => (
                    <li key={d.key} className="min-w-0">
                      <DefinitionCard definition={d} />
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </section>

      <RelatedSettings />
    </IntegrationsFrame>
  );
}

function DefinitionCard({
  definition: d,
}: {
  definition: IntegrationDefinition;
}) {
  const planned = d.availability === "planned";
  return (
    <Card
      className={cn(
        "flex h-full flex-col p-4",
        planned && "bg-surface-muted/50",
      )}
      data-integration={d.key}
      aria-label={d.name}
    >
      <div className="flex items-start gap-3">
        <IntegrationGlyph category={d.category} />
        <div className="min-w-0 flex-1">
          <Link
            href={`/settings/integrations/${d.key}`}
            className="block truncate text-[14px] font-semibold hover:underline"
          >
            {d.name}
          </Link>
          <p className="truncate text-xs text-muted-foreground">{d.provider}</p>
        </div>
        <StateBadge value={d.availability} />
      </div>
      <p className="mt-2.5 line-clamp-2 text-[13px] text-muted-foreground">
        {d.description}
      </p>
      <div className="mt-auto flex flex-wrap items-center justify-between gap-2 pt-3">
        <span className="text-xs text-muted-foreground">
          {d.connection_count > 0
            ? `${d.connection_count} connected here`
            : "Not connected"}
        </span>
        {planned ? (
          <span className="text-xs font-medium text-muted-foreground">
            Planned · can&apos;t be connected yet
          </span>
        ) : (
          <div className="flex gap-1.5">
            <Button variant="ghost" size="sm" asChild>
              <Link href={`/settings/integrations/${d.key}`}>Details</Link>
            </Button>
            <ConnectLink definition={d} />
          </div>
        )}
      </div>
    </Card>
  );
}

function ConnectLink({ definition }: { definition: IntegrationDefinition }) {
  const { can } = useSession();
  if (!can("integrations.manage"))
    return (
      <GatedButton
        permission="integrations.manage"
        size="sm"
        variant="secondary"
      >
        Connect
      </GatedButton>
    );
  return (
    <Button size="sm" variant="secondary" asChild>
      <Link
        href={`/settings/integrations/${definition.key}?connect=1`}
        aria-label={`Connect ${definition.name}`}
      >
        Connect
      </Link>
    </Button>
  );
}

function ConnectionsTable({
  rows,
  loading,
  error,
  onRetry,
  byKey,
}: {
  rows: Connection[] | undefined;
  loading: boolean;
  error: unknown;
  onRetry: () => void;
  byKey: Map<string, IntegrationDefinition>;
}) {
  const columns: Column<Connection>[] = [
    {
      key: "name",
      header: "Connection",
      cell: (c) => {
        const d = byKey.get(c.integration_key);
        return (
          <div className="flex min-w-0 items-center gap-2.5">
            <IntegrationGlyph category={d?.category} size="sm" />
            <div className="min-w-0">
              <Link
                href={`/settings/integrations/connections/${c.id}`}
                className="block truncate font-medium hover:underline"
              >
                {c.display_name}
              </Link>
              <p className="truncate text-xs text-muted-foreground">
                {d?.name ?? c.integration_key}
                <span className="sm:hidden"> · {c.mode}</span>
              </p>
            </div>
          </div>
        );
      },
    },
    {
      key: "status",
      header: "Status",
      cell: (c) => <StateBadge value={c.status} />,
    },
    {
      key: "health",
      header: "Health",
      hideBelow: "md",
      cell: (c) => <StateBadge value={c.health} />,
    },
    {
      key: "mode",
      header: "Mode",
      hideBelow: "sm",
      cell: (c) => <StateBadge value={c.mode} />,
    },
    {
      key: "last",
      header: "Last success",
      hideBelow: "lg",
      cell: (c) => <When value={c.last_success_at} />,
    },
    {
      key: "error",
      header: "Last error",
      hideBelow: "xl",
      cell: (c) =>
        c.last_error ? (
          <span className="line-clamp-1 max-w-72 text-xs text-danger">
            {c.last_error}
          </span>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
  ];
  return (
    <DataTable
      caption="Connections in this environment"
      columns={columns}
      rows={rows}
      loading={loading}
      error={error}
      onRetry={onRetry}
      loadingRows={3}
      getRowId={(c) => c.id}
      rowHref={(c) => `/settings/integrations/connections/${c.id}`}
      rowClassName={(c) => (c.status === "revoked" ? "opacity-60" : undefined)}
      empty={
        <EmptyState
          compact
          icon={Plug}
          title="No connections in this environment yet"
          description="Pick an integration from the directory below to connect it. Connections made in other environments don't appear here."
        />
      }
    />
  );
}

function RelatedSettings() {
  const { can } = useSession();
  const links = [
    can("pi.read") && {
      href: "/pi/whatsapp",
      icon: MessageCircle,
      title: "PI WhatsApp connection",
      description:
        "The installed PI product's own WhatsApp number and webhook event history.",
      extra: { href: "/pi/whatsapp/events", label: "Webhook events" },
    },
    can("pi.read") && {
      href: "/pi/settings/provider-configuration",
      icon: Bot,
      title: "AI provider configuration",
      description:
        "Provider credentials for PI are managed on the server; workspace policy lives here.",
    },
    can("audit.read") && {
      href: "/settings/audit",
      icon: ScrollText,
      title: "Audit log",
      description:
        "Every connect, rotate, test, retry and disconnect is recorded.",
    },
  ].filter(Boolean) as {
    href: string;
    icon: typeof Bot;
    title: string;
    description: string;
    extra?: { href: string; label: string };
  }[];
  if (!links.length) return null;
  return (
    <Card className="mt-8">
      <CardHeader title="Related settings" />
      <CardBody>
        <ul className="grid gap-3 md:grid-cols-3">
          {links.map((l) => (
            <li
              key={l.href}
              className="flex gap-3 rounded-lg border border-border p-3"
            >
              <l.icon
                className="mt-0.5 size-4 shrink-0 text-muted-foreground"
                aria-hidden="true"
              />
              <div className="min-w-0">
                <Link
                  href={l.href}
                  className="inline-flex items-center gap-1 text-[13px] font-medium text-primary hover:underline"
                >
                  {l.title}{" "}
                  <ArrowRight className="size-3.5" aria-hidden="true" />
                </Link>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {l.description}
                </p>
                {l.extra && (
                  <Link
                    href={l.extra.href}
                    className="mt-1 inline-block text-xs font-medium text-primary hover:underline"
                  >
                    {l.extra.label}
                  </Link>
                )}
              </div>
            </li>
          ))}
        </ul>
      </CardBody>
    </Card>
  );
}
