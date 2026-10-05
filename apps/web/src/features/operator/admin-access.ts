"use client";

import { useQuery } from "@tanstack/react-query";
import { useSession } from "@/features/auth/session-provider";
import { isDemo } from "@/lib/data-mode";
import { operatorService, type OperatorMe } from "./service";

/**
 * The signed-in person's admin console access (super admin, admin or operator), or null.
 * Platform-wide, so the key is per user rather than per workspace. The API re-checks
 * every request; this only decides whether to show the way in.
 */
export function useAdminAccess(): OperatorMe | null {
  const { session, status } = useSession();
  const userId = session?.user.id;
  const query = useQuery({
    queryKey: ["admin-access", userId],
    queryFn: operatorService.me,
    enabled: status === "ready" && Boolean(userId) && !isDemo,
    retry: false,
    staleTime: 5 * 60_000,
  });
  return query.data ?? null;
}
