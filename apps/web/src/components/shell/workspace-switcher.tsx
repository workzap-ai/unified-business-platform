"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Check, ChevronsUpDown, Layers, Plus } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { Avatar } from "@/components/ui/display";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/overlays";
import { authService } from "@/features/auth/service";
import { useSession } from "@/features/auth/session-provider";
import type { Environment } from "@/features/auth/types";
import { errorMessage } from "@/services/api-client";

export const ENV_TONE: Record<Environment["kind"], string> = {
  production: "bg-success-soft text-success",
  staging: "bg-warning-soft text-warning",
  development: "bg-info-soft text-info",
};

function useWorkspaceOptions() {
  const { status, session } = useSession();
  const tenants = useQuery({
    queryKey: ["workspace-options", "tenants", session?.user.id],
    queryFn: () => authService.tenants(),
    enabled: status === "ready",
    staleTime: 60_000,
  });
  const environments = useQuery({
    queryKey: ["workspace-options", "environments", session?.tenant?.id],
    queryFn: () => authService.environments(),
    enabled: status === "ready" && Boolean(session?.tenant),
    staleTime: 60_000,
  });
  return { tenants, environments };
}

export function WorkspaceSwitcher({ compact = false }: { compact?: boolean }) {
  const { session, switchWorkspace } = useSession();
  const router = useRouter();
  const { tenants } = useWorkspaceOptions();
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState<string | null>(null);
  const name = session?.tenant?.name ?? "Choose workspace";

  async function choose(tenantId: string) {
    if (tenantId === session?.tenant?.id) return setOpen(false);
    setPending(tenantId);
    try {
      await switchWorkspace(tenantId);
      setOpen(false);
      router.push("/");
      toast.success("Workspace switched");
    } catch (error) {
      toast.error(errorMessage(error, "Could not switch workspace."));
    } finally {
      setPending(null);
    }
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cn(
            "flex w-full items-center gap-2.5 rounded-lg p-1.5 text-left transition-colors hover:bg-sidebar-hover",
            compact && "justify-center p-1",
          )}
          aria-label={`Workspace: ${name}. Switch workspace`}
        >
          <Avatar name={name} size="md" square className="ring-1 ring-sidebar-border" />
          {!compact && (
            <>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[13.5px] font-semibold text-sidebar-foreground">
                  {name}
                </span>
                <span className="block truncate text-2xs text-sidebar-muted">
                  {session?.environment?.name ?? "No environment"} ·{" "}
                  {session?.roles[0] ? session.roles[0].replace(/^\w/, (c) => c.toUpperCase()) : "Member"}
                </span>
              </span>
              <ChevronsUpDown className="size-3.5 shrink-0 text-sidebar-muted" aria-hidden="true" />
            </>
          )}
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-72 p-1.5" align="start" side={compact ? "right" : "bottom"}>
        <p className="px-2 pt-1 pb-1.5 text-2xs font-semibold tracking-wide text-muted-foreground uppercase">
          Workspaces
        </p>
        <ul className="space-y-px">
          {(tenants.data ?? []).map((tenant) => (
            <li key={tenant.id}>
              <button
                type="button"
                onClick={() => void choose(tenant.id)}
                disabled={pending !== null}
                className="flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-left hover:bg-surface-muted disabled:opacity-60"
              >
                <Avatar name={tenant.name} size="sm" square />
                <span className="min-w-0 flex-1 truncate text-[13px] font-medium">{tenant.name}</span>
                {tenant.id === session?.tenant?.id && (
                  <Check className="size-4 text-primary" aria-label="Current workspace" />
                )}
              </button>
            </li>
          ))}
          {tenants.isPending && <li className="px-2 py-2 text-xs text-muted-foreground">Loading…</li>}
          {tenants.isError && (
            <li className="px-2 py-2 text-xs text-danger">Workspaces could not be loaded.</li>
          )}
        </ul>
        <div className="mt-1 border-t border-border pt-1">
          <Link
            href="/settings/environments"
            onClick={() => setOpen(false)}
            className="flex items-center gap-2 rounded-md px-2 py-1.5 text-[13px] text-muted-foreground hover:bg-surface-muted hover:text-foreground"
          >
            <Layers className="size-4" aria-hidden="true" /> Manage environments
          </Link>
          <Link
            href="/register"
            onClick={() => setOpen(false)}
            className="flex items-center gap-2 rounded-md px-2 py-1.5 text-[13px] text-muted-foreground hover:bg-surface-muted hover:text-foreground"
          >
            <Plus className="size-4" aria-hidden="true" /> Create a new workspace
          </Link>
        </div>
      </PopoverContent>
    </Popover>
  );
}

export function EnvironmentSwitcher() {
  const { session, switchWorkspace } = useSession();
  const { environments } = useWorkspaceOptions();
  const [open, setOpen] = useState(false);
  const current = environments.data?.find((e) => e.id === session?.environment?.id);
  const kind = (current?.kind ?? session?.environment?.kind ?? "production") as Environment["kind"];

  async function choose(env: Environment) {
    if (!session?.tenant || env.id === session.environment?.id) return setOpen(false);
    try {
      await switchWorkspace(session.tenant.id, env.id);
      setOpen(false);
      toast.success(`Switched to ${env.name}`);
    } catch (error) {
      toast.error(errorMessage(error, "Could not switch environment."));
    }
  }

  if (!session?.environment) return null;
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cn(
            "inline-flex h-7 items-center gap-1.5 rounded-full px-2.5 text-xs font-semibold transition-[filter] hover:brightness-95",
            ENV_TONE[kind],
          )}
          aria-label={`Environment: ${session.environment.name}. Switch environment`}
        >
          <span className="size-1.5 rounded-full bg-current" aria-hidden="true" />
          <span className="max-w-24 truncate">{session.environment.name}</span>
          <ChevronsUpDown className="size-3 opacity-70" aria-hidden="true" />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-64 p-1.5" align="end">
        <p className="px-2 pt-1 pb-1.5 text-2xs font-semibold tracking-wide text-muted-foreground uppercase">
          Environment
        </p>
        {(environments.data ?? [])
          .filter((e) => e.status === "active")
          .map((env) => (
            <button
              key={env.id}
              type="button"
              onClick={() => void choose(env)}
              className="flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-left text-[13px] hover:bg-surface-muted"
            >
              <span className={cn("size-2 rounded-full", ENV_TONE[env.kind].split(" ")[1]?.replace("text-", "bg-"))} />
              <span className="flex-1">
                <span className="block font-medium">{env.name}</span>
                <span className="block text-2xs text-muted-foreground capitalize">{env.kind}</span>
              </span>
              {env.id === session.environment?.id && <Check className="size-4 text-primary" />}
            </button>
          ))}
        <p className="mt-1 border-t border-border px-2 pt-2 pb-1 text-2xs leading-4 text-muted-foreground">
          Data, PI configuration and WhatsApp numbers are separate per environment.
        </p>
      </PopoverContent>
    </Popover>
  );
}
