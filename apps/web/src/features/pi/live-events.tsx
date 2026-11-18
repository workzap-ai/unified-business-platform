"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/display";
import { useSession } from "@/features/auth/session-provider";
import { API_BASE } from "@/services/api-client";
import { piSpeedService } from "./speed-service";

/**
 * Live inbox signals (docs/pi-saas/live-events.md). The server only says "something changed"; this
 * refetches through the normal calls, so nothing is trusted from the stream. While the stream is
 * confirmed alive and a worker is publishing, screens poll slowly; the moment that stops being
 * true, polling is exactly what it was before. Off on the server unless PI_EVENTS_ENABLED is set.
 */

const REFRESH_PREFIXES = ["conversations", "messages", "context", "handoffs"];
const MAX_FAILURES = 5;
const SILENCE_MS = 40_000; // the server pings every 15 s; this long without a word means dead

const LiveContext = createContext(false);

/** True while the live stream is confirmed alive (callers slow their polling down). */
export function useLiveConnected(): boolean {
  return useContext(LiveContext);
}

/** A small "Live" mark: shown only while the live stream is confirmed alive. */
export function LiveDot() {
  return useLiveConnected() ? (
    <Badge tone="success" title="Live: new messages appear as they arrive">
      <span className="size-1.5 rounded-full bg-success" aria-hidden="true" />
      Live
    </Badge>
  ) : null;
}

export function LiveEventsProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const { status, scopeKey } = useSession();
  const client = useQueryClient();
  const [connected, setConnected] = useState(false);
  const scope = scopeKey.join("|");

  useEffect(() => {
    if (status !== "ready" || typeof EventSource === "undefined") return;
    let stopped = false;
    let source: EventSource | null = null;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let debounce: ReturnType<typeof setTimeout> | undefined;
    let watchdog: ReturnType<typeof setTimeout> | undefined;
    let failures = 0;
    let heardAt: number | null = null;
    let heardLag = 0;
    let lastReport = 0;

    const refresh = (lagMs?: number) => {
      if (lagMs !== undefined && heardAt === null) {
        heardAt = performance.now();
        heardLag = lagMs;
      }
      clearTimeout(debounce);
      debounce = setTimeout(() => {
        const started = heardAt;
        const lag = heardLag;
        heardAt = null;
        void Promise.all(
          REFRESH_PREFIXES.map((p) =>
            client.invalidateQueries({ queryKey: [...scopeKey, "pi", p] }),
          ),
        ).then(() => {
          const now = Date.now();
          if (started === null || now - lastReport < 10_000) return;
          lastReport = now; // at most one sample every ten seconds
          void piSpeedService
            .timing(lag, performance.now() - started)
            .catch(() => undefined);
        });
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
    const alive = () => {
      clearTimeout(watchdog);
      watchdog = setTimeout(failed, SILENCE_MS);
    };
    // "live" says the server's worker is publishing: a stream that is open but has nobody
    // publishing must not slow the polling down.
    const liveBit = (event: Event) => {
      try {
        return Boolean(JSON.parse((event as MessageEvent<string>).data)?.live);
      } catch {
        return false;
      }
    };

    async function open() {
      if (stopped || document.hidden) return;
      try {
        const grant = await piSpeedService.ticket();
        if (stopped) return;
        if (!grant.enabled || !grant.ticket) {
          later(300_000); // off on the server: look again in five minutes
          return;
        }
        source = new EventSource(
          `${API_BASE}/pi/events/stream?ticket=${encodeURIComponent(grant.ticket)}`,
        );
        source.addEventListener("ready", (event) => {
          failures = 0;
          alive();
          setConnected(liveBit(event));
          refresh(); // catch up on anything that happened while we were not listening
        });
        source.addEventListener("ping", (event) => {
          alive();
          setConnected(liveBit(event));
        });
        source.addEventListener("change", (event) => {
          alive();
          let lag: number | undefined;
          try {
            const sent = JSON.parse((event as MessageEvent<string>).data);
            if (typeof sent?.lag_ms === "number") lag = sent.lag_ms;
          } catch {
            /* a change with no lag still refreshes */
          }
          refresh(lag);
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
    // scopeKey is read through `scope` so a workspace switch reconnects
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, scope, client]);

  return (
    <LiveContext.Provider value={connected}>{children}</LiveContext.Provider>
  );
}
