"use client";

import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowDownLeft,
  ArrowLeft,
  ArrowUpRight,
  Copy,
  RotateCcw,
  ScrollText,
} from "lucide-react";
import Link from "next/link";
import * as React from "react";

import {
  Badge,
  Button,
  Card,
  CardSection,
  Dialog,
  DialogClose,
  DialogContent,
  DialogTrigger,
  EmptyState,
  ErrorState,
  LoadingBlock,
  Notice,
  PageHeader,
} from "@/components/ui";
import { errorText, get, post } from "@/lib/api";
import { cn } from "@/lib/cn";
import { count, dateTime, timeAgo } from "@/lib/format";
import { useAction, useBusinessKey, useCan } from "@/lib/session";

interface Connection {
  id: string;
  provider: string;
  display_phone_number: string | null;
  display_name: string | null;
  status: string;
  last_inbound_at: string | null;
  last_outbound_at: string | null;
  last_error_code: string | null;
  last_error_at: string | null;
  messages_24h: { inbound: number; outbound: number; failed: number };
}

interface WebhookEvent {
  id: string;
  event_key: string;
  kind: string;
  status: string;
  duplicate_count: number;
  attempts: number;
  error_code: string | null;
  created_at: string;
  processed_at: string | null;
  summary: string;
}

interface EventPage {
  items: WebhookEvent[];
  total: number;
  page: number;
  page_size: number;
}

const PAGE_SIZE = 25;

const ERROR_TEXT: Record<string, string> = {
  RECIPIENT_UNAVAILABLE:
    "The customer can't receive messages right now (not on WhatsApp, or more than 24 hours since they last wrote).",
  SIGNATURE_INVALID:
    "A message arrived that WhatsApp didn't sign, so Pi ignored it.",
  TOKEN_INVALID: "WhatsApp rejected the connection. Reconnect your number.",
  TOKEN_EXPIRED: "The WhatsApp connection expired. Reconnect your number.",
  RATE_LIMITED:
    "WhatsApp is slowing down messages from this number. Pi will retry.",
  MEDIA_TOO_LARGE: "A file was larger than the allowed size.",
  PROCESSING_TIMEOUT: "Handling a message took too long. Try it again.",
  rate_limit: "The AI service was busy.",
  timeout: "The AI service took too long to answer.",
  provider_unavailable: "The AI service was unavailable.",
  all_providers_failed: "No AI service could answer at the time.",
  invalid_response: "The AI service gave an unusable answer.",
};

function friendlyError(code: string | null): string {
  if (!code) return "";
  return (
    ERROR_TEXT[code] ??
    code
      .toLowerCase()
      .replace(/_/g, " ")
      .replace(/^\w/, (c) => c.toUpperCase())
  );
}

const STATUS_META: Record<
  string,
  {
    label: string;
    tone: "neutral" | "accent" | "success" | "warning" | "danger" | "info";
  }
> = {
  received: { label: "Received", tone: "info" },
  queued: { label: "Waiting", tone: "info" },
  processed: { label: "Handled", tone: "success" },
  ignored: { label: "Ignored", tone: "neutral" },
  failed: { label: "Failed", tone: "danger" },
};

const FILTERS: { value: string; label: string }[] = [
  { value: "", label: "All" },
  { value: "failed", label: "Failed" },
  { value: "queued", label: "Waiting" },
  { value: "received", label: "Received" },
  { value: "processed", label: "Handled" },
  { value: "ignored", label: "Ignored" },
];

const KIND_LABEL: Record<string, string> = {
  message: "Message",
  status: "Delivery update",
  unknown: "Other",
};

const REPLAYABLE = new Set(["failed", "received", "queued"]);

function Metric({
  label,
  value,
  icon,
  tone,
}: {
  label: string;
  value: number;
  icon: React.ReactNode;
  tone?: "danger";
}) {
  return (
    <div
      className={cn(
        "flex min-w-0 items-center gap-3 rounded-xl border border-border bg-surface-muted p-3.5",
        tone === "danger" && value > 0 && "border-danger/30 bg-danger-soft",
      )}
    >
      <span
        className={cn(
          "flex size-9 shrink-0 items-center justify-center rounded-full bg-surface",
          tone === "danger" && value > 0 ? "text-danger" : "text-accent",
        )}
      >
        {icon}
      </span>
      <div className="min-w-0">
        <p className="text-2xl font-semibold leading-tight tabular-nums">
          {count(value)}
        </p>
        <p className="truncate text-[13px] text-muted-foreground">{label}</p>
      </div>
    </div>
  );
}

function Health({ connection }: { connection: Connection }) {
  const m = connection.messages_24h;
  const rate =
    m.outbound > 0
      ? Math.max(0, Math.round(((m.outbound - m.failed) / m.outbound) * 100))
      : null;
  return (
    <Card className="min-w-0">
      <CardSection className="space-y-5">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <h2 className="text-lg font-semibold">Last 24 hours</h2>
            <p className="mt-1 truncate text-sm text-muted-foreground">
              {connection.display_name || "Your WhatsApp number"}
              {connection.display_phone_number
                ? ` · ${connection.display_phone_number}`
                : ""}
            </p>
          </div>
          <Badge tone={connection.status === "active" ? "success" : "warning"}>
            {connection.status === "active" ? "Connected" : "Not live"}
          </Badge>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Metric
            label="Messages received"
            value={m.inbound}
            icon={<ArrowDownLeft className="size-4" aria-hidden />}
          />
          <Metric
            label="Messages sent"
            value={m.outbound}
            icon={<ArrowUpRight className="size-4" aria-hidden />}
          />
          <Metric
            label="Messages failed"
            value={m.failed}
            tone="danger"
            icon={<AlertTriangle className="size-4" aria-hidden />}
          />
        </div>
        <dl className="grid grid-cols-1 gap-x-6 gap-y-3 text-sm sm:grid-cols-3">
          <div>
            <dt className="text-muted-foreground">Last message in</dt>
            <dd className="font-medium">
              {connection.last_inbound_at ? (
                <time
                  dateTime={connection.last_inbound_at}
                  title={dateTime(connection.last_inbound_at)}
                >
                  {timeAgo(connection.last_inbound_at)}
                </time>
              ) : (
                "None yet"
              )}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Last message out</dt>
            <dd className="font-medium">
              {connection.last_outbound_at ? (
                <time
                  dateTime={connection.last_outbound_at}
                  title={dateTime(connection.last_outbound_at)}
                >
                  {timeAgo(connection.last_outbound_at)}
                </time>
              ) : (
                "None yet"
              )}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Delivered</dt>
            <dd className="font-medium">
              {rate === null ? "No messages sent" : `${rate}%`}
            </dd>
          </div>
        </dl>
        {connection.last_error_code ? (
          <Notice
            tone="warning"
            title={`Last problem${connection.last_error_at ? `, ${timeAgo(connection.last_error_at)}` : ""}`}
          >
            {friendlyError(connection.last_error_code)}
          </Notice>
        ) : (
          <Notice tone="success">No problems reported.</Notice>
        )}
      </CardSection>
    </Card>
  );
}

function ReplayButton({ event }: { event: WebhookEvent }) {
  const [open, setOpen] = React.useState(false);
  const replay = useAction(
    () => post<WebhookEvent>(`/pi/whatsapp/events/${event.id}/replay`),
    {
      success: "Trying it again",
      invalidate: [["whatsapp-events"]],
      onSuccess: () => setOpen(false),
    },
  );
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="secondary" size="sm" className="min-h-11">
          <RotateCcw className="size-4" aria-hidden />
          Try again
        </Button>
      </DialogTrigger>
      <DialogContent
        title="Try this again?"
        description="Pi will handle this WhatsApp event again. Pi never sends the same reply twice for one message."
      >
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <DialogClose asChild>
            <Button variant="secondary">Cancel</Button>
          </DialogClose>
          <Button loading={replay.isPending} onClick={() => replay.mutate()}>
            Try again
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function EventRow({ event }: { event: WebhookEvent }) {
  const meta = STATUS_META[event.status] ?? {
    label: event.status,
    tone: "neutral" as const,
  };
  return (
    <li
      className={cn(
        "flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between",
        event.status === "failed" && "bg-danger-soft/40",
      )}
    >
      <div className="min-w-0 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium">
            {KIND_LABEL[event.kind] ?? event.kind}
          </span>
          <Badge tone={meta.tone}>{meta.label}</Badge>
          {event.duplicate_count > 0 ? (
            <Badge tone="neutral">
              <Copy className="size-3" aria-hidden />
              Sent {event.duplicate_count + 1}× by WhatsApp
            </Badge>
          ) : null}
        </div>
        <p className="text-[13px] text-muted-foreground">
          <time dateTime={event.created_at} title={dateTime(event.created_at)}>
            {timeAgo(event.created_at)}
          </time>
          {" · "}
          {event.attempts === 1 ? "1 attempt" : `${event.attempts} attempts`}
          {event.processed_at
            ? ` · handled ${timeAgo(event.processed_at)}`
            : ""}
        </p>
        {event.error_code ? (
          <p className="break-words text-sm text-danger">
            {friendlyError(event.error_code)}
          </p>
        ) : null}
      </div>
      {REPLAYABLE.has(event.status) ? (
        <div className="shrink-0">
          <ReplayButton event={event} />
        </div>
      ) : null}
    </li>
  );
}

export function WhatsAppActivityPage() {
  const can = useCan();
  const key = useBusinessKey();
  const allowed = can("pi.whatsapp.manage");
  const [status, setStatus] = React.useState("");
  const [page, setPage] = React.useState(1);
  const connection = useQuery({
    queryKey: key(["whatsapp-connection"]),
    queryFn: () => get<Connection | null>("/pi/whatsapp"),
    enabled: allowed,
    refetchInterval: 60_000,
  });
  const events = useQuery({
    queryKey: key(["whatsapp-events", status, page]),
    queryFn: () =>
      get<EventPage>("/pi/whatsapp/events", {
        status: status || undefined,
        page,
        page_size: PAGE_SIZE,
      }),
    enabled: allowed,
    refetchInterval: 30_000,
  });
  const pages = events.data
    ? Math.max(1, Math.ceil(events.data.total / PAGE_SIZE))
    : 1;

  return (
    <div className="min-w-0">
      <PageHeader
        title="WhatsApp activity"
        description="How messages are flowing through your number, and anything that needs a retry."
        action={
          <Button asChild variant="secondary">
            <Link href="/settings/whatsapp">
              <ArrowLeft className="size-4" aria-hidden />
              Back to WhatsApp
            </Link>
          </Button>
        }
      />
      {!allowed ? (
        <Notice tone="warning" title="No access">
          Ask your business owner for access to WhatsApp settings.
        </Notice>
      ) : (
        <div className="space-y-6">
          {connection.isLoading ? (
            <LoadingBlock rows={2} label="Loading WhatsApp health" />
          ) : connection.isError ? (
            <ErrorState
              message={errorText(connection.error)}
              onRetry={() => void connection.refetch()}
            />
          ) : connection.data ? (
            <Health connection={connection.data} />
          ) : (
            <Notice
              tone="info"
              title="No WhatsApp number connected"
              action={
                <Button asChild size="sm">
                  <Link href="/settings/whatsapp">Connect WhatsApp</Link>
                </Button>
              }
            >
              Connect your number to see its activity here.
            </Notice>
          )}

          <section className="min-w-0 space-y-3" aria-labelledby="events-title">
            <div>
              <h2 id="events-title" className="text-lg font-semibold">
                Events from WhatsApp
              </h2>
              <p className="text-sm text-muted-foreground">
                Every message and delivery update WhatsApp sent to Pi. Repeats
                are kept once, so a customer never gets a second reply.
              </p>
            </div>
            <div
              role="group"
              aria-label="Filter by status"
              className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0"
            >
              <div className="flex w-max gap-2">
                {FILTERS.map((f) => (
                  <button
                    key={f.value || "all"}
                    type="button"
                    aria-pressed={status === f.value}
                    onClick={() => {
                      setStatus(f.value);
                      setPage(1);
                    }}
                    className={cn(
                      "min-h-11 whitespace-nowrap rounded-full border px-4 text-sm font-medium transition-colors",
                      status === f.value
                        ? "border-accent bg-accent-soft text-accent-soft-foreground"
                        : "border-border bg-surface text-foreground-secondary hover:bg-surface-muted",
                    )}
                  >
                    {f.label}
                  </button>
                ))}
              </div>
            </div>
            {events.isLoading ? (
              <LoadingBlock rows={4} label="Loading events" />
            ) : events.isError ? (
              <ErrorState
                message={errorText(events.error)}
                onRetry={() => void events.refetch()}
              />
            ) : !events.data?.items.length ? (
              <Card>
                <EmptyState
                  icon={<ScrollText className="size-5" aria-hidden />}
                  title={status ? "Nothing with this status" : "No events yet"}
                >
                  {status
                    ? "Try another filter."
                    : "Events appear here once customers message your number."}
                </EmptyState>
              </Card>
            ) : (
              <Card className="min-w-0 overflow-hidden">
                <ul className="divide-y divide-border">
                  {events.data.items.map((e) => (
                    <EventRow key={e.id} event={e} />
                  ))}
                </ul>
              </Card>
            )}
            {events.data && pages > 1 ? (
              <div className="flex items-center justify-between gap-3">
                <Button
                  variant="secondary"
                  disabled={page <= 1}
                  onClick={() => setPage(page - 1)}
                >
                  Newer
                </Button>
                <span className="text-sm text-muted-foreground">
                  Page {page} of {pages}
                </span>
                <Button
                  variant="secondary"
                  disabled={page >= pages}
                  onClick={() => setPage(page + 1)}
                >
                  Older
                </Button>
              </div>
            ) : null}
          </section>
        </div>
      )}
    </div>
  );
}
