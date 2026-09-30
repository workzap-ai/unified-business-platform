const relative = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

export function timeAgo(value: string | null | undefined): string {
  if (!value) return "";
  const seconds = Math.round((new Date(value).getTime() - Date.now()) / 1000);
  const abs = Math.abs(seconds);
  if (abs < 45) return "just now";
  if (abs < 3600) return relative.format(Math.round(seconds / 60), "minute");
  if (abs < 86400) return relative.format(Math.round(seconds / 3600), "hour");
  if (abs < 86400 * 7)
    return relative.format(Math.round(seconds / 86400), "day");
  return new Date(value).toLocaleDateString("en", {
    day: "numeric",
    month: "short",
  });
}

export function dateTime(value: string | null | undefined): string {
  if (!value) return "";
  return new Date(value).toLocaleString("en", {
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function date(value: string | null | undefined): string {
  if (!value) return "";
  return new Date(value).toLocaleDateString("en", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function money(
  amount: string | null | undefined,
  currency: string,
): string {
  if (amount === null || amount === undefined) return "";
  // Decimal strings from the API; Intl only formats, it never does arithmetic here.
  const value = Number(amount);
  try {
    return new Intl.NumberFormat("en", { style: "currency", currency }).format(
      value,
    );
  } catch {
    return `${amount} ${currency}`;
  }
}

export function count(value: string | number | null | undefined): string {
  const number = typeof value === "string" ? Number(value) : (value ?? 0);
  return new Intl.NumberFormat("en", {
    notation: number >= 100000 ? "compact" : "standard",
  }).format(number);
}

export const STATE_LABEL: Record<
  string,
  {
    label: string;
    tone: "neutral" | "accent" | "success" | "warning" | "danger" | "info";
  }
> = {
  draft: { label: "Setting up", tone: "neutral" },
  awaiting_connection: { label: "Connect WhatsApp", tone: "info" },
  awaiting_approval: { label: "Waiting for WhatsApp", tone: "info" },
  ready: { label: "Ready to launch", tone: "accent" },
  active: { label: "Active", tone: "success" },
  paused: { label: "Paused", tone: "warning" },
  action_required: { label: "Needs attention", tone: "danger" },
};

export const REASON_LABEL: Record<string, string> = {
  TRIAL_ENDED: "Your free trial has ended. Choose a plan to keep Pi replying.",
  PAYMENT_REQUIRED:
    "Your payment didn't go through. Update your payment details.",
  PAST_DUE_GRACE:
    "Your last payment failed. Pi keeps working during a short grace period.",
  SUBSCRIPTION_CANCELED: "Your plan has ended.",
  SUBSCRIPTION_SUSPENDED:
    "Your plan is suspended. Contact us to reactivate it.",
  USAGE_LIMIT_REACHED:
    "You've used this month's allowance. Pi will hand new messages to your team.",
  SPEND_LIMIT_REACHED:
    "Your spend limit was reached. Pi will hand new messages to your team.",
  ACCOUNT_SUSPENDED: "This business is suspended. Contact support.",
  PI_PAUSED: "Pi is paused. Your team is handling messages.",
  RENEWAL_PENDING: "We're confirming your renewal.",
  NO_SUBSCRIPTION: "No plan is active.",
};
