import { Badge } from "@/components/ui/display";
import { humanize } from "@/lib/format";

type Tone =
  | "neutral"
  | "primary"
  | "success"
  | "warning"
  | "danger"
  | "info"
  | "pi"
  | "outline";

/** One vocabulary of status tones across every module so states read the same everywhere. */
const TONES: Record<string, Tone> = {
  active: "success",
  archived: "neutral",
  inactive: "neutral",
  draft: "neutral",
  pending: "warning",
  pending_approval: "warning",
  approved: "info",
  sent: "info",
  accepted: "success",
  rejected: "danger",
  submitted: "primary",
  revoked: "neutral",
  expired: "neutral",
  cancelled: "neutral",
  confirmed: "info",
  processing: "warning",
  shipped: "primary",
  delivered: "success",
  issued: "info",
  partially_paid: "warning",
  paid: "success",
  void: "neutral",
  overdue: "danger",
  recorded: "neutral",
  new: "info",
  qualified: "primary",
  proposal: "warning",
  won: "success",
  lost: "neutral",
  open: "warning",
  assigned: "info",
  in_progress: "primary",
  resolved: "success",
  closed: "neutral",
  ai: "pi",
  human: "info",
  ready: "success",
  failed: "danger",
  queued: "neutral",
  received: "neutral",
  processed: "success",
  ignored: "neutral",
  duplicate: "neutral",
  read: "success",
  error: "danger",
  disabled: "neutral",
  on_leave: "warning",
  terminated: "neutral",
  installed: "success",
  suspended: "warning",
  healthy: "success",
  low: "warning",
  out: "danger",
  degraded: "warning",
  down: "danger",
  success: "success",
  denied: "danger",
  failure: "danger",
  running: "info",
  completed: "success",
  handoff: "warning",
  skipped: "neutral",
  invalid: "danger",
  confirmation_required: "warning",
  production: "success",
  staging: "warning",
  development: "info",
};

const LABELS: Record<string, string> = {
  ai: "AI",
  in_progress: "In progress",
  pending_approval: "Needs approval",
  partially_paid: "Partially paid",
  on_leave: "On leave",
  out: "Out of stock",
  low: "Low stock",
  confirmation_required: "Needs confirmation",
};

export function statusLabel(status: string) {
  return LABELS[status] ?? humanize(status);
}

export function StatusBadge({
  status,
  label,
  className,
  dot = true,
}: {
  status: string;
  label?: string;
  className?: string;
  dot?: boolean;
}) {
  return (
    <Badge tone={TONES[status] ?? "neutral"} dot={dot} className={className}>
      {label ?? statusLabel(status)}
    </Badge>
  );
}
