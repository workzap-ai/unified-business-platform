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

export const STATUS: Record<
  CustomerIssue["status"],
  {
    label: string;
    tone: "warning" | "info" | "success";
    bar: string;
    dot: string;
  }
> = {
  open: {
    label: "In progress",
    tone: "warning",
    bar: "border-l-warning",
    dot: "bg-warning",
  },
  with_team: {
    label: "With the team",
    tone: "info",
    bar: "border-l-info",
    dot: "bg-info",
  },
  resolved: {
    label: "Sorted",
    tone: "success",
    bar: "border-l-success",
    dot: "bg-success",
  },
};

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
