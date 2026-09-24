"use client";

import { useCallback, useSyncExternalStore } from "react";

/**
 * Per-browser preference (column visibility, saved views, sidebar collapse). Reads
 * through useSyncExternalStore, so the server render uses `initial` and the client
 * picks up the stored value without an effect. Storage failures fall back to `initial`.
 */
const listeners = new Set<() => void>();

function subscribe(notify: () => void) {
  listeners.add(notify);
  window.addEventListener("storage", notify);
  return () => {
    listeners.delete(notify);
    window.removeEventListener("storage", notify);
  };
}

function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function useLocalStorageState<T>(key: string, initial: T) {
  const raw = useSyncExternalStore(
    subscribe,
    () => read(key),
    () => null,
  );
  let value = initial;
  if (raw !== null) {
    try {
      value = JSON.parse(raw) as T;
    } catch {
      value = initial;
    }
  }
  const setValue = useCallback(
    (next: T | ((current: T) => T)) => {
      const current = (() => {
        const stored = read(key);
        if (stored === null) return initial;
        try {
          return JSON.parse(stored) as T;
        } catch {
          return initial;
        }
      })();
      const resolved =
        typeof next === "function" ? (next as (c: T) => T)(current) : next;
      try {
        window.localStorage.setItem(key, JSON.stringify(resolved));
      } catch {
        /* storage unavailable: the change lasts until reload */
      }
      listeners.forEach((notify) => notify());
    },
    // initial is a stable default per call site
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [key],
  );
  return [value, setValue] as const;
}
