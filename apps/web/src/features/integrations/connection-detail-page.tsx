"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { toast } from "sonner";
import {
  Activity,
  ArrowRight,
  Ban,
  FlaskConical,
  KeyRound,
  Pencil,
  Play,
  Power,
  RefreshCw,
  SearchX,
  Unplug,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge, Card, CardBody, CardHeader } from "@/components/ui/display";
import { NativeSelect } from "@/components/ui/input";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/overlays";
import { PageShell, RequirePermission } from "@/components/app/page";
import { PageSkeleton } from "@/components/app/page-skeleton";
import {
  ActivityTimeline,
  PropertyList,
  RecordHeader,
  type TimelineEvent,
} from "@/components/app/record";
import { ConfirmDialog, FormField } from "@/components/app/forms";
import {
  EmptyState,
  ErrorState,
  InlineError,
  Notice,
} from "@/components/app/states";
import { StatusBadge } from "@/components/app/status-badge";
import { useBreadcrumbs } from "@/components/shell/breadcrumbs";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import { ApiError, errorMessage } from "@/services/api-client";
import { formatDateTime, humanize } from "@/lib/format";
import { integrationsService } from "./service";
import {
  categoryIcon,
  CircuitBadge,
  CredentialHint,
  GatedButton,
  StateBadge,
  TestResultPanel,
  When,
  useDefinitions,
} from "./components";
import { EditConfigDialog, RotateCredentialsDialog } from "./connection-forms";
import {
  DISABLEABLE,
  formatLatency,
  isOAuth,
  supportsSync,
  syncEntities,
  TESTABLE,
} from "./lib";
import type {
  ConnectionDetail,
  IntegrationDefinition,
  TestResult,
} from "./types";

export function ConnectionDetailPage({
  connectionId,
}: {
  connectionId: string;
}) {
  return (
    <RequirePermission permission="integrations.read" area="integrations">
      <Loader connectionId={connectionId} />
    </RequirePermission>
  );
}

function Loader({ connectionId }: { connectionId: string }) {
  const connection = useScopedQuery(
    ["integrations", "connection", connectionId],
    () => integrationsService.connection(connectionId),
  );
  const definitions = useDefinitions();
  if (connection.isPending || definitions.isPending)
    return <PageSkeleton variant="detail" />;
  if (
    connection.isError &&
    connection.error instanceof ApiError &&
    connection.error.status === 404
  )
    return (
      <PageShell width="default">
        <h1 className="sr-only">Connection not found</h1>
        <EmptyState
          icon={SearchX}
          title="Connection not found"
          description="It may belong to another workspace or environment."
          action={
            <Button variant="secondary" asChild>
              <Link href="/settings/integrations">Back to integrations</Link>
            </Button>
          }
        />
      </PageShell>
    );
  if (connection.isError || definitions.isError)
    return (
      <PageShell width="default">
        <h1 className="sr-only">Connection</h1>
        <ErrorState
          error={connection.error ?? definitions.error}
          onRetry={() => {
            void connection.refetch();
            void definitions.refetch();
          }}
        />
      </PageShell>
    );
  const definition = definitions.data.find(
    (d) => d.key === connection.data.integration_key,
  );
  return (
    <ConnectionDetailView
      connection={connection.data}
      definition={definition}
    />
  );
}

function activityKind(kind: string, outcome: string): string {
  if (kind === "created") return "created";
  if (["config_updated", "credentials_rotated"].includes(kind))
    return "updated";
  if (outcome === "failure" || outcome === "warning") return "system";
  return "status";
}

function ConnectionDetailView({
  connection: c,
  definition: d,
}: {
  connection: ConnectionDetail;
  definition: IntegrationDefinition | undefined;
}) {
  const { session } = useSession();
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  useBreadcrumbs([{ label: c.display_name }], {
    href: `/settings/integrations/connections/${c.id}`,
    kind: "Connection",
  });

  const [result, setResult] = useState<TestResult | null>(null);
  const [dialog, setDialog] = useState<
    "edit" | "rotate" | "disconnect" | "sync" | null
  >(null);

  // OAuth callback lands here with ?oauth=ok|error; report it once and clean the URL.
  const oauth = params.get("oauth");
  useEffect(() => {
    if (!oauth) return;
    if (oauth === "ok")
      toast.success("Authorization completed. The provider granted access.");
    else
      toast.error(
        "Authorization didn't complete. Nothing was changed; try reconnecting.",
      );
    router.replace(pathname, { scroll: false });
  }, [oauth, pathname, router]);

  const invalidate = [["integrations"]];
  const test = useScopedMutation(
    () => integrationsService.testConnection(c.id),
    {
      invalidate,
      onSuccess: (r) => setResult(r),
    },
  );
  const enable = useScopedMutation(
    () => integrationsService.enableConnection(c.id),
    {
      invalidate,
      success: (r) =>
        r.status === "connected"
          ? "Enabled and verified"
          : `Enabled; current status: ${humanize(r.status)}`,
    },
  );
  const disable = useScopedMutation(
    () => integrationsService.disableConnection(c.id),
    {
      invalidate,
      success: "Connection disabled",
    },
  );
  const disconnect = useScopedMutation(
    () => integrationsService.disconnect(c.id),
    {
      invalidate,
      success: "Disconnected. Credentials were revoked.",
      onSuccess: () => setDialog(null),
    },
  );
  const startOAuth = useScopedMutation(
    () => integrationsService.startOAuth(c.id),
    {
      onSuccess: ({ authorization_url }) =>
        window.location.assign(authorization_url),
    },
  );

  const oauthDef = d ? isOAuth(d.auth_type) : false;
  const secretFields = d?.config_schema.filter((f) => f.secret) ?? [];
  const plainFields = d?.config_schema.filter((f) => !f.secret) ?? [];
  const revoked = c.status === "revoked";
  const disabled = c.status === "disabled";
  const testBlocked = revoked
    ? "Disconnected: reconnect before testing"
    : disabled
      ? "Disabled: enable it before testing"
      : !TESTABLE.includes(c.status)
        ? "Can't be tested in its current state"
        : null;
  const envName =
    session?.environment?.id === c.environment_id
      ? session.environment.name
      : c.environment_id;
  const envKind =
    session?.environment?.id === c.environment_id
      ? session.environment.kind
      : null;

  const reconnect = () => {
    if (oauthDef) startOAuth.mutate(undefined);
    else setDialog("rotate");
  };

  const timeline: TimelineEvent[] = c.recent_activity.map((a, i) => ({
    id: `${a.at}-${i}`,
    kind: activityKind(a.kind, a.outcome),
    title: a.message,
    description: `${humanize(a.kind)} · ${humanize(a.outcome)}`,
    at: a.at,
  }));

  return (
    <PageShell width="wide">
      <RecordHeader
        icon={categoryIcon(d?.category)}
        title={c.display_name}
        status={<StateBadge value={c.status} />}
        subtitle={
          d ? (
            <Link
              href={`/settings/integrations/${d.key}`}
              className="hover:underline"
            >
              {d.name}
            </Link>
          ) : (
            c.integration_key
          )
        }
        meta={
          <>
            <span className="inline-flex items-center gap-1.5">
              Workspace:{" "}
              <span className="font-medium text-foreground">
                {session?.tenant?.name ?? "—"}
              </span>
            </span>
            <span className="inline-flex items-center gap-1.5">
              Environment:{" "}
              <span className="font-medium text-foreground">{envName}</span>
              {envKind && envKind !== String(envName).toLowerCase() && (
                <StatusBadge status={envKind} />
              )}
            </span>
            <span className="inline-flex items-center gap-1.5">
              Mode: <StateBadge value={c.mode} />
            </span>
          </>
        }
        actions={
          <>
            <GatedButton
              size="sm"
              variant="secondary"
              permission="integrations.operate"
              blockedReason={testBlocked}
              loading={test.isPending}
              onClick={() => test.mutate(undefined)}
            >
              <FlaskConical /> Test connection
            </GatedButton>
            {disabled ? (
              <GatedButton
                size="sm"
                variant="secondary"
                permission="integrations.manage"
                loading={enable.isPending}
                onClick={() => enable.mutate(undefined)}
              >
                <Power /> Enable
              </GatedButton>
            ) : (
              <GatedButton
                size="sm"
                variant="secondary"
                permission="integrations.manage"
                blockedReason={
                  !DISABLEABLE.includes(c.status)
                    ? "Can't be disabled in its current state"
                    : null
                }
                loading={disable.isPending}
                onClick={() => disable.mutate(undefined)}
              >
                <Ban /> Disable
              </GatedButton>
            )}
            {(revoked ||
              ["expired", "error"].includes(c.status) ||
              (oauthDef && !c.connected_at)) && (
              <GatedButton
                size="sm"
                permission="integrations.manage"
                blockedReason={disabled ? "Enable the connection first" : null}
                loading={startOAuth.isPending}
                onClick={reconnect}
              >
                <RefreshCw />{" "}
                {oauthDef && !c.connected_at && !revoked
                  ? `Authorize with ${d?.provider}`
                  : "Reconnect"}
              </GatedButton>
            )}
            <GatedButton
              size="sm"
              variant="danger-outline"
              permission="integrations.manage"
              blockedReason={revoked ? "Already disconnected" : null}
              onClick={() => setDialog("disconnect")}
            >
              <Unplug /> Disconnect
            </GatedButton>
          </>
        }
      />

      <div className="mb-4 space-y-3">
        {revoked && (
          <Notice tone="neutral" icon={Unplug} title="Disconnected">
            Credentials were revoked and nothing is sent or received. The record
            is kept for audit. Reconnect to use it again.
          </Notice>
        )}
        {disabled && (
          <Notice tone="neutral" icon={Ban} title="Disabled">
            Calls, webhooks and sync for this connection are paused. Stored
            credentials are kept.
          </Notice>
        )}
        {c.status === "draft" && !revoked && (
          <Notice tone="warning" title="Not verified yet">
            This connection hasn&apos;t passed a test, so it isn&apos;t used.{" "}
            {oauthDef && !c.connected_at
              ? "Authorize access with the provider to finish."
              : "Run a test once the credentials are correct."}
          </Notice>
        )}
        {c.last_error && !revoked && (
          <Notice
            tone={c.status === "error" ? "danger" : "warning"}
            title="Last error"
          >
            <span className="break-words">{c.last_error}</span>
            {c.last_failure_at && (
              <span className="block text-xs text-muted-foreground">
                {formatDateTime(c.last_failure_at)}
              </span>
            )}
          </Notice>
        )}
        {result && <TestResultPanel result={result} />}
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="min-w-0 space-y-4">
          <Card>
            <CardHeader
              title="Health"
              icon={<Activity />}
              description="From recorded calls and the last test. Viewing it never calls the provider."
            />
            <CardBody>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3">
                <Stat label="Health" value={<StateBadge value={c.health} />} />
                <Stat
                  label="Circuit"
                  value={<CircuitBadge value={c.circuit_state} />}
                />
                <Stat
                  label="Latency"
                  value={
                    <span className="tabular">
                      {formatLatency(c.health_detail.latency_ms)}
                    </span>
                  }
                />
                <Stat
                  label="Consecutive failures"
                  value={
                    <span className="tabular">
                      {c.health_detail.consecutive_failures}
                    </span>
                  }
                />
                <Stat
                  label="Rate limited until"
                  value={
                    c.health_detail.rate_limited_until ? (
                      <span className="text-warning">
                        {formatDateTime(c.health_detail.rate_limited_until)}
                      </span>
                    ) : (
                      "Not limited"
                    )
                  }
                />
                <Stat
                  label="Last health check"
                  value={<When value={c.last_health_check_at} />}
                />
                <Stat
                  label="Last success"
                  value={<When value={c.last_success_at} />}
                />
                <Stat
                  label="Last failure"
                  value={
                    <When value={c.last_failure_at} empty="None recorded" />
                  }
                />
                <Stat
                  label="Connected since"
                  value={<When value={c.connected_at} empty="Not yet" />}
                />
              </dl>
            </CardBody>
          </Card>

          <Card>
            <CardHeader
              title="Configuration"
              actions={
                plainFields.length > 0 && d ? (
                  <GatedButton
                    size="xs"
                    variant="secondary"
                    permission="integrations.manage"
                    blockedReason={
                      revoked
                        ? "Disconnected connections can't be edited"
                        : null
                    }
                    onClick={() => setDialog("edit")}
                  >
                    <Pencil /> Edit
                  </GatedButton>
                ) : null
              }
            />
            <CardBody>
              {plainFields.length === 0 ? (
                <p className="text-[13px] text-muted-foreground">
                  No configuration fields.
                </p>
              ) : (
                <PropertyList
                  items={plainFields.map((f) => ({
                    label: f.label,
                    value:
                      c.config[f.key] === undefined ||
                      c.config[f.key] === "" ? null : (
                        <span className="font-mono text-xs break-all">
                          {String(c.config[f.key])}
                        </span>
                      ),
                  }))}
                />
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader
              title="Credentials"
              icon={<KeyRound />}
              description="Write-only. Values are never shown after saving; only whether they're set and a short hint."
              actions={
                secretFields.length > 0 && d ? (
                  <GatedButton
                    size="xs"
                    variant="secondary"
                    permission="integrations.manage"
                    onClick={() => setDialog("rotate")}
                  >
                    <RefreshCw /> Rotate credentials
                  </GatedButton>
                ) : null
              }
            />
            <CardBody className="space-y-3">
              {c.credentials.length > 0 ? (
                <ul
                  className="divide-y divide-border rounded-lg border border-border"
                  data-testid="credentials"
                >
                  {c.credentials.map((cred) => (
                    <li
                      key={cred.key}
                      className="flex flex-wrap items-center justify-between gap-2 px-3 py-2"
                    >
                      <span className="text-[13px]">
                        {d?.config_schema.find((f) => f.key === cred.key)
                          ?.label ?? humanize(cred.key)}
                      </span>
                      <CredentialHint credential={cred} />
                    </li>
                  ))}
                </ul>
              ) : oauthDef ? (
                <p className="text-[13px] text-muted-foreground">
                  Authorized with OAuth; tokens are held by the server and
                  refreshed automatically.
                </p>
              ) : (
                <p className="text-[13px] text-muted-foreground">
                  No credentials required.
                </p>
              )}
              {(c.scopes.length > 0 || (d && d.required_scopes.length > 0)) && (
                <div>
                  <h3 className="mb-1.5 text-xs font-medium text-muted-foreground">
                    Granted scopes
                  </h3>
                  {c.scopes.length ? (
                    <div className="flex flex-wrap gap-1.5">
                      {c.scopes.map((s) => (
                        <Badge key={s} tone="outline" className="font-mono">
                          {s}
                        </Badge>
                      ))}
                    </div>
                  ) : (
                    <p className="text-[13px] text-muted-foreground">
                      None granted yet.
                    </p>
                  )}
                </div>
              )}
            </CardBody>
          </Card>
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader title="Scope" />
            <CardBody>
              <PropertyList
                items={[
                  { label: "Workspace", value: session?.tenant?.name ?? "—" },
                  { label: "Environment", value: envName },
                  { label: "Mode", value: <StateBadge value={c.mode} /> },
                  { label: "Integration", value: d?.name ?? c.integration_key },
                  {
                    label: "Sync direction",
                    value:
                      c.sync_direction === "none"
                        ? "None"
                        : humanize(c.sync_direction),
                  },
                  {
                    label: "Expires",
                    value: c.expires_at
                      ? formatDateTime(c.expires_at)
                      : "Doesn't expire",
                  },
                  { label: "Created", value: formatDateTime(c.created_at) },
                ]}
              />
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Related" />
            <CardBody>
              <ul className="space-y-1">
                {d?.webhook_support && (
                  <RelatedLink
                    href={`/settings/integrations/events?connection=${c.id}`}
                    label="Inbound events"
                  />
                )}
                {supportsSync(d) && (
                  <RelatedLink
                    href={`/settings/integrations/jobs?connection=${c.id}`}
                    label="Sync jobs"
                  />
                )}
                <RelatedLink
                  href="/settings/integrations/failures"
                  label="Failures"
                />
                <RelatedLink
                  href="/settings/integrations/health"
                  label="Health overview"
                />
              </ul>
              {supportsSync(d) && (
                <GatedButton
                  size="sm"
                  variant="secondary"
                  className="mt-3 w-full"
                  permission="integrations.operate"
                  blockedReason={
                    !["connected", "degraded"].includes(c.status)
                      ? "Only connected integrations can sync"
                      : null
                  }
                  onClick={() => setDialog("sync")}
                >
                  <Play /> Run sync
                </GatedButton>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Recent activity" />
            <CardBody>
              <ActivityTimeline
                events={timeline}
                empty="No activity recorded yet."
              />
            </CardBody>
          </Card>
        </div>
      </div>

      {dialog === "edit" && d && (
        <EditConfigDialog
          connection={c}
          definition={d}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === "rotate" && d && (
        <RotateCredentialsDialog
          connection={c}
          definition={d}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === "sync" && d && (
        <RunSyncDialog
          connection={c}
          definition={d}
          onClose={() => setDialog(null)}
        />
      )}
      <ConfirmDialog
        open={dialog === "disconnect"}
        onOpenChange={(open) => !open && setDialog(null)}
        title={`Disconnect ${c.display_name}?`}
        description="This can't be undone. You can reconnect later with new credentials."
        consequences={[
          "Stored credentials are revoked and deleted.",
          "Outbound calls, inbound webhooks and sync for this connection stop immediately.",
          "The connection record and its history are kept for audit.",
        ]}
        confirmLabel="Disconnect"
        destructive
        loading={disconnect.isPending}
        onConfirm={() => disconnect.mutate(undefined)}
      />
    </PageShell>
  );
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 text-[13px] font-medium">{value}</dd>
    </div>
  );
}

function RelatedLink({ href, label }: { href: string; label: string }) {
  return (
    <li>
      <Link
        href={href}
        className="flex items-center justify-between rounded-md px-2 py-1.5 text-[13px] font-medium text-foreground hover:bg-surface-muted"
      >
        {label}{" "}
        <ArrowRight
          className="size-3.5 text-muted-foreground"
          aria-hidden="true"
        />
      </Link>
    </li>
  );
}

function RunSyncDialog({
  connection,
  definition,
  onClose,
}: {
  connection: ConnectionDetail;
  definition: IntegrationDefinition;
  onClose: () => void;
}) {
  const entities = syncEntities(definition);
  const [entity, setEntity] = useState(entities[0] ?? "");
  const [mode, setMode] = useState<"incremental" | "full">("incremental");
  const [error, setError] = useState<string | null>(null);
  const run = useScopedMutation(
    () => integrationsService.startSync(connection.id, { entity, mode }),
    {
      invalidate: [["integrations"]],
      toastErrors: false,
      success: (j) => `${humanize(j.entity)} sync queued`,
    },
  );
  return (
    <Dialog open onOpenChange={(open) => !open && !run.isPending && onClose()}>
      <DialogContent size="sm">
        <DialogHeader
          title="Run sync"
          description={`Queue a sync job for ${connection.display_name}.`}
        />
        <form
          className="flex min-h-0 flex-1 flex-col"
          onSubmit={async (e) => {
            e.preventDefault();
            setError(null);
            try {
              await run.mutateAsync(undefined);
              onClose();
            } catch (err) {
              setError(
                err instanceof ApiError && err.fields.entity
                  ? err.fields.entity
                  : errorMessage(err, "The sync couldn't be started."),
              );
            }
          }}
        >
          <DialogBody className="space-y-4">
            <FormField label="Records" htmlFor="sync-entity" required>
              <NativeSelect
                id="sync-entity"
                value={entity}
                onChange={(e) => setEntity(e.target.value)}
                disabled={run.isPending}
              >
                {entities.map((en) => (
                  <option key={en} value={en}>
                    {humanize(en)}
                  </option>
                ))}
              </NativeSelect>
            </FormField>
            <FormField
              label="Mode"
              htmlFor="sync-mode"
              required
              help={
                mode === "full"
                  ? "Re-reads every record. Slower; use after fixing mapping problems."
                  : "Only records changed since the last successful sync."
              }
            >
              <NativeSelect
                id="sync-mode"
                value={mode}
                onChange={(e) =>
                  setMode(e.target.value as "incremental" | "full")
                }
                disabled={run.isPending}
              >
                <option value="incremental">Incremental</option>
                <option value="full">Full</option>
              </NativeSelect>
            </FormField>
            {error && <InlineError message={error} />}
          </DialogBody>
          <DialogFooter>
            <Button
              type="button"
              variant="secondary"
              onClick={onClose}
              disabled={run.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" loading={run.isPending} disabled={!entity}>
              Queue sync
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
