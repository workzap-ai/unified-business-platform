"use client";

import { useCallback, useMemo } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

/**
 * List state (search, filters, sort, page, view) kept in the URL so it survives reloads,
 * back/forward and sharing. Values equal to their default are omitted from the URL.
 */
export function useUrlState<T extends Record<string, string>>(defaults: T) {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const serializedDefaults = JSON.stringify(defaults);

  const state = useMemo(() => {
    const base = JSON.parse(serializedDefaults) as T;
    const result = { ...base };
    for (const key of Object.keys(base) as (keyof T)[]) {
      const value = params.get(String(key));
      if (value !== null) result[key] = value as T[keyof T];
    }
    return result;
  }, [params, serializedDefaults]);

  const set = useCallback(
    (patch: Partial<T>, options: { resetPage?: boolean } = { resetPage: true }) => {
      const base = JSON.parse(serializedDefaults) as T;
      const next = new URLSearchParams(params.toString());
      const merged: Record<string, string | undefined> = { ...patch };
      if (options.resetPage !== false && !("page" in patch) && "page" in base) merged.page = base.page;
      for (const [key, value] of Object.entries(merged)) {
        if (value === undefined || value === "" || value === base[key]) next.delete(key);
        else next.set(key, value);
      }
      const qs = next.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [params, pathname, router, serializedDefaults],
  );

  const reset = useCallback(() => router.replace(pathname, { scroll: false }), [pathname, router]);
  return [state, set, reset] as const;
}

export function usePersistentState<T>(key: string, initial: T) {
  const read = (): T => {
    if (typeof window === "undefined") return initial;
    try {
      const raw = window.localStorage.getItem(key);
      return raw ? (JSON.parse(raw) as T) : initial;
    } catch {
      return initial;
    }
  };
  const write = (value: T) => {
    try {
      window.localStorage.setItem(key, JSON.stringify(value));
    } catch {
      /* ignore */
    }
  };
  return { read, write };
}
