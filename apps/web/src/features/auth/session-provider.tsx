"use client";

import { createContext, useCallback, useContext, useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@/services/api-client";
import { isDemo } from "@/lib/data-mode";
import { writeDemoState } from "@/demo/workspace";
import { authService } from "./service";
import type { LoginInput, RegisterInput, Session } from "./types";

type SessionStatus = "loading" | "anonymous" | "ready" | "error";

type SessionContextValue = {
  session: Session | null;
  status: SessionStatus;
  /** Display gating only. The API enforces every permission server-side. */
  can: (permission: string) => boolean;
  canAny: (...permissions: string[]) => boolean;
  scopeKey: readonly [string, string, string];
  login: (input: LoginInput) => Promise<Session>;
  register: (input: RegisterInput) => Promise<Session>;
  logout: () => Promise<void>;
  switchWorkspace: (tenantId: string, environmentId?: string) => Promise<void>;
  setDemoRole: (role: string) => Promise<void>;
  retry: () => void;
};

const SessionContext = createContext<SessionContextValue | null>(null);
export const SESSION_KEY = ["session"] as const;

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const client = useQueryClient();
  const query = useQuery({
    queryKey: SESSION_KEY,
    queryFn: () => authService.session(),
    retry: (count, error) =>
      !(error instanceof ApiError && error.status === 401) && count < 1,
    staleTime: 60_000,
    refetchOnWindowFocus: true,
  });

  const anonymous =
    query.error instanceof ApiError && query.error.status === 401;
  const session = anonymous ? null : (query.data ?? null);
  const permissions = useMemo(
    () => new Set(session?.permissions ?? []),
    [session],
  );

  // Workspace data never survives an identity or workspace change: cancel and drop it.
  const purgeWorkspaceData = useCallback(async () => {
    await client.cancelQueries({ queryKey: ["ws"] });
    client.removeQueries({ queryKey: ["ws"] });
  }, [client]);

  const adopt = useCallback(
    async (next: Session) => {
      await purgeWorkspaceData();
      client.setQueryData(SESSION_KEY, next);
    },
    [client, purgeWorkspaceData],
  );

  const value: SessionContextValue = {
    session,
    status: query.isPending
      ? "loading"
      : anonymous
        ? "anonymous"
        : query.isError
          ? "error"
          : "ready",
    can: (permission) => permissions.has(permission),
    canAny: (...list) => list.some((p) => permissions.has(p)),
    scopeKey: [
      "ws",
      session?.tenant?.id ?? "none",
      session?.environment?.id ?? "none",
    ] as const,
    login: async (input) => {
      const next = await authService.login(input);
      await adopt(next);
      return next;
    },
    register: async (input) => {
      const next = await authService.register(input);
      await adopt(next);
      return next;
    },
    logout: async () => {
      try {
        await authService.logout();
      } finally {
        await purgeWorkspaceData();
        client.removeQueries();
        client.setQueryData(SESSION_KEY, undefined);
        await client.invalidateQueries({ queryKey: SESSION_KEY });
      }
    },
    switchWorkspace: async (tenantId, environmentId) => {
      const next = await authService.selectWorkspace(tenantId, environmentId);
      await adopt(next);
      await client.invalidateQueries({ queryKey: ["workspace-options"] });
    },
    setDemoRole: async (role) => {
      if (!isDemo) return;
      writeDemoState({ role });
      await adopt(await authService.session());
    },
    retry: () => void query.refetch(),
  };

  return (
    <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
  );
}

export function useSession() {
  const context = useContext(SessionContext);
  if (!context) throw new Error("SessionProvider is required");
  return context;
}

/** Query-key prefix for workspace-scoped data; changes with tenant/environment. */
export function useScopeKey() {
  return useSession().scopeKey;
}
