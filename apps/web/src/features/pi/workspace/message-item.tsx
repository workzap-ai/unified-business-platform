"use client";

import { useState } from "react";
import {
  AlertCircle,
  AudioLines,
  Check,
  CheckCheck,
  ChevronRight,
  Clock,
  ImageIcon,
  PackageCheck,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { formatDateTime, formatMoney, formatTime } from "@/lib/format";
import { Tooltip } from "@/components/ui/overlays";
import { StatusBadge } from "@/components/app/status-badge";
import type { Message, ToolEvent } from "../types";
import { agentLabel, toolLabel } from "./lib";

type Names = {
  agentNames: Map<string, string>;
  toolNames: Map<string, string>;
};

export function MessageItem({
  message,
  names,
}: {
  message: Message;
  names: Names;
}) {
  if (message.sender_type === "system") {
    return (
      <li className="flex justify-center py-1">
        <p className="max-w-[85%] rounded-full bg-surface-muted px-3 py-1 text-center text-xs text-muted-foreground">
          {message.body}
          <span className="mx-1.5" aria-hidden="true">
            ·
          </span>
          <time
            dateTime={message.created_at}
            title={formatDateTime(message.created_at)}
          >
            {formatTime(message.created_at)}
          </time>
        </p>
      </li>
    );
  }

  const inbound = message.direction === "inbound";
  const ai = message.sender_type === "ai";
  const label = inbound
    ? null
    : ai
      ? `PI · ${agentLabel(message.agent_key, names.agentNames)}`
      : (message.sent_by_label ?? "Team");

  return (
    <li className={cn("flex flex-col", inbound ? "items-start" : "items-end")}>
      <div
        className={cn(
          "flex max-w-[85%] flex-col sm:max-w-[72%]",
          inbound ? "items-start" : "items-end",
        )}
      >
        {label && (
          <p
            className={cn(
              "mb-1 px-1 text-[11px] font-medium",
              ai ? "text-pi-soft-foreground" : "text-primary-soft-foreground",
            )}
          >
            {label}
          </p>
        )}
        <div
          className={cn(
            "rounded-2xl px-3.5 py-2 text-[13.5px] leading-relaxed",
            inbound && "rounded-bl-md bg-surface-muted text-foreground",
            ai && "rounded-br-md bg-pi-soft text-foreground",
            !inbound && !ai && "rounded-br-md bg-primary-soft text-foreground",
          )}
        >
          <MediaBlock message={message} />
          {message.body && (
            <p className="break-words whitespace-pre-wrap">{message.body}</p>
          )}
          {message.confirmation && (
            <ConfirmationCard confirmation={message.confirmation} />
          )}
          <div
            className={cn(
              "mt-1 flex items-center gap-1 text-[11px] text-muted-foreground",
              !inbound && "justify-end",
            )}
          >
            <time
              dateTime={message.created_at}
              title={formatDateTime(message.created_at)}
            >
              {formatTime(message.created_at)}
            </time>
            {!inbound && <DeliveryStatus message={message} />}
          </div>
        </div>
        {inbound && message.status === "failed" && (
          <p className="mt-1 flex items-center gap-1 px-1 text-[11px] text-danger">
            <AlertCircle className="size-3" aria-hidden="true" /> PI
            couldn&apos;t process this message
          </p>
        )}
        {ai && message.tool_events.length > 0 && (
          <ToolEvents
            events={message.tool_events}
            toolNames={names.toolNames}
          />
        )}
      </div>
    </li>
  );
}

function MediaBlock({ message }: { message: Message }) {
  const media = message.media;
  if (message.message_type === "audio") {
    const seconds = media?.duration_s ?? 0;
    return (
      <div className="mb-1 min-w-52 rounded-xl border border-border bg-surface px-3 py-2">
        <div className="flex items-center gap-2 text-xs font-medium">
          <span className="flex size-7 items-center justify-center rounded-full bg-surface-muted text-muted-foreground">
            <AudioLines className="size-3.5" aria-hidden="true" />
          </span>
          Voice note
          <span className="tabular ml-auto text-muted-foreground">
            {Math.floor(seconds / 60)}:
            {String(Math.round(seconds % 60)).padStart(2, "0")}
          </span>
        </div>
        {media?.transcript ? (
          <div className="mt-2 border-t border-border pt-2">
            <p className="text-2xs font-semibold tracking-wide text-muted-foreground uppercase">
              Transcript
            </p>
            <p className="mt-0.5 text-[13px] break-words whitespace-pre-wrap">
              {media.transcript}
            </p>
          </div>
        ) : (
          <p className="mt-2 text-xs text-muted-foreground">
            No transcript available.
          </p>
        )}
      </div>
    );
  }
  if (message.message_type === "image") {
    return (
      <div className="mb-1 min-w-52">
        <div
          className="flex h-28 items-center justify-center rounded-xl border border-border bg-surface-sunken text-muted-foreground"
          role="img"
          aria-label="Image sent by the customer"
        >
          <ImageIcon className="size-6" aria-hidden="true" />
        </div>
        {media?.description && (
          <div className="mt-2">
            <p className="text-2xs font-semibold tracking-wide text-pi uppercase">
              PI saw:
            </p>
            <p className="mt-0.5 text-[13px] break-words">
              {media.description}
            </p>
          </div>
        )}
      </div>
    );
  }
  return null;
}

const DELIVERY: Record<
  string,
  { icon: typeof Check; label: string; className?: string }
> = {
  queued: { icon: Clock, label: "Queued to send" },
  sent: { icon: Check, label: "Sent" },
  delivered: { icon: CheckCheck, label: "Delivered" },
  read: { icon: CheckCheck, label: "Read by customer", className: "text-info" },
  failed: {
    icon: AlertCircle,
    label: "Not delivered",
    className: "text-danger",
  },
};

function DeliveryStatus({ message }: { message: Message }) {
  const d = DELIVERY[message.status];
  if (!d) return null;
  const Icon = d.icon;
  const label =
    message.status === "failed" && message.error_code
      ? `${d.label} (WhatsApp rejected the message)`
      : d.label;
  return (
    <Tooltip content={label}>
      <span
        tabIndex={0}
        aria-label={label}
        className={cn(
          "inline-flex rounded focus-visible:outline-2 focus-visible:outline-ring",
          d.className,
        )}
      >
        <Icon className="size-3.5" aria-hidden="true" />
      </span>
    </Tooltip>
  );
}

function ToolEvents({
  events,
  toolNames,
}: {
  events: ToolEvent[];
  toolNames: Map<string, string>;
}) {
  const [open, setOpen] = useState(false);
  const failures = events.filter(
    (e) => e.status === "error" || e.status === "denied",
  ).length;
  return (
    <div className="mt-1 w-full max-w-full">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="ml-auto flex max-w-full items-center gap-1 rounded-md px-1 py-0.5 text-[11px] text-muted-foreground hover:bg-surface-muted hover:text-foreground"
      >
        <ChevronRight
          className={cn(
            "size-3 shrink-0 transition-transform",
            open && "rotate-90",
          )}
          aria-hidden="true"
        />
        <span className="truncate">
          Used: {events.map((e) => toolLabel(e.tool, toolNames)).join(" · ")}
        </span>
        {failures > 0 && (
          <span className="shrink-0 font-semibold text-danger">
            · {failures} failed
          </span>
        )}
      </button>
      {open && (
        <ul className="mt-1 space-y-1 rounded-lg border border-border bg-surface p-2">
          {events.map((e, i) => (
            <li
              key={`${e.tool}-${i}`}
              className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs"
            >
              <span className="font-medium">
                {toolLabel(e.tool, toolNames)}
              </span>
              <StatusBadge status={e.status} />
              {e.summary && (
                <span className="w-full text-muted-foreground">
                  {e.summary}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ConfirmationCard({
  confirmation,
}: {
  confirmation: NonNullable<Message["confirmation"]>;
}) {
  return (
    <div className="my-1.5 rounded-xl border border-border bg-surface px-3 py-2.5">
      <div className="flex items-center gap-2">
        <PackageCheck className="size-4 text-pi" aria-hidden="true" />
        <p className="text-xs font-semibold">Order summary</p>
        <StatusBadge
          status={confirmation.status}
          label={
            confirmation.status === "pending" ? "Awaiting customer" : undefined
          }
          className="ml-auto"
        />
      </div>
      <dl className="mt-2 grid grid-cols-2 gap-2 text-xs">
        <div>
          <dt className="text-muted-foreground">Reference</dt>
          <dd className="font-mono font-medium">{confirmation.reference}</dd>
        </div>
        <div className="text-right">
          <dt className="text-muted-foreground">Total</dt>
          <dd className="tabular font-semibold">
            {formatMoney(confirmation.total, confirmation.currency)}
          </dd>
        </div>
      </dl>
    </div>
  );
}
