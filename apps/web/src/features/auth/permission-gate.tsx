"use client";

import { useSession } from "./session-provider";

/**
 * Hides UI the current member cannot use. Display logic only: the API independently
 * rejects unauthorized requests, so hiding is never the security boundary.
 */
export function PermissionGate({
  permission,
  any,
  children,
  fallback = null,
}: {
  permission?: string;
  any?: string[];
  children: React.ReactNode;
  fallback?: React.ReactNode;
}) {
  const { can, canAny } = useSession();
  const allowed =
    (permission ? can(permission) : true) && (any ? canAny(...any) : true);
  return allowed ? children : fallback;
}
