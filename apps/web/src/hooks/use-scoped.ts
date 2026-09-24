"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryOptions,
} from "@tanstack/react-query";
import { toast } from "sonner";
import { useSession } from "@/features/auth/session-provider";
import { errorMessage } from "@/services/api-client";

/**
 * Workspace-scoped query: the key is prefixed with tenant + environment so switching
 * workspaces can never show another workspace's cached data.
 */
export function useScopedQuery<T>(
  key: readonly unknown[],
  fn: () => Promise<T>,
  options: Omit<UseQueryOptions<T>, "queryKey" | "queryFn"> = {},
) {
  const { scopeKey, status } = useSession();
  return useQuery<T>({
    queryKey: [...scopeKey, ...key],
    queryFn: fn,
    ...options,
    enabled: status === "ready" && (options.enabled ?? true),
  });
}

/** Mutation that invalidates workspace-scoped keys and reports safe, consistent toasts. */
export function useScopedMutation<TInput, TResult>(
  fn: (input: TInput) => Promise<TResult>,
  {
    invalidate = [],
    success,
    error: errorFallback = "That didn't work. Please try again.",
    onSuccess,
    toastErrors = true,
    invalidateGlobal = [],
  }: {
    invalidate?: readonly unknown[][];
    /** Unscoped keys to refresh too (e.g. the workspace switcher's options). */
    invalidateGlobal?: readonly unknown[][];
    success?: string | ((result: TResult) => string);
    error?: string;
    onSuccess?: (result: TResult, input: TInput) => void;
    /** Set false when the caller shows the error inline (avoids a duplicate toast). */
    toastErrors?: boolean;
  } = {},
) {
  const client = useQueryClient();
  const { scopeKey } = useSession();
  return useMutation<TResult, unknown, TInput>({
    mutationFn: fn,
    onSuccess: async (result, input) => {
      await Promise.all([
        ...invalidate.map((k) =>
          client.invalidateQueries({ queryKey: [...scopeKey, ...k] }),
        ),
        ...invalidateGlobal.map((k) =>
          client.invalidateQueries({ queryKey: [...k] }),
        ),
      ]);
      if (success)
        toast.success(
          typeof success === "function" ? success(result) : success,
        );
      onSuccess?.(result, input);
    },
    onError: (e) => {
      if (toastErrors) toast.error(errorMessage(e, errorFallback));
    },
  });
}
