"use client";

import { useEffect, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  Archive,
  ArchiveRestore,
  Info,
  Layers,
  Pencil,
  Plus,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input, NativeSelect } from "@/components/ui/input";
import { Badge, Card, Skeleton } from "@/components/ui/display";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  Tooltip,
} from "@/components/ui/overlays";
import {
  PageHeader,
  PageShell,
  RequirePermission,
} from "@/components/app/page";
import { ConfirmDialog, FormField } from "@/components/app/forms";
import {
  EmptyState,
  ErrorState,
  InlineError,
  Notice,
} from "@/components/app/states";
import { StatusBadge } from "@/components/app/status-badge";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import { ApiError, errorMessage } from "@/services/api-client";
import type { Environment } from "@/features/auth/types";
import { adminService } from "./service";
import { SLUG, slugify } from "./lib";

const KINDS: { value: Environment["kind"]; label: string; help: string }[] = [
  {
    value: "production",
    label: "Production",
    help: "Live customers and real WhatsApp numbers.",
  },
  {
    value: "staging",
    label: "Staging",
    help: "Rehearse changes with production-like setup.",
  },
  {
    value: "development",
    label: "Development",
    help: "Experiments and testing.",
  },
];

const createSchema = z.object({
  name: z
    .string()
    .trim()
    .min(2, "Use at least 2 characters")
    .max(80, "Keep the name under 80 characters"),
  key: z
    .string()
    .trim()
    .refine(
      (v) => SLUG.test(v),
      "Use 2–48 lowercase letters, digits or dashes, starting with a letter",
    ),
  kind: z.enum(["production", "staging", "development"]),
});
const renameSchema = createSchema.pick({ name: true });

export function EnvironmentsPage() {
  return (
    <RequirePermission
      permission="admin.environments.manage"
      area="environments"
    >
      <EnvironmentsContent />
    </RequirePermission>
  );
}

function EnvironmentsContent() {
  const { session } = useSession();
  const envs = useScopedQuery(["admin", "environments"], () =>
    adminService.environments(),
  );
  const [creating, setCreating] = useState(false);
  const [renaming, setRenaming] = useState<Environment | null>(null);
  const [archiving, setArchiving] = useState<Environment | null>(null);
  const setStatus = useScopedMutation(
    ({ env, status }: { env: Environment; status: Environment["status"] }) =>
      adminService.updateEnvironment(env.id, { name: env.name, status }),
    {
      invalidate: [["admin", "environments"]],
      invalidateGlobal: [["workspace-options"]],
      success: (env) =>
        env.status === "archived"
          ? `${env.name} archived`
          : `${env.name} restored`,
      onSuccess: () => setArchiving(null),
    },
  );
  const sorted = envs.data
    ? [...envs.data].sort(
        (a, b) =>
          Number(b.is_default) - Number(a.is_default) ||
          a.status.localeCompare(b.status) ||
          a.name.localeCompare(b.name),
      )
    : undefined;

  return (
    <PageShell width="default">
      <PageHeader
        title="Environments"
        description="Separate spaces for production, staging and development within this workspace."
        actions={
          <Button onClick={() => setCreating(true)}>
            <Plus /> New environment
          </Button>
        }
      />
      <Notice
        tone="info"
        icon={Info}
        className="mb-5"
        title="Each environment is isolated"
      >
        Business data, PI configuration and WhatsApp numbers are kept separate
        per environment. Switch environments from the workspace switcher.
      </Notice>

      {envs.isPending ? (
        <div className="grid gap-3 md:grid-cols-2">
          {Array.from({ length: 3 }, (_, i) => (
            <Skeleton key={i} className="h-36 rounded-xl" />
          ))}
        </div>
      ) : envs.isError ? (
        <ErrorState error={envs.error} onRetry={() => void envs.refetch()} />
      ) : !sorted?.length ? (
        <EmptyState
          icon={Layers}
          title="No environments"
          description="Create a production environment to start working."
          action={
            <Button onClick={() => setCreating(true)}>
              <Plus /> New environment
            </Button>
          }
        />
      ) : (
        <ul className="grid gap-3 md:grid-cols-2">
          {sorted.map((env) => {
            const current = env.id === session?.environment?.id;
            const protectedEnv = env.is_default || current;
            const archived = env.status === "archived";
            return (
              <li key={env.id}>
                <Card
                  className={cn(
                    "flex h-full flex-col p-4",
                    archived && "bg-surface-muted/50",
                  )}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <h2
                        className={cn(
                          "truncate text-[15px] font-semibold",
                          archived && "text-muted-foreground",
                        )}
                      >
                        {env.name}
                      </h2>
                      <p className="mt-0.5 font-mono text-xs text-muted-foreground">
                        {env.key}
                      </p>
                    </div>
                    <StatusBadge status={env.kind} />
                  </div>
                  <div className="mt-3 flex flex-wrap items-center gap-1.5">
                    <StatusBadge status={env.status} />
                    {env.is_default && <Badge tone="primary">Default</Badge>}
                    {current && <Badge tone="info">Current</Badge>}
                  </div>
                  <div className="mt-auto flex flex-wrap gap-2 pt-4">
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => setRenaming(env)}
                    >
                      <Pencil /> Rename
                    </Button>
                    {archived ? (
                      <Button
                        variant="secondary"
                        size="sm"
                        loading={
                          setStatus.isPending &&
                          setStatus.variables?.env.id === env.id
                        }
                        onClick={() =>
                          setStatus.mutate({ env, status: "active" })
                        }
                      >
                        <ArchiveRestore /> Restore
                      </Button>
                    ) : (
                      <Tooltip
                        content={
                          env.is_default
                            ? "The default environment can't be archived"
                            : "You're working in this environment"
                        }
                        disabled={!protectedEnv}
                      >
                        <span>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setArchiving(env)}
                            disabled={protectedEnv}
                          >
                            <Archive /> Archive
                          </Button>
                        </span>
                      </Tooltip>
                    )}
                  </div>
                </Card>
              </li>
            );
          })}
        </ul>
      )}

      {creating && <CreateEnvironmentDialog open onOpenChange={setCreating} />}
      {renaming && (
        <RenameEnvironmentDialog
          env={renaming}
          onClose={() => setRenaming(null)}
        />
      )}
      <ConfirmDialog
        open={archiving !== null}
        onOpenChange={(open) => !open && setArchiving(null)}
        title={`Archive ${archiving?.name ?? "environment"}?`}
        description="Archived environments are hidden from the workspace switcher. You can restore them later."
        consequences={[
          "Members can no longer switch into this environment.",
          "Its data, PI configuration and WhatsApp numbers are kept, not deleted.",
          "PI stops replying on WhatsApp numbers connected to this environment.",
        ]}
        confirmLabel="Archive environment"
        destructive
        loading={setStatus.isPending}
        onConfirm={() =>
          archiving && setStatus.mutate({ env: archiving, status: "archived" })
        }
      />
    </PageShell>
  );
}

function CreateEnvironmentDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  type Values = z.infer<typeof createSchema>;
  const empty: Values = { name: "", key: "", kind: "staging" };
  const form = useForm<Values>({
    resolver: zodResolver(createSchema),
    defaultValues: empty,
  });
  const [serverError, setServerError] = useState<string | null>(null);
  const [keyTouched, setKeyTouched] = useState(false);
  const { setValue } = form;
  const name = useWatch({ control: form.control, name: "name" });
  const kind = useWatch({ control: form.control, name: "kind" });
  useEffect(() => {
    if (!keyTouched) setValue("key", slugify(name));
  }, [name, keyTouched, setValue]);
  const create = useScopedMutation(
    (input: Values) =>
      adminService.createEnvironment({
        key: input.key.trim(),
        name: input.name.trim(),
        kind: input.kind,
      }),
    {
      invalidate: [["admin", "environments"]],
      invalidateGlobal: [["workspace-options"]],
      success: (env) => `${env.name} created`,
    },
  );
  const e = form.formState.errors;
  const saving = create.isPending;
  return (
    <Dialog open={open} onOpenChange={(next) => !saving && onOpenChange(next)}>
      <DialogContent size="sm">
        <DialogHeader
          title="New environment"
          description="Starts empty: no business data, PI configuration or WhatsApp number."
        />
        <form
          noValidate
          className="flex min-h-0 flex-1 flex-col"
          onSubmit={form.handleSubmit(async (v) => {
            setServerError(null);
            try {
              await create.mutateAsync(v);
              onOpenChange(false);
            } catch (error) {
              if (error instanceof ApiError && error.status === 409)
                form.setError("key", {
                  type: "server",
                  message: errorMessage(error),
                });
              else
                setServerError(
                  errorMessage(error, "The environment could not be created."),
                );
            }
          })}
        >
          <DialogBody className="space-y-4">
            <FormField label="Name" htmlFor="env-name" required error={e.name}>
              <Input
                id="env-name"
                autoComplete="off"
                disabled={saving}
                aria-invalid={!!e.name || undefined}
                {...form.register("name")}
              />
            </FormField>
            <FormField
              label="Key"
              htmlFor="env-key"
              required
              error={e.key}
              help="Stable identifier, e.g. staging. Can't be changed later."
            >
              <Input
                id="env-key"
                autoComplete="off"
                className="font-mono"
                disabled={saving}
                aria-invalid={!!e.key || undefined}
                {...form.register("key", {
                  onChange: () => setKeyTouched(true),
                })}
              />
            </FormField>
            <FormField
              label="Kind"
              htmlFor="env-kind"
              required
              help={KINDS.find((k) => k.value === kind)?.help}
            >
              <NativeSelect
                id="env-kind"
                disabled={saving}
                {...form.register("kind")}
              >
                {KINDS.map((k) => (
                  <option key={k.value} value={k.value}>
                    {k.label}
                  </option>
                ))}
              </NativeSelect>
            </FormField>
            {serverError && <InlineError message={serverError} />}
          </DialogBody>
          <DialogFooter>
            <Button
              type="button"
              variant="secondary"
              onClick={() => onOpenChange(false)}
              disabled={saving}
            >
              Cancel
            </Button>
            <Button type="submit" loading={saving}>
              Create environment
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function RenameEnvironmentDialog({
  env,
  onClose,
}: {
  env: Environment;
  onClose: () => void;
}) {
  const form = useForm<z.infer<typeof renameSchema>>({
    resolver: zodResolver(renameSchema),
    defaultValues: { name: env.name },
  });
  const [serverError, setServerError] = useState<string | null>(null);
  const rename = useScopedMutation(
    (name: string) =>
      adminService.updateEnvironment(env.id, { name, status: env.status }),
    {
      invalidate: [["admin", "environments"]],
      invalidateGlobal: [["workspace-options"]],
      success: "Environment renamed",
    },
  );
  const e = form.formState.errors;
  return (
    <Dialog
      open
      onOpenChange={(open) => !open && !rename.isPending && onClose()}
    >
      <DialogContent size="sm">
        <DialogHeader
          title={`Rename ${env.name}`}
          description={`Key ${env.key} stays the same.`}
        />
        <form
          noValidate
          className="flex min-h-0 flex-1 flex-col"
          onSubmit={form.handleSubmit(async (v) => {
            setServerError(null);
            try {
              await rename.mutateAsync(v.name.trim());
              onClose();
            } catch (error) {
              setServerError(
                errorMessage(error, "The environment could not be renamed."),
              );
            }
          })}
        >
          <DialogBody className="space-y-4">
            <FormField
              label="Name"
              htmlFor="env-rename"
              required
              error={e.name}
            >
              <Input
                id="env-rename"
                autoComplete="off"
                disabled={rename.isPending}
                aria-invalid={!!e.name || undefined}
                {...form.register("name")}
              />
            </FormField>
            {serverError && <InlineError message={serverError} />}
          </DialogBody>
          <DialogFooter>
            <Button
              type="button"
              variant="secondary"
              onClick={onClose}
              disabled={rename.isPending}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              loading={rename.isPending}
              disabled={!form.formState.isDirty}
            >
              Save
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
