"use client";

import { useQuery } from "@tanstack/react-query";
import {
  CalendarClock,
  CreditCard,
  HelpCircle,
  LifeBuoy,
  MessageSquareWarning,
  Package,
  Sparkles,
} from "lucide-react";

import { ApiError } from "@/lib/api";
import {
  customerGet,
  type CustomerIssue,
  type CustomerMe,
  type CustomerPrefs,
  type Stage,
} from "@/lib/customer-api";
import { cn } from "@/lib/cn";

export const ME = ["pi-customer", "me"] as const;
export const LIST = ["pi-customer", "conversations"] as const;

export function useMe() {
  return useQuery({
    queryKey: ME,
    queryFn: async () => {
      try {
        return await customerGet<CustomerMe>("/me");
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null;
        throw error;
      }
    },
    retry: false,
  });
}

/** "just now", "5m ago", "2h ago", "Yesterday", "3 Oct". */
export function ago(iso: string) {
  const date = new Date(iso);
  const seconds = (Date.now() - date.getTime()) / 1000;
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  const yesterday = new Date();
  yesterday.setDate(yesterday.getDate() - 1);
  if (new Date().toDateString() === date.toDateString())
    return `${Math.floor(seconds / 3600)}h ago`;
  if (yesterday.toDateString() === date.toDateString()) return "Yesterday";
  return date.toLocaleDateString([], { day: "numeric", month: "short" });
}

export function clock(iso: string) {
  return new Date(iso).toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit",
  });
}

export function dayLabel(iso: string) {
  const date = new Date(iso);
  const yesterday = new Date();
  yesterday.setDate(yesterday.getDate() - 1);
  if (new Date().toDateString() === date.toDateString()) return "Today";
  if (yesterday.toDateString() === date.toDateString()) return "Yesterday";
  return date.toLocaleDateString([], {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
}

const AVATAR_TONES = [
  "bg-accent-soft text-accent-soft-foreground",
  "bg-info-soft text-info",
  "bg-success-soft text-success",
  "bg-warning-soft text-warning",
  "bg-danger-soft text-danger",
];

export function Avatar({
  name,
  size = "md",
}: {
  name: string;
  size?: "md" | "lg";
}) {
  const hash = [...name].reduce(
    (n, ch) => (n * 31 + ch.charCodeAt(0)) >>> 0,
    7,
  );
  const initials =
    name
      .trim()
      .split(/\s+/)
      .slice(0, 2)
      .map((w) => w.charAt(0).toUpperCase())
      .join("") || "?";
  return (
    <span
      aria-hidden
      className={cn(
        "flex shrink-0 items-center justify-center rounded-2xl font-semibold",
        size === "lg" ? "size-14 text-lg" : "size-11 text-sm",
        AVATAR_TONES[hash % AVATAR_TONES.length],
      )}
    >
      {initials}
    </span>
  );
}

export const CATEGORY: Record<
  CustomerIssue["category"],
  { label: string; icon: typeof HelpCircle }
> = {
  inquiry: { label: "Question", icon: HelpCircle },
  order: { label: "Order", icon: Package },
  booking: { label: "Booking", icon: CalendarClock },
  payment: { label: "Payment", icon: CreditCard },
  complaint: { label: "Complaint", icon: MessageSquareWarning },
  support: { label: "Support", icon: LifeBuoy },
  other: { label: "Request", icon: Sparkles },
};

export const PREFS = ["pi-customer", "prefs"] as const;

export function usePrefs() {
  return useQuery({
    queryKey: PREFS,
    queryFn: () => customerGet<CustomerPrefs>("/prefs"),
    staleTime: 60_000,
  });
}

/** English, or Roman Urdu when the customer chose Urdu. */
export function useLang(): "en" | "ur" {
  const prefs = usePrefs();
  const language = prefs.data?.language;
  return language === "roman_ur" || language === "ur" ? "ur" : "en";
}

type Tone = "neutral" | "accent" | "success" | "warning" | "info";

/** One status vocabulary, the same on the dashboard, WhatsApp and the team's tools. */
export const STAGE: Record<
  Stage,
  { en: string; ur: string; tone: Tone; dot: string; bar: string }
> = {
  noted: {
    en: "Noted",
    ur: "Note ho gaya",
    tone: "accent",
    // "Noted" is a hollow ring so it never relies on colour alone.
    dot: "border-2 border-accent bg-transparent",
    bar: "border-l-accent",
  },
  need_answer: {
    en: "Need your answer",
    ur: "Aap ka jawab chahiye",
    tone: "warning",
    dot: "bg-warning",
    bar: "border-l-warning",
  },
  on_it: {
    en: "We're on it",
    ur: "Team kaam kar rahi hai",
    tone: "info",
    dot: "bg-info",
    bar: "border-l-info",
  },
  solution_ready: {
    en: "Solution ready",
    ur: "Hal tayyar hai",
    tone: "success",
    dot: "bg-success",
    bar: "border-l-success",
  },
  building: {
    en: "Building",
    ur: "Ban raha hai",
    tone: "info",
    dot: "bg-info",
    bar: "border-l-info",
  },
  live: {
    en: "Live",
    ur: "Mukammal",
    tone: "success",
    dot: "bg-success",
    bar: "border-l-success",
  },
  paused: {
    en: "Paused",
    ur: "Ruka hua",
    tone: "neutral",
    dot: "bg-muted-foreground/40",
    bar: "border-l-border-strong",
  },
  closed: {
    en: "Closed",
    ur: "Band",
    tone: "neutral",
    dot: "bg-muted-foreground/40",
    bar: "border-l-border-strong",
  },
};

export type Turn = "you" | "other" | "us" | "done";

/** Whose turn it is for one request. */
export function turnOf(issue: CustomerIssue): Turn {
  if (["live", "closed", "paused"].includes(issue.stage)) return "done";
  if (issue.waiting_on_other_until) return "other";
  return issue.ball_with === "client" ? "you" : "us";
}

export const TURN: Record<
  Turn,
  { en: string; ur: string; tone: Tone; dot: string }
> = {
  you: {
    en: "Waiting on you",
    ur: "Aap ki baari",
    tone: "warning",
    dot: "bg-warning",
  },
  other: {
    en: "Waiting on someone else",
    ur: "Kisi aur ka intezar",
    tone: "neutral",
    dot: "bg-muted-foreground/50",
  },
  us: { en: "Waiting on us", ur: "Hamari baari", tone: "info", dot: "bg-info" },
  done: { en: "Done", ur: "Ho gaya", tone: "success", dot: "bg-success" },
};

/** "Thu 8 Oct". */
export function shortDay(iso: string) {
  return new Date(iso).toLocaleDateString([], {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
}

/** Journey progress across requests: steps done out of 7, averaged. */
export function journeyPercent(issues: CustomerIssue[]) {
  const counted = issues.filter((i) => i.journey_steps !== null);
  if (!counted.length) return null;
  const total = counted.reduce((n, i) => n + (i.journey_steps ?? 0), 0);
  return Math.round((total / (counted.length * 7)) * 100);
}

/** The next step as who + what + when. */
export function nextStepLine(issue: CustomerIssue, lang: "en" | "ur") {
  if (issue.waiting_on_other_until)
    return lang === "ur"
      ? `Aap ne bataya aap kisi ka intezar kar rahe hain. Reminders ${shortDay(issue.waiting_on_other_until)} tak band.`
      : `You're waiting on someone else. No reminders until ${shortDay(issue.waiting_on_other_until)}.`;
  if (issue.ball_with === "client" && issue.open_question)
    return issue.open_question;
  if (issue.ball_with === "team" && issue.next_update_by) {
    const when = shortDay(issue.next_update_by);
    const step = issue.next_step.replace(/^(team|pi|you)\s*:\s*/i, "");
    return lang === "ur"
      ? `${step ? `${step}. ` : ""}Team ${when} tak update degi.`
      : `${step ? `${step}. ` : ""}Update from the team by ${when}.`;
  }
  return issue.next_step;
}

/** WhatsApp formatting (*bold*, _italic_, ~strike~) as the customer saw it. */
export function Formatted({ text }: { text: string }) {
  const parts = text.split(
    /((?<!\w)(?:\*[^*\n]+\*|_[^_\n]+_|~[^~\n]+~)(?!\w))/g,
  );
  return (
    <p className="whitespace-pre-wrap break-words">
      {parts.map((part, i) => {
        const inner = part.slice(1, -1);
        if (part.length > 2 && part.startsWith("*") && part.endsWith("*"))
          return <strong key={i}>{inner}</strong>;
        if (part.length > 2 && part.startsWith("_") && part.endsWith("_"))
          return <em key={i}>{inner}</em>;
        if (part.length > 2 && part.startsWith("~") && part.endsWith("~"))
          return <s key={i}>{inner}</s>;
        return part;
      })}
    </p>
  );
}
