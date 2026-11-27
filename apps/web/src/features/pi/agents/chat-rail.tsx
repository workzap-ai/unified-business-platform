"use client";

import { MessageSquarePlus, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { relativeTime } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { AgentAvatar } from "./agent-avatar";
import { agentFor } from "./use-agents";
import type { Agent, Chat } from "./meeting-agents-service";

/** New chat button and the list of past chats. Used in the side column and in the phone sheet. */
export function ChatRail({
  chats,
  agents,
  activeId,
  onSelect,
  onNew,
  onDelete,
}: {
  chats: Chat[];
  agents: Agent[] | undefined;
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (chat: Chat) => void;
}) {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="p-3">
        <Button
          variant="secondary"
          className="min-h-11 w-full sm:min-h-9"
          onClick={onNew}
        >
          <MessageSquarePlus /> New chat
        </Button>
      </div>
      {chats.length === 0 ? (
        <p className="px-4 py-3 text-[13px] text-muted-foreground">
          Your chats about this meeting will be listed here.
        </p>
      ) : (
        <ul
          aria-label="Past chats"
          className="scrollbar-thin min-h-0 flex-1 space-y-0.5 overflow-y-auto px-2 pb-3"
        >
          {chats.map((c) => {
            const on = c.id === activeId;
            return (
              <li key={c.id} className="group relative">
                <button
                  type="button"
                  aria-current={on ? "true" : undefined}
                  onClick={() => onSelect(c.id)}
                  className={cn(
                    "flex min-h-14 w-full items-center gap-2.5 rounded-xl py-2 pr-11 pl-2.5 text-left transition-colors",
                    on ? "bg-primary-soft/70" : "hover:bg-surface-muted",
                  )}
                >
                  <AgentAvatar
                    agent={agentFor(agents, c.agent_key)}
                    size="sm"
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13px] font-semibold">
                      {c.title || "New chat"}
                    </span>
                    <span className="flex items-baseline justify-between gap-2 text-xs text-muted-foreground">
                      <span className="truncate">{c.last_text}</span>
                      <span className="shrink-0 text-[11px]">
                        {c.updated_at ? relativeTime(c.updated_at) : ""}
                      </span>
                    </span>
                  </span>
                </button>
                <button
                  type="button"
                  aria-label={`Delete chat ${c.title || "New chat"}`}
                  onClick={() => onDelete(c)}
                  className="absolute top-1/2 right-1 grid size-10 -translate-y-1/2 place-items-center rounded-lg text-muted-foreground transition-opacity hover:bg-danger-soft hover:text-danger focus-visible:opacity-100 sm:size-8 sm:opacity-0 sm:group-focus-within:opacity-100 sm:group-hover:opacity-100"
                >
                  <Trash2 className="size-4" aria-hidden="true" />
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
