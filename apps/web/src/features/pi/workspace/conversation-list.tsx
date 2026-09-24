"use client";

import { useRef } from "react";
import Link from "next/link";
import { MessagesSquare, SearchX } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatNumber } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Avatar, Badge, Skeleton } from "@/components/ui/display";
import { SearchInput } from "@/components/app/filters";
import { EmptyState, ErrorState } from "@/components/app/states";
import { statusLabel } from "@/components/app/status-badge";
import type { Page } from "@/services/api-client";
import type { Conversation } from "../types";
import { ModeIndicator, TimeAgo, senderPrefix } from "./parts";

export type InboxFilters = {
  search: string;
  status: string;
  mode: string;
  assignment: string;
  unread: string;
};

const CHIPS: { group: keyof InboxFilters; value: string; label: string }[] = [
  { group: "status", value: "open", label: "Open" },
  { group: "status", value: "closed", label: "Closed" },
  { group: "mode", value: "ai", label: "AI" },
  { group: "mode", value: "human", label: "Human" },
  { group: "assignment", value: "mine", label: "Mine" },
  { group: "assignment", value: "unassigned", label: "Unassigned" },
  { group: "unread", value: "1", label: "Unread" },
];

const ACTIVE_HANDOFF = ["open", "assigned", "in_progress"];

export function ConversationList({
  filters,
  onFilters,
  onClear,
  query,
  selectedId,
  onSelect,
}: {
  filters: InboxFilters;
  onFilters: (patch: Partial<InboxFilters>) => void;
  onClear: () => void;
  query: {
    data: Page<Conversation> | undefined;
    isPending: boolean;
    isError: boolean;
    error: unknown;
    refetch: () => unknown;
  };
  selectedId: string;
  onSelect: (id: string) => void;
}) {
  const listRef = useRef<HTMLUListElement>(null);
  const filtered = Boolean(
    filters.search ||
    filters.status ||
    filters.mode ||
    filters.assignment ||
    filters.unread,
  );
  const rows = query.data?.items;

  function onKeyDown(event: React.KeyboardEvent<HTMLUListElement>) {
    const buttons = Array.from(
      listRef.current?.querySelectorAll<HTMLButtonElement>(
        "button[data-conversation]",
      ) ?? [],
    );
    if (!buttons.length) return;
    const index = buttons.indexOf(document.activeElement as HTMLButtonElement);
    let next = -1;
    if (event.key === "ArrowDown" || event.key === "j")
      next = Math.min(buttons.length - 1, index + 1);
    else if (event.key === "ArrowUp" || event.key === "k")
      next = Math.max(0, index <= 0 ? 0 : index - 1);
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = buttons.length - 1;
    if (next >= 0) {
      event.preventDefault();
      buttons[next]?.focus();
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="shrink-0 space-y-2 border-b border-border p-3">
        <div className="flex items-center justify-between gap-2">
          <h1 className="text-[15px] font-semibold tracking-tight">Inbox</h1>
          {query.data && (
            <span className="tabular text-xs text-muted-foreground">
              {formatNumber(query.data.total)} conversations
            </span>
          )}
        </div>
        <SearchInput
          value={filters.search}
          onChange={(search) => onFilters({ search })}
          placeholder="Search customer, phone or message"
        />
        <div
          className="scrollbar-thin -mx-3 flex items-center gap-1.5 overflow-x-auto px-3 pb-0.5"
          role="group"
          aria-label="Filter conversations"
        >
          {CHIPS.map((chip) => {
            const active = filters[chip.group] === chip.value;
            return (
              <button
                key={`${chip.group}-${chip.value}`}
                type="button"
                aria-pressed={active}
                onClick={() =>
                  onFilters({ [chip.group]: active ? "" : chip.value })
                }
                className={cn(
                  "h-7 shrink-0 rounded-full border px-2.5 text-xs font-medium transition-colors",
                  active
                    ? "border-primary/40 bg-primary-soft text-primary-soft-foreground"
                    : "border-border bg-surface text-foreground-secondary hover:bg-surface-muted",
                )}
              >
                {chip.label}
              </button>
            );
          })}
          {filtered && (
            <button
              type="button"
              onClick={onClear}
              className="h-7 shrink-0 px-1.5 text-xs font-medium text-muted-foreground hover:text-foreground"
            >
              Clear
            </button>
          )}
        </div>
      </div>

      <div className="scrollbar-thin min-h-0 flex-1 overflow-y-auto">
        {query.isError ? (
          <ErrorState
            error={query.error}
            onRetry={() => void query.refetch()}
            compact
          />
        ) : query.isPending || !rows ? (
          <ul aria-hidden="true">
            {Array.from({ length: 8 }, (_, i) => (
              <li
                key={i}
                className="flex gap-3 border-b border-border px-3 py-3"
              >
                <Skeleton className="size-9 rounded-full" />
                <div className="flex-1 space-y-2">
                  <Skeleton
                    className="h-3.5"
                    style={{ width: `${45 + ((i * 17) % 35)}%` }}
                  />
                  <Skeleton className="h-3 w-4/5" />
                </div>
              </li>
            ))}
          </ul>
        ) : rows.length === 0 ? (
          filtered ? (
            <EmptyState
              compact
              icon={SearchX}
              title="No conversations match"
              description="Try a different search or clear the filters."
              action={
                <Button variant="secondary" size="sm" onClick={onClear}>
                  Clear filters
                </Button>
              }
            />
          ) : (
            <EmptyState
              compact
              tone="pi"
              icon={MessagesSquare}
              title="No conversations yet"
              description="When customers message your WhatsApp number, their conversations appear here."
              action={
                <Button variant="secondary" size="sm" asChild>
                  <Link href="/pi/whatsapp">WhatsApp setup</Link>
                </Button>
              }
            />
          )
        ) : (
          <ul ref={listRef} onKeyDown={onKeyDown} aria-label="Conversations">
            {rows.map((c) => (
              <li key={c.id}>
                <ConversationRow
                  conversation={c}
                  selected={c.id === selectedId}
                  onSelect={() => onSelect(c.id)}
                />
              </li>
            ))}
          </ul>
        )}
      </div>
      <p className="hidden shrink-0 border-t border-border px-3 py-1.5 text-2xs text-muted-foreground md:block">
        Use ↑ ↓ or J K to move, Enter to open.
      </p>
    </div>
  );
}

function ConversationRow({
  conversation: c,
  selected,
  onSelect,
}: {
  conversation: Conversation;
  selected: boolean;
  onSelect: () => void;
}) {
  const unread = c.unread_count > 0;
  const handoff = c.handoff_status && ACTIVE_HANDOFF.includes(c.handoff_status);
  return (
    <button
      type="button"
      data-conversation={c.id}
      onClick={onSelect}
      aria-current={selected ? "true" : undefined}
      className={cn(
        "relative flex w-full gap-3 border-b border-border px-3 py-2.5 text-left transition-colors focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring",
        selected ? "bg-primary-soft/50" : "hover:bg-surface-muted/70",
      )}
    >
      {selected && (
        <span
          className="absolute inset-y-0 left-0 w-0.5 bg-primary"
          aria-hidden="true"
        />
      )}
      <Avatar name={c.customer_name} size="lg" className="size-9" />
      <span className="block min-w-0 flex-1 overflow-hidden">
        <span className="flex items-center gap-1.5">
          <span
            className={cn(
              "truncate text-[13px]",
              unread ? "font-semibold text-foreground" : "font-medium",
            )}
          >
            {c.customer_name}
          </span>
          <ModeIndicator mode={c.mode} />
          <TimeAgo
            value={c.last_message_at}
            className={cn(
              "ml-auto text-[11px]",
              unread
                ? "font-semibold text-foreground"
                : "text-muted-foreground",
            )}
          />
        </span>
        <span className="mt-0.5 flex items-center gap-2">
          <span
            className={cn(
              "min-w-0 flex-1 truncate text-xs",
              unread ? "text-foreground-secondary" : "text-muted-foreground",
            )}
          >
            {c.last_sender !== "customer" && (
              <span className="font-medium">{senderPrefix(c.last_sender)}</span>
            )}
            {c.last_message_preview}
          </span>
          {unread && (
            <span className="tabular shrink-0 rounded-full bg-primary px-1.5 text-[10.5px] leading-4 font-semibold text-primary-foreground">
              <span className="sr-only">Unread: </span>
              {c.unread_count}
            </span>
          )}
        </span>
        {(handoff || c.pending_confirmation || c.status === "closed") && (
          <span className="mt-1.5 flex flex-wrap gap-1">
            {handoff && (
              <Badge tone="warning" dot>
                Handoff · {statusLabel(c.handoff_status!)}
              </Badge>
            )}
            {c.pending_confirmation && (
              <Badge tone="info">Awaiting confirmation</Badge>
            )}
            {c.status === "closed" && <Badge tone="neutral">Closed</Badge>}
          </span>
        )}
      </span>
    </button>
  );
}
