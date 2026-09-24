"use client";

import { Fragment, useEffect, useLayoutEffect, useRef, useState } from "react";
import Link from "next/link";
import { isToday, isYesterday } from "date-fns";
import {
  ArrowLeft,
  Bot,
  CircleX,
  MessageSquareOff,
  MoreHorizontal,
  PanelRight,
  UserCheck,
  UserRound,
  UserRoundPlus,
} from "lucide-react";
import { formatDate } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Avatar, Skeleton } from "@/components/ui/display";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/overlays";
import { ConfirmDialog } from "@/components/app/forms";
import { EmptyState, ErrorState } from "@/components/app/states";
import { StatusBadge, statusLabel } from "@/components/app/status-badge";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import { piService } from "../service";
import type { Conversation, Message } from "../types";
import { piKeys } from "./lib";
import { Composer } from "./composer";
import {
  CreateHandoffDialog,
  TakeoverDialog,
  useConversationActions,
} from "./conversation-actions";
import { useConversationContext } from "./context-panel";
import { MessageItem } from "./message-item";
import { usePiNames } from "./parts";

const ACTIVE_HANDOFF = ["open", "assigned", "in_progress"];

function dayLabel(iso: string) {
  const d = new Date(iso);
  if (isToday(d)) return "Today";
  if (isYesterday(d)) return "Yesterday";
  return formatDate(d, "EEEE, d MMM yyyy");
}

export function ConversationThread({
  conversationId,
  listItem,
  onBack,
  onOpenContext,
  showContextButton,
}: {
  conversationId: string;
  listItem?: Conversation;
  onBack?: () => void;
  onOpenContext: () => void;
  showContextButton: boolean;
}) {
  const { canAny, can } = useSession();
  const canReply = can("pi.inbox.reply");
  const canHandoff = canAny("pi.handoffs.manage", "pi.inbox.reply");
  const context = useConversationContext(conversationId);
  const conversation = context.data?.conversation ?? listItem;
  const messages = useScopedQuery<Message[]>(
    piKeys.messages(conversationId),
    () => piService.messages(conversationId),
    {
      refetchInterval: 15_000,
    },
  );
  const names = usePiNames();
  const actions = useConversationActions(conversationId);
  const [confirm, setConfirm] = useState<
    "takeover" | "return" | "close" | null
  >(null);
  const [handoffOpen, setHandoffOpen] = useState(false);

  // Mark read once per opened conversation, after its messages load.
  const markRead = useScopedMutation((id: string) => piService.markRead(id), {
    invalidate: [["pi", "conversations"]],
    error: "Couldn't mark the conversation as read.",
  });
  const marked = useRef<string | null>(null);
  const loaded = messages.isSuccess;
  const { mutate: markReadMutate } = markRead;
  useEffect(() => {
    if (!loaded || marked.current === conversationId) return;
    marked.current = conversationId;
    markReadMutate(conversationId);
  }, [loaded, conversationId, markReadMutate]);

  // Auto-scroll: jump to the latest message on open; follow new messages if near the bottom.
  const scroller = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  const lastId = useRef<string | null>(null);
  const count = messages.data?.length ?? 0;
  useLayoutEffect(() => {
    const el = scroller.current;
    if (!el || !count) return;
    if (lastId.current !== conversationId || stick.current)
      el.scrollTop = el.scrollHeight;
    lastId.current = conversationId;
  }, [count, conversationId]);

  const run = (mutation: {
    mutate: (v: undefined, o?: { onSuccess?: () => void }) => void;
  }) => mutation.mutate(undefined, { onSuccess: () => setConfirm(null) });

  const handoffActive = Boolean(
    conversation?.handoff_status &&
    ACTIVE_HANDOFF.includes(conversation.handoff_status),
  );

  return (
    <section
      className="flex h-full min-h-0 flex-col bg-background"
      aria-label={
        conversation
          ? `Conversation with ${conversation.customer_name}`
          : "Conversation"
      }
    >
      <header className="flex shrink-0 items-center gap-2.5 border-b border-border bg-surface px-3 py-2.5 sm:px-4">
        {onBack && (
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={onBack}
            aria-label="Back to conversations"
          >
            <ArrowLeft />
          </Button>
        )}
        {conversation ? (
          <>
            <Avatar
              name={conversation.customer_name}
              size="lg"
              className="hidden size-9 sm:inline-flex"
            />
            <div className="min-w-0 flex-1">
              <div className="flex min-w-0 items-center gap-1.5">
                <h2 className="truncate text-[14px] font-semibold">
                  {conversation.customer_name}
                </h2>
                <StatusBadge
                  status={conversation.mode}
                  label={conversation.mode === "ai" ? "AI" : "Human"}
                />
                {handoffActive && (
                  <StatusBadge
                    status={conversation.handoff_status!}
                    label={`Handoff · ${statusLabel(conversation.handoff_status!)}`}
                    className="hidden sm:inline-flex"
                  />
                )}
                {conversation.status === "closed" && (
                  <StatusBadge
                    status="closed"
                    className="hidden sm:inline-flex"
                  />
                )}
              </div>
              <p className="tabular truncate text-xs text-muted-foreground">
                {conversation.customer_phone ?? "No phone on file"}
                {conversation.assigned_label &&
                  ` · ${conversation.assigned_label}`}
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-1.5">
              {canReply &&
                conversation.status === "open" &&
                (conversation.mode === "ai" ? (
                  <Button size="sm" onClick={() => setConfirm("takeover")}>
                    <UserRound />{" "}
                    <span className="hidden sm:inline">Take over</span>
                  </Button>
                ) : (
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => setConfirm("return")}
                  >
                    <Bot className="text-pi" />{" "}
                    <span className="hidden sm:inline">Return to PI</span>
                  </Button>
                ))}
              {showContextButton && (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={onOpenContext}
                  aria-label="Show conversation details"
                >
                  <PanelRight /> <span className="hidden lg:inline">Info</span>
                </Button>
              )}
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label="More conversation actions"
                  >
                    <MoreHorizontal />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent className="w-60">
                  {canHandoff && (
                    <DropdownMenuItem
                      disabled={handoffActive}
                      onSelect={() => setHandoffOpen(true)}
                    >
                      <UserRoundPlus />
                      <span className="flex flex-col">
                        Create handoff
                        {handoffActive && (
                          <span className="text-2xs text-muted-foreground">
                            A handoff is already open
                          </span>
                        )}
                      </span>
                    </DropdownMenuItem>
                  )}
                  {handoffActive && (
                    <DropdownMenuItem asChild>
                      <Link href="/pi/handoffs">
                        <UserCheck /> View handoff queue
                      </Link>
                    </DropdownMenuItem>
                  )}
                  <DropdownMenuItem asChild>
                    <Link href={`/customers/${conversation.customer_id}`}>
                      <UserRound /> Open customer profile
                    </Link>
                  </DropdownMenuItem>
                  {canReply && conversation.status === "open" && (
                    <>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem
                        destructive
                        onSelect={() => setConfirm("close")}
                      >
                        <CircleX /> Close conversation
                      </DropdownMenuItem>
                    </>
                  )}
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </>
        ) : context.isError ? (
          <p className="flex-1 text-[13px] text-muted-foreground">
            Conversation details unavailable
          </p>
        ) : (
          <div className="flex flex-1 items-center gap-3">
            <Skeleton className="size-9 rounded-full" />
            <div className="space-y-1.5">
              <Skeleton className="h-3.5 w-40" />
              <Skeleton className="h-3 w-28" />
            </div>
          </div>
        )}
      </header>

      <div
        ref={scroller}
        onScroll={(e) => {
          const el = e.currentTarget;
          stick.current =
            el.scrollHeight - el.scrollTop - el.clientHeight < 120;
        }}
        className="scrollbar-thin min-h-0 flex-1 overflow-y-auto px-3 py-4 sm:px-5"
        aria-live="polite"
        aria-relevant="additions"
      >
        {messages.isError ? (
          <ErrorState
            error={messages.error}
            onRetry={() => void messages.refetch()}
          />
        ) : messages.isPending ? (
          <ul className="space-y-4" aria-hidden="true">
            {Array.from({ length: 6 }, (_, i) => (
              <li key={i} className={i % 2 ? "flex justify-end" : "flex"}>
                <Skeleton
                  className="h-14 rounded-2xl"
                  style={{ width: `${38 + ((i * 19) % 30)}%` }}
                />
              </li>
            ))}
          </ul>
        ) : messages.data.length === 0 ? (
          <EmptyState
            compact
            icon={MessageSquareOff}
            title="No messages yet"
            description="Messages in this conversation will appear here."
          />
        ) : (
          <ol className="mx-auto max-w-3xl space-y-3" aria-label="Messages">
            {messages.data.map((m, i) => {
              const prev = messages.data[i - 1];
              const newDay =
                !prev ||
                new Date(prev.created_at).toDateString() !==
                  new Date(m.created_at).toDateString();
              return (
                <Fragment key={m.id}>
                  {newDay && (
                    <li
                      className="flex items-center gap-3 py-1"
                      role="separator"
                      aria-label={dayLabel(m.created_at)}
                    >
                      <span className="h-px flex-1 bg-border" />
                      <span className="text-2xs font-medium text-muted-foreground">
                        {dayLabel(m.created_at)}
                      </span>
                      <span className="h-px flex-1 bg-border" />
                    </li>
                  )}
                  <MessageItem message={m} names={names} />
                </Fragment>
              );
            })}
          </ol>
        )}
      </div>

      {conversation && (
        <Composer
          key={conversationId}
          conversation={conversation}
          canReply={canReply}
          onTakeover={() => setConfirm("takeover")}
        />
      )}

      {conversation && (
        <>
          <TakeoverDialog
            open={confirm === "takeover" || confirm === "return"}
            onOpenChange={(o) => !o && setConfirm(null)}
            mode={confirm === "return" ? "return" : "takeover"}
            customerName={conversation.customer_name}
            loading={actions.takeover.isPending || actions.returnToAi.isPending}
            onConfirm={() =>
              run(confirm === "return" ? actions.returnToAi : actions.takeover)
            }
          />
          <ConfirmDialog
            open={confirm === "close"}
            onOpenChange={(o) => !o && setConfirm(null)}
            title="Close this conversation?"
            description={`The conversation with ${conversation.customer_name} moves to Closed.`}
            consequences={[
              "It leaves the open inbox and stops counting as unresolved.",
              "If the customer writes again, the conversation reopens.",
            ]}
            confirmLabel="Close conversation"
            destructive
            loading={actions.close.isPending}
            onConfirm={() => run(actions.close)}
          />
          <CreateHandoffDialog
            conversationId={conversationId}
            customerName={conversation.customer_name}
            open={handoffOpen}
            onOpenChange={setHandoffOpen}
          />
        </>
      )}
    </section>
  );
}
