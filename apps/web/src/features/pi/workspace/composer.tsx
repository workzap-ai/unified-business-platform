"use client";

import { useState } from "react";
import { Bot, Lock, Paperclip, SendHorizontal } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { useScopedMutation } from "@/hooks/use-scoped";
import { piService } from "../service";
import type { Conversation } from "../types";
import { piKeys } from "./lib";
import { DisabledHint } from "./parts";

const LIMIT = 4096;

export function Composer({
  conversation,
  canReply,
  onTakeover,
}: {
  conversation: Conversation;
  canReply: boolean;
  onTakeover: () => void;
}) {
  if (conversation.status === "closed") {
    return (
      <Bar icon={<Lock className="size-4" />}>
        <p className="text-[13px] font-medium">This conversation is closed</p>
        <p className="text-xs text-muted-foreground">
          It reopens automatically when the customer sends a new message.
        </p>
      </Bar>
    );
  }
  if (conversation.mode === "ai") {
    return (
      <Bar
        tone="pi"
        icon={<Bot className="size-4" />}
        action={
          canReply ? (
            <Button size="sm" variant="secondary" onClick={onTakeover}>
              Take over to reply
            </Button>
          ) : undefined
        }
      >
        <p className="text-[13px] font-medium">
          PI is handling this conversation
        </p>
        <p className="text-xs text-muted-foreground">
          {canReply
            ? "Automatic replies are on. Take over to reply yourself."
            : "Replying requires the inbox reply permission."}
        </p>
      </Bar>
    );
  }
  if (!canReply) {
    return (
      <Bar icon={<Lock className="size-4" />}>
        <p className="text-[13px] font-medium">
          A team member is handling this conversation
        </p>
        <p className="text-xs text-muted-foreground">
          You can read it, but replying requires the inbox reply permission.
        </p>
      </Bar>
    );
  }
  return <ReplyBox conversationId={conversation.id} />;
}

function Bar({
  children,
  icon,
  action,
  tone = "neutral",
}: {
  children: React.ReactNode;
  icon: React.ReactNode;
  action?: React.ReactNode;
  tone?: "neutral" | "pi";
}) {
  return (
    <div className="shrink-0 border-t border-border bg-surface p-3">
      <div
        className={cn(
          "flex flex-wrap items-center gap-3 rounded-lg px-3 py-2.5",
          tone === "pi" ? "bg-pi-soft" : "bg-surface-muted",
        )}
      >
        <span
          className={cn(
            "shrink-0",
            tone === "pi" ? "text-pi" : "text-muted-foreground",
          )}
          aria-hidden="true"
        >
          {icon}
        </span>
        <div className="min-w-0 flex-1">{children}</div>
        {action}
      </div>
    </div>
  );
}

function ReplyBox({ conversationId }: { conversationId: string }) {
  const [draft, setDraft] = useState("");
  const send = useScopedMutation(
    (body: string) => piService.sendMessage(conversationId, body),
    {
      invalidate: [
        [...piKeys.messages(conversationId)],
        ["pi", "conversations"],
      ],
      error:
        "Your message wasn't sent. It's still in the box, so you can try again.",
      onSuccess: () => setDraft(""),
    },
  );
  const length = draft.length;
  const over = length > LIMIT;
  const blocked = !draft.trim() || over || send.isPending;

  function submit() {
    if (blocked) return;
    send.mutate(draft);
  }

  return (
    <form
      className="shrink-0 border-t border-border bg-surface p-3"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <label htmlFor="pi-reply" className="sr-only">
        Reply to customer
      </label>
      <div className="rounded-lg border border-border bg-surface shadow-sm focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/15">
        <textarea
          id="pi-reply"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (
              e.key === "Enter" &&
              !e.shiftKey &&
              !e.nativeEvent.isComposing
            ) {
              e.preventDefault();
              submit();
            }
          }}
          rows={2}
          placeholder="Write a reply… (Enter to send, Shift+Enter for a new line)"
          aria-invalid={over || undefined}
          aria-describedby="pi-reply-count"
          className="block max-h-40 min-h-14 w-full resize-none bg-transparent px-3 pt-2.5 text-[13.5px] leading-relaxed outline-none placeholder:text-muted-foreground/80"
          disabled={send.isPending}
        />
        <div className="flex items-center gap-2 px-2 pb-2">
          <DisabledHint content="Attachments are sent from WhatsApp in this version">
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              disabled
              aria-label="Attach file (unavailable)"
            >
              <Paperclip />
            </Button>
          </DisabledHint>
          <span
            id="pi-reply-count"
            className={cn(
              "tabular ml-auto text-2xs",
              over ? "font-semibold text-danger" : "text-muted-foreground",
            )}
            aria-live="polite"
          >
            {length.toLocaleString()} / {LIMIT.toLocaleString()}
            {over && " · too long for WhatsApp"}
          </span>
          <Button
            type="submit"
            size="sm"
            loading={send.isPending}
            disabled={blocked}
          >
            {!send.isPending && <SendHorizontal />} Send
          </Button>
        </div>
      </div>
    </form>
  );
}
