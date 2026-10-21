"use client";

import { useCallback, useState } from "react";
import type { Reply } from "./service";

/*
 * Agent Beta chat history, kept in this browser per workspace, environment, person and
 * permission set. When a person's permissions change, chats saved under the old set are
 * deleted (they may show data the person can no longer see), and sign-out deletes them
 * all. Storage can be missing or full, so every read and write is guarded.
 */

export type Step = { tool: string; label: string; done: boolean; ok: boolean };
export type Turn = {
  id: string;
  user?: string;
  reply?: Reply;
  error?: string;
  stopped?: boolean;
  steps?: Step[];
  notes?: string[];
};
export type Thread = {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  turns: Turn[];
};

export const HISTORY_PREFIX = "owner-agent:";
const VERSION = "v1:";
const MAX_THREADS = 40;
const MAX_TURNS = 80;
const MAX_BYTES = 2_500_000;

export const newId = () =>
  `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;

function hash(text: string) {
  let h = 5381;
  for (let i = 0; i < text.length; i++) h = (h * 33) ^ text.charCodeAt(i);
  return (h >>> 0).toString(36);
}

/** Storage key for this workspace, person and permission set ("" = don't store). */
export function historyKey(
  tenant?: string,
  environment?: string,
  user?: string,
  permissions: string[] = [],
) {
  if (!tenant || !environment || !user) return "";
  return `${HISTORY_PREFIX}${VERSION}${tenant}:${environment}:${user}:${hash(
    permissions.toSorted().join(","),
  )}`;
}

function load(key: string): Thread[] {
  try {
    // Chats saved under this person's earlier permissions go.
    const owner = key.slice(0, key.lastIndexOf(":") + 1);
    for (let i = window.localStorage.length - 1; i >= 0; i--) {
      const k = window.localStorage.key(i);
      if (k && k !== key && k.startsWith(owner))
        window.localStorage.removeItem(k);
    }
    const raw = window.localStorage.getItem(key);
    const data = raw ? (JSON.parse(raw) as { threads?: Thread[] }) : null;
    return Array.isArray(data?.threads) ? data.threads : [];
  } catch {
    return [];
  }
}

function save(key: string, threads: Thread[]) {
  let list = threads
    .filter((t) => t.turns.length)
    .sort((a, b) => b.updatedAt - a.updatedAt)
    .slice(0, MAX_THREADS)
    .map((t) => ({ ...t, turns: t.turns.slice(-MAX_TURNS) }));
  try {
    let raw = JSON.stringify({ threads: list });
    while (raw.length > MAX_BYTES && list.length > 1) {
      list = list.slice(0, -1); // drop the oldest chat until it fits
      raw = JSON.stringify({ threads: list });
    }
    window.localStorage.setItem(key, raw);
  } catch {
    // Storage blocked or full: history just isn't kept on this device.
  }
}

/** Delete every saved Agent Beta chat in this browser (sign-out). */
export function clearAgentHistory() {
  try {
    for (let i = window.localStorage.length - 1; i >= 0; i--) {
      const k = window.localStorage.key(i);
      if (k?.startsWith(HISTORY_PREFIX)) window.localStorage.removeItem(k);
    }
  } catch {
    // nothing stored
  }
}

export function useThreads(key: string) {
  // Load when the key changes (adjusting state during render, so the first paint
  // already shows the right chats).
  const [store, setStore] = useState<{ key: string; threads: Thread[] }>({
    key: "",
    threads: [],
  });
  let threads = store.threads;
  if (store.key !== key) {
    threads = key ? load(key) : [];
    setStore({ key, threads });
  }
  const update = useCallback((change: (threads: Thread[]) => Thread[]) => {
    setStore((current) => {
      const next = change(current.threads);
      if (current.key) save(current.key, next);
      return { key: current.key, threads: next };
    });
  }, []);
  return { threads, update };
}

export function titleFor(text: string) {
  const line = text.replace(/\s+/g, " ").trim();
  return line.length > 70 ? `${line.slice(0, 67)}…` : line;
}

/** What the model sees of an earlier answer: the words plus a note of what was shown. */
function replyAsText(reply: Reply): string {
  const shown = [
    ...reply.analytics.map(
      (a) =>
        `${a.topic} analytics (${a.kpis
          .slice(0, 5)
          .map((k) => `${k.label}: ${k.value}`)
          .join(", ")})`,
    ),
    ...(reply.team
      ? [`decision brief: ${reply.team.brief.recommendation}`]
      : []),
    ...reply.signals.slice(0, 5).map((s) => `${s.title} (${s.count})`),
    ...reply.results.map((r) => `${r.title ?? r.area}: ${r.total} records`),
    ...reply.proposals.map((p) => `draft ${p.operation} (${p.status})`),
  ].join("; ");
  return (
    shown ? `${reply.message}\n\n[Shown: ${shown}]` : reply.message
  ).slice(0, 3000);
}

export type HistoryTurn = { role: "user" | "assistant"; content: string };

export function historyFor(turns: Turn[]): HistoryTurn[] {
  return turns
    .flatMap<HistoryTurn>((t) =>
      t.user
        ? [{ role: "user", content: t.user }]
        : t.reply
          ? [{ role: "assistant", content: replyAsText(t.reply) }]
          : [],
    )
    .filter((t) => t.content.trim())
    .slice(-16);
}

export function when(time: number) {
  const diff = (time - Date.now()) / 1000;
  const fmt = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  const abs = Math.abs(diff);
  if (abs < 60) return fmt.format(Math.round(diff), "second");
  if (abs < 3600) return fmt.format(Math.round(diff / 60), "minute");
  if (abs < 86400) return fmt.format(Math.round(diff / 3600), "hour");
  if (abs < 86400 * 7) return fmt.format(Math.round(diff / 86400), "day");
  return new Date(time).toLocaleDateString(undefined, {
    day: "numeric",
    month: "long",
  });
}
