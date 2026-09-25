"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  ArrowUpRight,
  Check,
  Clock3,
  Plug,
  SearchX,
  ShieldAlert,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge, Card, CardBody, CardHeader } from "@/components/ui/display";
import { PageShell, RequirePermission } from "@/components/app/page";
import { PageSkeleton } from "@/components/app/page-skeleton";
import {
  PropertyList,
  RecordHeader,
  RelatedList,
} from "@/components/app/record";
import { EmptyState, ErrorState, Notice } from "@/components/app/states";
import { useBreadcrumbs } from "@/components/shell/breadcrumbs";
import { useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import { integrationsService } from "./service";
import {
  categoryIcon,
  GatedButton,
  StateBadge,
  When,
  useDefinitions,
} from "./components";
import { ConnectDialog } from "./connection-forms";
import {
  AUTH_LABELS,
  CATEGORY_LABELS,
  capabilityLabel,
  isElevatedScope,
} from "./lib";
import type { IntegrationDefinition } from "./types";

export function IntegrationDetailPage({
  integrationKey,
}: {
  integrationKey: string;
}) {
  return (
    <RequirePermission permission="integrations.read" area="integrations">
      <DetailLoader integrationKey={integrationKey} />
    </RequirePermission>
  );
}

function DetailLoader({ integrationKey }: { integrationKey: string }) {
  const definitions = useDefinitions();
  if (definitions.isPending) return <PageSkeleton variant="detail" />;
  if (definitions.isError)
    return (
      <PageShell width="default">
        <ErrorState
          error={definitions.error}
          onRetry={() => void definitions.refetch()}
        />
      </PageShell>
    );
  const definition = definitions.data.find((d) => d.key === integrationKey);
  if (!definition)
    return (
      <PageShell width="default">
        <h1 className="sr-only">Integration not found</h1>
        <EmptyState
          icon={SearchX}
          title="Integration not found"
          description="No integration with this key is registered."
          action={
            <Button variant="secondary" asChild>
              <Link href="/settings/integrations">Back to directory</Link>
            </Button>
          }
        />
      </PageShell>
    );
  return <IntegrationDetail definition={definition} />;
}

function IntegrationDetail({
  definition: d,
}: {
  definition: IntegrationDefinition;
}) {
  const { can } = useSession();
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  useBreadcrumbs([{ label: d.name }], {
    href: `/settings/integrations/${d.key}`,
    kind: "Integration",
  });
  const planned = d.availability === "planned";
  const [connectOpen, setConnectOpen] = useState(
    () =>
      params.get("connect") === "1" && !planned && can("integrations.manage"),
  );
  const connections = useScopedQuery(
    ["integrations", "connections", { integration_key: d.key }],
    () =>
      integrationsService.connections({ integration_key: d.key, pageSize: 50 }),
  );
  const closeConnect = () => {
    setConnectOpen(false);
    if (params.get("connect")) router.replace(pathname, { scroll: false });
  };
  const optionalScopes = d.supported_scopes.filter(
    (s) => !d.required_scopes.includes(s),
  );
  const syncDirections = d.sync_support.filter((s) => s !== "none");

  return (
    <PageShell width="default">
      <RecordHeader
        icon={categoryIcon(d.category)}
        title={d.name}
        subtitle={d.description}
        status={<StateBadge value={d.availability} />}
        identifier={d.key}
        meta={
          <>
            <span>{CATEGORY_LABELS[d.category]}</span>
            <span>Provider: {d.provider}</span>
            <span>
              {d.connection_count > 0
                ? `${d.connection_count} connected in this environment`
                : "Not connected in this environment"}
            </span>
          </>
        }
        actions={
          <>
            {d.documentation_url && (
              <Button variant="secondary" size="sm" asChild>
                <a
                  href={d.documentation_url}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Provider docs <ArrowUpRight />
                </a>
              </Button>
            )}
            <GatedButton
              size="sm"
              permission="integrations.manage"
              blockedReason={
                planned
                  ? "Planned: no adapter exists yet, so it can't be connected"
                  : null
              }
              onClick={() => setConnectOpen(true)}
            >
              <Plug /> Connect
            </GatedButton>
          </>
        }
      />

      {planned && (
        <Notice
          tone="neutral"
          icon={Clock3}
          className="mb-4"
          title="Planned integration"
        >
          {d.name} is registered so you can see what&apos;s coming, but it has
          no adapter yet and can&apos;t be connected.
        </Notice>
      )}
      {d.availability === "beta" && (
        <Notice tone="info" className="mb-4" title="Beta">
          This integration works, but its behaviour and configuration may still
          change.
        </Notice>
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-w-0 space-y-4">
          <Card>
            <CardHeader
              title="Access requested"
              description="Every scope this integration asks the provider for. Elevated scopes can change data or act on your behalf."
            />
            <CardBody>
              {d.required_scopes.length === 0 && optionalScopes.length === 0 ? (
                <p className="text-[13px] text-muted-foreground">
                  No provider scopes. Access is limited to the credentials you
                  enter ({AUTH_LABELS[d.auth_type]}).
                </p>
              ) : (
                <div className="space-y-4">
                  <ScopeList title="Required" scopes={d.required_scopes} />
                  {optionalScopes.length > 0 && (
                    <ScopeList
                      title="Optional (requested only if you enable the feature)"
                      scopes={optionalScopes}
                    />
                  )}
                </div>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Capabilities" />
            <CardBody>
              <ul className="grid gap-2 sm:grid-cols-2">
                {d.capabilities.map((c) => (
                  <li
                    key={c}
                    className="flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-[13px]"
                  >
                    <Check className="size-4 text-success" aria-hidden="true" />
                    {capabilityLabel(c)}
                  </li>
                ))}
              </ul>
            </CardBody>
          </Card>

          <RelatedList
            title="Connections in this environment"
            items={connections.data?.items}
            loading={connections.isPending}
            getKey={(c) => c.id}
            empty={
              planned
                ? "Planned integrations can't have connections."
                : "No connections yet."
            }
            render={(c) => (
              <Link
                href={`/settings/integrations/connections/${c.id}`}
                className="flex flex-wrap items-center justify-between gap-2 rounded-md px-2 py-2 hover:bg-surface-muted"
              >
                <span className="min-w-0">
                  <span className="block truncate text-[13px] font-medium">
                    {c.display_name}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {c.mode} · last success <When value={c.last_success_at} />
                  </span>
                </span>
                <StateBadge value={c.status} />
              </Link>
            )}
          />
          {connections.isError && (
            <ErrorState
              compact
              error={connections.error}
              onRetry={() => void connections.refetch()}
            />
          )}
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader title="Details" />
            <CardBody>
              <PropertyList
                items={[
                  {
                    label: "Availability",
                    value: <StateBadge value={d.availability} />,
                  },
                  { label: "Category", value: CATEGORY_LABELS[d.category] },
                  { label: "Provider", value: d.provider },
                  { label: "Authentication", value: AUTH_LABELS[d.auth_type] },
                  {
                    label: "Inbound webhooks",
                    value: d.webhook_support ? "Supported" : "Not supported",
                  },
                  {
                    label: "Sync",
                    value: syncDirections.length
                      ? syncDirections
                          .map((s) =>
                            s === "bidirectional"
                              ? "Two-way"
                              : s === "pull"
                                ? "Pull"
                                : "Push",
                          )
                          .join(", ")
                      : "None",
                  },
                  {
                    label: "Sandbox",
                    value: d.supports_sandbox ? "Supported" : "Not offered",
                  },
                  { label: "Adapter version", value: d.version },
                  {
                    label: "Documentation",
                    value: d.documentation_url ? (
                      <a
                        href={d.documentation_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-primary hover:underline"
                      >
                        Open{" "}
                        <ArrowUpRight className="size-3.5" aria-hidden="true" />
                      </a>
                    ) : (
                      "None"
                    ),
                  },
                ]}
              />
            </CardBody>
          </Card>
          {d.config_schema.length > 0 && (
            <Card>
              <CardHeader
                title="You'll need"
                description="Fields asked for when connecting."
              />
              <CardBody>
                <ul className="space-y-1.5 text-[13px]">
                  {d.config_schema.map((f) => (
                    <li
                      key={f.key}
                      className="flex items-center justify-between gap-2"
                    >
                      <span>{f.label}</span>
                      <span className="flex gap-1">
                        {f.secret && <Badge tone="outline">Secret</Badge>}
                        {!f.required && <Badge tone="neutral">Optional</Badge>}
                      </span>
                    </li>
                  ))}
                </ul>
              </CardBody>
            </Card>
          )}
        </div>
      </div>

      {connectOpen && !planned && (
        <ConnectDialog definition={d} onClose={closeConnect} />
      )}
    </PageShell>
  );
}

function ScopeList({ title, scopes }: { title: string; scopes: string[] }) {
  return (
    <div>
      <h3 className="mb-1.5 text-xs font-medium text-muted-foreground">
        {title}
      </h3>
      <ul className="divide-y divide-border rounded-lg border border-border">
        {scopes.map((s) => {
          const elevated = isElevatedScope(s);
          return (
            <li
              key={s}
              className="flex flex-wrap items-center justify-between gap-2 px-3 py-2"
            >
              <code className="font-mono text-xs break-all">{s}</code>
              {elevated ? (
                <Badge tone="warning">
                  <ShieldAlert aria-hidden="true" /> Elevated: can change data
                  or act for you
                </Badge>
              ) : (
                <Badge tone="neutral">Standard</Badge>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
