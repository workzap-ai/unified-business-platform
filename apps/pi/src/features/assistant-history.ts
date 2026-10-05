"use client";

import * as React from "react";

/*
 * pi Assistant chat history, kept in this browser per business and per signed-in
 * person (never shared between team members on one device; cleared on sign-out).
 * Storage can be missing or full (private windows, blocked site data), so every read
 * and write is guarded and the chat still works without it.
 */

export type Card = {
  title: string;
  href: string | null;
  metrics: Record<string, string | number | null>;
  rows: Record<string, unknown>[];
  bars: { label: string; value: number }[];
  note: string;
};
export type Guide = {
  id: string;
  title: string;
  body: string;
  page: string | null;
};
export type Reply = {
  message: string;
  mode: "ai" | "tools";
  cards: Card[];
  guides: Guide[];
  notice?: string;
  follow_ups?: string[];
};
export type Step = { tool: string; label: string; done: boolean; ok: boolean };
export type Turn = {
  id: string;
  question?: string;
  reply?: Reply;
  error?: string;
  stopped?: boolean;
  steps?: Step[];
};
export type Thread = {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  turns: Turn[];
};

const PREFIX = "pi-assistant:v1:";
const MAX_THREADS = 30;
const MAX_TURNS = 60;
const MAX_BYTES = 1_500_000;

export const newId = () =>
  `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;

function load(key: string): Thread[] {
  try {
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

export function titleFor(question: string) {
  const line = question.replace(/\s+/g, " ").trim();
  return line.length > 60 ? `${line.slice(0, 57)}…` : line;
}

export function useThreads(businessId?: string, userId?: string) {
  const key = businessId && userId ? `${PREFIX}${businessId}:${userId}` : "";
  // Load when the business or person changes (adjusting state during render, not in
  // an effect, so the first paint already shows the right chats).
  const [store, setStore] = React.useState<{ key: string; threads: Thread[] }>({
    key: "",
    threads: [],
  });
  let threads = store.threads;
  if (store.key !== key) {
    threads = key ? load(key) : [];
    setStore({ key, threads });
  }
  const update = React.useCallback(
    (change: (threads: Thread[]) => Thread[]) => {
      setStore((current) => {
        const next = change(current.threads);
        if (current.key) save(current.key, next);
        return { key: current.key, threads: next };
      });
    },
    [],
  );
  return { threads, update };
}

/** What the model sees of an earlier answer: the words plus a short note of the cards. */
export function replyAsText(reply: Reply): string {
  const shown = reply.cards
    .map((c) => {
      const metrics = Object.entries(c.metrics)
        .slice(0, 6)
        .map(([k, v]) => `${k}: ${v ?? "-"}`)
        .join(", ");
      return metrics ? `${c.title} (${metrics})` : c.title;
    })
    .join("; ");
  return shown
    ? `${reply.message}\n\n[Cards shown: ${shown}]`.slice(0, 2400)
    : reply.message.slice(0, 2400);
}

export type HistoryTurn = { role: "user" | "assistant"; content: string };

export function historyFor(turns: Turn[]): HistoryTurn[] {
  return turns
    .flatMap<HistoryTurn>((t) =>
      t.question
        ? [{ role: "user" as const, content: t.question }]
        : t.reply
          ? [{ role: "assistant" as const, content: replyAsText(t.reply) }]
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
