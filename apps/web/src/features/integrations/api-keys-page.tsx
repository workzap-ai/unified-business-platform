"use client";

import { useMemo, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { KeyRound, Plus, ShieldAlert, Trash2 } from "lucide-react";
import { formatDate } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/display";
import { Input, NativeSelect } from "@/components/ui/input";
import { Checkbox, Label } from "@/components/ui/controls";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/overlays";
import { RequirePermission } from "@/components/app/page";
import { DataTable, type Column } from "@/components/app/data-table";
import { ConfirmDialog, FormField } from "@/components/app/forms";
import { EmptyState, InlineError, Notice } from "@/components/app/states";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useUrlState } from "@/hooks/use-url-state";
import { useSession } from "@/features/auth/session-provider";
import { adminService } from "@/features/admin/service";
import { errorMessage } from "@/services/api-client";
import { integrationsService } from "./service";
import {
  applyServerFieldErrors,
  GatedButton,
  IntegrationsFrame,
  SecretReveal,
  StateBadge,
  When,
} from "./components";
import { isElevatedScope } from "./lib";
import type { ApiKey, ApiKeyCreated } from "./types";

export function ApiKeysPage() {
  return (
    <RequirePermission permission="api_keys.manage" area="API keys">
      <ApiKeys />
    </RequirePermission>
  );
}

function keyState(k: ApiKey): "revoked" | "expired" | "active" {
  if (k.revoked_at) return "revoked";
  if (k.expires_at && new Date(k.expires_at).getTime() < Date.now())
    return "expired";
  return "active";
}

function ApiKeys() {
  const { session } = useSession();
  const [state, setState] = useUrlState({ create: "" });
  const keys = useScopedQuery(["integrations", "api-keys"], () =>
    integrationsService.apiKeys(),
  );
  const [creating, setCreating] = useState(() => state.create === "1");
  const [revoking, setRevoking] = useState<ApiKey | null>(null);
  const revoke = useScopedMutation(
    (k: ApiKey) => integrationsService.revokeApiKey(k.id),
    {
      invalidate: [["integrations", "api-keys"]],
      success: "API key revoked",
      onSuccess: () => setRevoking(null),
    },
  );
  const live = session?.environment?.kind === "production";

  const columns: Column<ApiKey>[] = [
    {
      key: "name",
      header: "Key",
      cell: (k) => (
        <div className="min-w-0">
          <p className="truncate font-medium">{k.name}</p>
          <p className="truncate font-mono text-xs text-muted-foreground">
            {k.prefix}_••••
          </p>
        </div>
      ),
    },
    {
      key: "state",
      header: "Status",
      cell: (k) => {
        const s = keyState(k);
        return (
          <StateBadge
            value={
              s === "active"
                ? "connected"
                : s === "expired"
                  ? "expired"
                  : "revoked"
            }
            label={
              s === "active"
                ? "Active"
                : s === "expired"
                  ? "Expired"
                  : "Revoked"
            }
          />
        );
      },
    },
    {
      key: "scopes",
      header: "Scopes",
      hideBelow: "md",
      cell: (k) => (
        <div className="flex max-w-80 flex-wrap gap-1">
          {k.scopes.slice(0, 3).map((s) => (
            <Badge
              key={s}
              tone={isElevatedScope(s) ? "warning" : "outline"}
              className="font-mono"
            >
              {s}
            </Badge>
          ))}
          {k.scopes.length > 3 && (
            <Badge tone="neutral">+{k.scopes.length - 3}</Badge>
          )}
        </div>
      ),
    },
    {
      key: "last",
      header: "Last used",
      hideBelow: "lg",
      cell: (k) => <When value={k.last_used_at} />,
    },
    {
      key: "expires",
      header: "Expires",
      hideBelow: "lg",
      cell: (k) =>
        k.expires_at ? (
          formatDate(k.expires_at)
        ) : (
          <span className="text-muted-foreground">Never</span>
        ),
    },
    {
      key: "created",
      header: "Created",
      hideBelow: "xl",
      cell: (k) => (
        <span className="text-xs">
          {formatDate(k.created_at)}
          {k.created_by_name && (
            <span className="text-muted-foreground">
              {" "}
              by {k.created_by_name}
            </span>
          )}
        </span>
      ),
    },
    {
      key: "actions",
      header: <span className="sr-only">Actions</span>,
      align: "right",
      cell: (k) =>
        k.revoked_at ? null : (
          <Button
            variant="ghost"
            size="xs"
            className="text-danger"
            onClick={() => setRevoking(k)}
            aria-label={`Revoke ${k.name}`}
          >
            <Trash2 /> <span className="hidden sm:inline">Revoke</span>
          </Button>
        ),
    },
  ];

  return (
    <IntegrationsFrame
      title="API keys"
      description="Keys let your own software call this workspace's API. A key can never have more access than the person who created it."
      actions={
        <GatedButton
          permission="api_keys.manage"
          onClick={() => setCreating(true)}
        >
          <Plus /> Create API key
        </GatedButton>
      }
    >
      <Notice tone="info" icon={KeyRound} className="mb-4">
        Keys are scoped to{" "}
        <span className="font-medium">{session?.tenant?.name}</span> ·{" "}
        <span className="font-medium">{session?.environment?.name}</span> and
        start with{" "}
        <code className="font-mono">{live ? "pk_live_" : "pk_test_"}</code>.
        Secrets are shown once at creation.
      </Notice>
      <DataTable
        caption="API keys"
        columns={columns}
        rows={keys.data}
        loading={keys.isPending}
        error={keys.error}
        onRetry={() => void keys.refetch()}
        getRowId={(k) => k.id}
        loadingRows={3}
        rowClassName={(k) =>
          keyState(k) === "active" ? undefined : "opacity-60"
        }
        empty={
          <EmptyState
            icon={KeyRound}
            title="No API keys"
            description="Create a key for an internal tool or script. Give it only the scopes it needs."
            action={
              <Button onClick={() => setCreating(true)}>
                <Plus /> Create API key
              </Button>
            }
          />
        }
      />
      {creating && (
        <CreateKeyDialog
          onClose={() => {
            setCreating(false);
            if (state.create) setState({ create: "" });
          }}
        />
      )}
      <ConfirmDialog
        open={revoking !== null}
        onOpenChange={(open) => !open && setRevoking(null)}
        title={`Revoke ${revoking?.name ?? "key"}?`}
        description="This can't be undone."
        consequences={[
          "Requests using this key are rejected immediately.",
          "Anything that depends on it stops working until it has a new key.",
        ]}
        confirmLabel="Revoke key"
        destructive
        loading={revoke.isPending}
        onConfirm={() => revoking && revoke.mutate(revoking)}
      />
    </IntegrationsFrame>
  );
}

const keySchema = z.object({
  name: z
    .string()
    .trim()
    .min(1, "Name is required")
    .max(80, "Keep the name under 80 characters"),
  scopes: z.array(z.string()).min(1, "Choose at least one scope"),
  expiry: z.enum(["30", "90", "365", "never"]),
});
type KeyValues = z.infer<typeof keySchema>;

function CreateKeyDialog({ onClose }: { onClose: () => void }) {
  const { session } = useSession();
  const catalog = useScopedQuery(
    ["admin", "permissions"],
    () => adminService.permissions(),
    { retry: false },
  );
  const mine = useMemo(() => new Set(session?.permissions ?? []), [session]);
  // Only the creator's own permissions can be granted to a key.
  const groups = useMemo(() => {
    const labelled = new Map((catalog.data ?? []).map((p) => [p.key, p]));
    const grouped = new Map<string, { key: string; label: string }[]>();
    for (const key of [...mine].sort()) {
      const p = labelled.get(key);
      const group =
        p?.group ?? key.split(".")[0]!.replace(/^\w/, (c) => c.toUpperCase());
      grouped.set(group, [
        ...(grouped.get(group) ?? []),
        { key, label: p?.label ?? key },
      ]);
    }
    return [...grouped.entries()];
  }, [catalog.data, mine]);
  const form = useForm<KeyValues>({
    resolver: zodResolver(keySchema),
    defaultValues: { name: "", scopes: [], expiry: "90" },
  });
  const [serverError, setServerError] = useState<string | null>(null);
  const [created, setCreated] = useState<ApiKeyCreated | null>(null);
  const create = useScopedMutation(
    (v: KeyValues) =>
      integrationsService.createApiKey({
        name: v.name.trim(),
        scopes: v.scopes,
        expires_in_days: v.expiry === "never" ? null : Number(v.expiry),
      }),
    { invalidate: [["integrations", "api-keys"]], toastErrors: false },
  );
  const e = form.formState.errors;
  const busy = create.isPending;

  return (
    <Dialog open onOpenChange={(open) => !open && !busy && onClose()}>
      <DialogContent size="lg">
        {created ? (
          <>
            <DialogHeader
              title="API key created"
              description={`${created.name} · ${created.scopes.length} scope${created.scopes.length === 1 ? "" : "s"}`}
            />
            <DialogBody>
              <SecretReveal
                label="API key"
                secret={created.secret}
                onDone={onClose}
              />
            </DialogBody>
          </>
        ) : (
          <>
            <DialogHeader
              title="Create API key"
              description="Give the key only the access it needs. You can revoke it at any time."
            />
            <form
              noValidate
              className="flex min-h-0 flex-1 flex-col"
              onSubmit={form.handleSubmit(async (values) => {
                setServerError(null);
                try {
                  setCreated(await create.mutateAsync(values));
                } catch (error) {
                  const { mapped, leftovers } = applyServerFieldErrors(
                    error,
                    (key, message) => {
                      const field = key === "expires_in_days" ? "expiry" : key;
                      if (!["name", "scopes", "expiry"].includes(field))
                        return false;
                      form.setError(field as keyof KeyValues, {
                        type: "server",
                        message,
                      });
                      return true;
                    },
                  );
                  if (!mapped || leftovers.length)
                    setServerError(
                      leftovers[0] ??
                        errorMessage(error, "The key could not be created."),
                    );
                }
              })}
            >
              <DialogBody className="space-y-4">
                <div className="grid gap-4 sm:grid-cols-[1fr_180px]">
                  <FormField
                    label="Name"
                    htmlFor="key-name"
                    required
                    error={e.name}
                    help="Where it's used, e.g. “Warehouse scanner app”."
                  >
                    <Input
                      id="key-name"
                      autoComplete="off"
                      disabled={busy}
                      aria-invalid={!!e.name || undefined}
                      {...form.register("name")}
                    />
                  </FormField>
                  <FormField
                    label="Expires"
                    htmlFor="key-expiry"
                    required
                    error={e.expiry}
                  >
                    <NativeSelect
                      id="key-expiry"
                      disabled={busy}
                      {...form.register("expiry")}
                    >
                      <option value="30">In 30 days</option>
                      <option value="90">In 90 days</option>
                      <option value="365">In 1 year</option>
                      <option value="never">Never</option>
                    </NativeSelect>
                  </FormField>
                </div>
                <fieldset>
                  <legend className="mb-1 flex items-center gap-1 text-[13px] font-medium">
                    Scopes{" "}
                    <span className="text-danger" aria-hidden="true">
                      *
                    </span>
                  </legend>
                  <p className="mb-2 text-xs text-muted-foreground">
                    Limited to the permissions your role has. Highlighted scopes
                    can change data.
                  </p>
                  <Controller
                    control={form.control}
                    name="scopes"
                    render={({ field }) => (
                      <div className="scrollbar-thin max-h-72 space-y-3 overflow-y-auto rounded-lg border border-border p-3">
                        {groups.map(([group, perms]) => (
                          <div key={group}>
                            <p className="mb-1 text-2xs font-semibold tracking-wide text-muted-foreground uppercase">
                              {group}
                            </p>
                            <ul className="grid gap-1.5 sm:grid-cols-2">
                              {perms.map((p) => {
                                const id = `scope-${p.key}`;
                                return (
                                  <li
                                    key={p.key}
                                    className="flex items-start gap-2"
                                  >
                                    <Checkbox
                                      id={id}
                                      className="mt-0.5"
                                      disabled={busy}
                                      checked={field.value.includes(p.key)}
                                      onCheckedChange={(on) =>
                                        field.onChange(
                                          on
                                            ? [...field.value, p.key]
                                            : field.value.filter(
                                                (v) => v !== p.key,
                                              ),
                                        )
                                      }
                                    />
                                    <Label
                                      htmlFor={id}
                                      className="min-w-0 font-normal"
                                    >
                                      <span className="block text-[13px]">
                                        {p.label}
                                      </span>
                                      <span className="flex items-center gap-1 font-mono text-2xs text-muted-foreground">
                                        {p.key}
                                        {isElevatedScope(p.key) && (
                                          <ShieldAlert
                                            className="size-3 text-warning"
                                            aria-label="Can change data"
                                          />
                                        )}
                                      </span>
                                    </Label>
                                  </li>
                                );
                              })}
                            </ul>
                          </div>
                        ))}
                      </div>
                    )}
                  />
                  {e.scopes && (
                    <p
                      role="alert"
                      className="mt-1.5 text-xs font-medium text-danger"
                    >
                      {e.scopes.message}
                    </p>
                  )}
                </fieldset>
                {serverError && <InlineError message={serverError} />}
              </DialogBody>
              <DialogFooter>
                <Button
                  type="button"
                  variant="secondary"
                  onClick={onClose}
                  disabled={busy}
                >
                  Cancel
                </Button>
                <Button type="submit" loading={busy}>
                  Create key
                </Button>
              </DialogFooter>
            </form>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
