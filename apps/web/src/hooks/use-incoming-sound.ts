"use client";

import { useEffect, useRef } from "react";
import { useLocalStorageState } from "@/hooks/use-local-storage";

/**
 * Incoming-message tone (a short, soft two-note chime, like a chat app's), synthesised
 * with the Web Audio API: no audio files. Browsers only allow audio after the person has
 * interacted with the page, so the AudioContext is created on the first pointer/key event.
 * Every step fails silently when audio isn't available.
 */
export const INCOMING_SOUND_KEY = "platform.inbox.sound";

type AudioCtor = typeof AudioContext;
let context: AudioContext | null = null;
let unlockBound = false;
let lastPlayed = 0;

function audioContext(): AudioContext | null {
  try {
    if (!context) {
      const Ctor: AudioCtor | undefined =
        window.AudioContext ??
        (window as unknown as { webkitAudioContext?: AudioCtor })
          .webkitAudioContext;
      if (!Ctor) return null;
      context = new Ctor();
    }
    if (context.state === "suspended") void context.resume().catch(() => {});
    return context;
  } catch {
    return null;
  }
}

/** Create/resume the AudioContext on the first interaction (browsers block it before). */
function bindUnlock() {
  if (unlockBound || typeof window === "undefined") return;
  unlockBound = true;
  const unlock = () => {
    const ctx = audioContext();
    if (ctx?.state === "running") {
      window.removeEventListener("pointerdown", unlock, true);
      window.removeEventListener("keydown", unlock, true);
    }
  };
  window.addEventListener("pointerdown", unlock, true);
  window.addEventListener("keydown", unlock, true);
}

/** The person's choice, default on. Read at play time so every tab honours it. */
export function incomingSoundOn(): boolean {
  try {
    return window.localStorage.getItem(INCOMING_SOUND_KEY) !== "false";
  } catch {
    return true;
  }
}

function note(
  ctx: AudioContext,
  frequency: number,
  start: number,
  length: number,
) {
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = "sine";
  osc.frequency.setValueAtTime(frequency, start);
  gain.gain.setValueAtTime(0.0001, start);
  gain.gain.exponentialRampToValueAtTime(0.07, start + 0.012);
  gain.gain.exponentialRampToValueAtTime(0.0001, start + length);
  osc.connect(gain);
  gain.connect(ctx.destination);
  osc.start(start);
  osc.stop(start + length + 0.02);
}

/** Play the tone once (about 250 ms, low volume). `force` ignores the off switch (preview). */
export function playIncomingTone(force = false) {
  if (typeof window === "undefined") return;
  if (!force && !incomingSoundOn()) return;
  const now = Date.now();
  if (now - lastPlayed < 1_500) return; // one tone per batch
  // A preview runs inside a click, so it may create the context; a message never does.
  const ctx = force ? audioContext() : context;
  if (!ctx) return; // no interaction yet: browsers would block it anyway
  lastPlayed = now;
  if (ctx.state === "running") chime(ctx);
  else if (force)
    void ctx
      .resume()
      .then(() => chime(ctx))
      .catch(() => {});
  else void ctx.resume().catch(() => {});
}

function chime(ctx: AudioContext) {
  try {
    const t = ctx.currentTime + 0.01;
    note(ctx, 987.77, t, 0.11); // B5
    note(ctx, 1318.51, t + 0.115, 0.135); // E6
  } catch {
    /* audio unavailable: stay silent */
  }
}

/** On/off switch for the tone, remembered in this browser (default on). */
export function useIncomingSoundSetting() {
  const [on, setOn] = useLocalStorageState(INCOMING_SOUND_KEY, true);
  useEffect(bindUnlock, []);
  return [on !== false, setOn] as const;
}

export type InboundSnapshot = Map<
  string,
  { unread: number; at: number; customer: boolean }
>;

type InboundRow = {
  id: string;
  unread_count: number;
  last_message_at: string;
  last_sender: string;
};

export function snapshotOf(rows: InboundRow[]): InboundSnapshot {
  return new Map(
    rows.map((r) => [
      r.id,
      {
        unread: r.unread_count,
        at: Date.parse(r.last_message_at) || 0,
        customer: r.last_sender === "customer",
      },
    ]),
  );
}

/** True when a customer wrote since `prev`: unread went up or a newer inbound arrived. */
export function hasNewInbound(prev: InboundSnapshot, next: InboundSnapshot) {
  let newest = 0;
  for (const p of prev.values()) newest = Math.max(newest, p.at);
  for (const [id, n] of next) {
    const p = prev.get(id);
    if (p) {
      if (n.unread > p.unread) return true;
      if (n.customer && n.at > p.at) return true;
    } else if ((n.unread > 0 || n.customer) && n.at > newest) {
      return true;
    }
  }
  return false;
}

/**
 * Plays the tone when `rows` (newest conversations) show a new customer message.
 * The first data is only a baseline; `scope` resets it on workspace switch.
 */
export function useIncomingTone(rows: InboundRow[] | undefined, scope: string) {
  const prev = useRef<{ scope: string; snap: InboundSnapshot } | null>(null);
  useEffect(bindUnlock, []);
  useEffect(() => {
    if (!rows) return;
    const snap = snapshotOf(rows);
    const before = prev.current;
    prev.current = { scope, snap };
    if (before && before.scope === scope && hasNewInbound(before.snap, snap))
      playIncomingTone();
  }, [rows, scope]);
}

const BADGE = /^\(\d+\+?\) /;

/** "(3) Title" in the tab while it's hidden and conversations are unread. */
export function useUnreadTitleBadge(unread: number) {
  useEffect(() => {
    const apply = () => {
      const base = document.title.replace(BADGE, "");
      document.title =
        document.hidden && unread > 0
          ? `(${unread > 99 ? "99+" : unread}) ${base}`
          : base;
    };
    apply();
    document.addEventListener("visibilitychange", apply);
    return () => {
      document.removeEventListener("visibilitychange", apply);
      document.title = document.title.replace(BADGE, "");
    };
  }, [unread]);
}
