"use client";

import {
  QueryClient,
  QueryClientProvider,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryKey,
} from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast, Toaster } from "sonner";

import { ApiError, errorText, get, post, put } from "./api";
import type { SessionView } from "./types";

function makeClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 20_000,
        refetchOnWindowFocus: true,
        retry: (count, error) =>
          !(
            error instanceof ApiError &&
            [400, 401, 403, 404, 409, 422].includes(error.status)
          ) && count < 2,
      },
    },
  });
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = React.useState(makeClient);
  return (
    <QueryClientProvider client={client}>
      {children}
      <Toaster position="top-center" richColors closeButton />
    </QueryClientProvider>
  );
}

export function useSession() {
  return useQuery({
    queryKey: ["session"],
    queryFn: async () => {
      try {
        return await get<SessionView>("/auth/session");
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null;
        throw error;
      }
    },
    staleTime: 60_000,
  });
}

/** Scoped keys: everything below the current business is dropped when it changes. */
export function useBusinessKey(): (key: QueryKey) => QueryKey {
  const { data } = useSession();
  const scope = data?.business
    ? `${data.business.id}:${data.business.environment}`
    : "none";
  return React.useCallback((key: QueryKey) => ["biz", scope, ...key], [scope]);
}

export function useCan() {
  const { data } = useSession();
  return React.useCallback(
    (permission: string) => Boolean(data?.permissions.includes(permission)),
    [data],
  );
}

export function useAction<TArgs, TResult>(
  fn: (args: TArgs) => Promise<TResult>,
  options: {
    success?: string | ((result: TResult) => string);
    invalidate?: QueryKey[];
    onSuccess?: (result: TResult) => void;
    silentError?: boolean;
  } = {},
) {
  const client = useQueryClient();
  const scoped = useBusinessKey();
  return useMutation({
    mutationFn: fn,
    onSuccess: async (result) => {
      await Promise.all(
        (options.invalidate ?? []).map((key) =>
          client.invalidateQueries({ queryKey: scoped(key) }),
        ),
      );
      if (options.success) {
        toast.success(
          typeof options.success === "function"
            ? options.success(result)
            : options.success,
        );
      }
      options.onSuccess?.(result);
    },
    onError: (error) => {
      if (!options.silentError) toast.error(errorText(error));
    },
  });
}

export function useSwitchBusiness() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (args: {
      business_id: string;
      environment?: "production" | "test";
    }) => put<SessionView>("/auth/business", args),
    onSuccess: (session) => {
      client.removeQueries({ queryKey: ["biz"] });
      client.setQueryData(["session"], session);
    },
    onError: (error) => toast.error(errorText(error)),
  });
}

export function useSignOut() {
  const client = useQueryClient();
  const router = useRouter();
  return useMutation({
    mutationFn: () => post("/auth/logout"),
    onSettled: () => {
      client.clear();
      router.replace("/sign-in");
    },
  });
}
