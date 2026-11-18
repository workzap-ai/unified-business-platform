"use client";

import { useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import { api } from "@/lib/api";
import { useBusinessKey, useSession } from "@/lib/session";

/**
 * Live inbox signals (docs/pi-saas/live-events.md). The server only says "something changed"; this
 * refetches through the normal calls, so nothing is trusted from the stream. While the stream is
 * confirmed alive, screens poll slowly; the moment it isn't, polling is exactly what it was before.
 * Off on the server unless PI_EVENTS_ENABLED is set: then the ticket call says so and we stay quiet.
 */

const BASE = "/api/v1/pi-app";
const REFRESH_KEYS = [
  "conversations",
  "history",
  "context",
  "handoffs",
] as const;
const MAX_FAILURES = 5;
const SILENCE_MS = 40_000; // the server pings every 15 s; this long without a word means dead

const LiveContext = React.createContext(false);

/** True while the live stream is confirmed alive (callers slow their polling down). */
export function useLiveConnected(): boolean {
  return React.useContext(LiveContext);
}

export function LiveEventsProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = useSession();
  const signedIn = Boolean(session.data?.business);
  const client = useQueryClient();
  const key = useBusinessKey();
  const [connected, setConnected] = React.useState(false);

  React.useEffect(() => {
    if (!signedIn || typeof EventSource === "undefined") return;
    let stopped = false;
    let source: EventSource | null = null;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let debounce: ReturnType<typeof setTimeout> | undefined;
    let failures = 0;
    let watchdog: ReturnType<typeof setTimeout> | undefined;

    const refresh = () => {
      clearTimeout(debounce);
      debounce = setTimeout(() => {
        for (const k of REFRESH_KEYS)
          void client.invalidateQueries({ queryKey: key([k]) });
      }, 400);
    };
    const close = () => {
      clearTimeout(watchdog);
      source?.close();
      source = null;
      setConnected(false);
    };
    const later = (ms: number) => {
      clearTimeout(retry);
      if (!stopped) retry = setTimeout(open, ms);
    };
    const failed = () => {
      close();
      failures += 1;
      // Back off, and after a few failures in a row give up for ten minutes: polling carries on.
      later(
        failures >= MAX_FAILURES
          ? 600_000
          : Math.min(60_000, 2_000 * 2 ** failures) + Math.random() * 1_000,
      );
      if (failures >= MAX_FAILURES) failures = 0;
    };

    async function open() {
      if (stopped || document.hidden) return;
      try {
        const grant = await api<{ enabled: boolean; ticket?: string }>(
          "POST",
          "/pi/events/ticket",
        );
        if (stopped) return;
        if (!grant.enabled || !grant.ticket) {
          later(300_000); // off on the server: look again in five minutes
          return;
        }
        const url = `${BASE}/pi/events/stream?ticket=${encodeURIComponent(grant.ticket)}`;
        source = new EventSource(url);
        const alive = () => {
          clearTimeout(watchdog);
          watchdog = setTimeout(failed, SILENCE_MS);
        };
        // "live" says the server's worker is publishing: a stream that is open but has nobody
        // publishing must not slow the polling down.
        const live = (event: Event) => {
          try {
            return Boolean(
              JSON.parse((event as MessageEvent<string>).data)?.live,
            );
          } catch {
            return false;
          }
        };
        source.addEventListener("ready", (event) => {
          failures = 0;
          alive();
          setConnected(live(event));
          refresh(); // catch up on anything that happened while we were not listening
        });
        source.addEventListener("ping", (event) => {
          alive();
          setConnected(live(event));
        });
        source.addEventListener("change", () => {
          alive();
          refresh();
        });
        source.addEventListener("busy", failed);
        // The server ends each stream after about a minute; the browser must not reconnect with
        // the old ticket, so close and ask for a new one.
        source.onerror = () => {
          if (source?.readyState === EventSource.CONNECTING) {
            close();
            later(500);
          } else {
            failed();
          }
        };
      } catch {
        failed();
      }
    }

    const onVisibility = () => {
      if (document.hidden) {
        clearTimeout(retry);
        close();
      } else if (!source) {
        later(300);
      }
    };
    document.addEventListener("visibilitychange", onVisibility);
    void open();
    return () => {
      stopped = true;
      clearTimeout(retry);
      clearTimeout(debounce);
      document.removeEventListener("visibilitychange", onVisibility);
      close();
    };
  }, [signedIn, client, key]);

  return (
    <LiveContext.Provider value={connected}>{children}</LiveContext.Provider>
  );
}
