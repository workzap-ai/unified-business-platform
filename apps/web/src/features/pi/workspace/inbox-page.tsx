"use client";

import { useCallback, useState } from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { MessagesSquare, PanelRightClose } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { DialogHeader, SheetContent } from "@/components/ui/overlays";
import { EmptyState } from "@/components/app/states";
import { useScopedQuery } from "@/hooks/use-scoped";
import { useUrlState } from "@/hooks/use-url-state";
import { piService, type ConversationFilters } from "../service";
import { piKeys } from "./lib";
import { ContextPanel } from "./context-panel";
import { ConversationList, type InboxFilters } from "./conversation-list";
import { ConversationThread } from "./conversation-thread";
import { useMediaQuery } from "./parts";

const DEFAULTS = {
  conversation: "",
  search: "",
  status: "",
  mode: "",
  assignment: "",
  unread: "",
};

/** Three-panel operations inbox: conversations, thread + composer, customer/AI context. */
export function InboxPage() {
  const [state, setState] = useUrlState(DEFAULTS);
  const desktop = useMediaQuery("(min-width: 768px)");
  const wide = useMediaQuery("(min-width: 1280px)");
  const [panelOpen, setPanelOpen] = useState(true);
  const [sheetOpen, setSheetOpen] = useState(false);

  const filters: ConversationFilters = {
    search: state.search || undefined,
    status: state.status || undefined,
    mode: state.mode || undefined,
    assignment:
      state.assignment === "mine" || state.assignment === "unassigned"
        ? state.assignment
        : "",
    unread: state.unread === "1" || undefined,
  };
  const conversations = useScopedQuery(
    piKeys.conversations(filters),
    () => piService.conversations(filters),
    {
      refetchInterval: 30_000,
      placeholderData: (previous) => previous,
    },
  );

  const selectedId = state.conversation;
  const listItem = conversations.data?.items.find((c) => c.id === selectedId);

  const onFilters = useCallback(
    (patch: Partial<InboxFilters>) => setState(patch),
    [setState],
  );
  const onClear = useCallback(
    () =>
      setState({
        search: "",
        status: "",
        mode: "",
        assignment: "",
        unread: "",
      }),
    [setState],
  );
  const select = useCallback(
    (id: string) => setState({ conversation: id }),
    [setState],
  );

  const inlinePanel = wide && panelOpen;
  const list = (
    <ConversationList
      filters={{
        search: state.search,
        status: state.status,
        mode: state.mode,
        assignment: state.assignment,
        unread: state.unread,
      }}
      onFilters={onFilters}
      onClear={onClear}
      query={conversations}
      selectedId={selectedId}
      onSelect={select}
    />
  );
  const thread = selectedId ? (
    <ConversationThread
      key={selectedId}
      conversationId={selectedId}
      listItem={listItem}
      onBack={desktop ? undefined : () => setState({ conversation: "" })}
      onOpenContext={() => (wide ? setPanelOpen(true) : setSheetOpen(true))}
      showContextButton={!inlinePanel}
    />
  ) : (
    <div className="flex h-full items-center justify-center bg-background">
      <EmptyState
        tone="pi"
        icon={MessagesSquare}
        title="Select a conversation"
        description="Pick a conversation to read the thread, see what PI did and step in when a customer needs a person."
      />
    </div>
  );

  return (
    <div className="flex h-full min-h-0 border-t border-border">
      {desktop ? (
        <>
          <aside
            className="w-[320px] shrink-0 border-r border-border bg-surface lg:w-[340px]"
            aria-label="Conversation list"
          >
            {list}
          </aside>
          <div className="min-w-0 flex-1">{thread}</div>
          {selectedId && inlinePanel && (
            <aside
              className="flex w-[340px] shrink-0 flex-col border-l border-border bg-surface"
              aria-label="Conversation details"
            >
              <div className="flex shrink-0 items-center justify-between border-b border-border px-4 py-2.5">
                <h2 className="text-[13.5px] font-semibold">Details</h2>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  onClick={() => setPanelOpen(false)}
                  aria-label="Hide conversation details"
                >
                  <PanelRightClose />
                </Button>
              </div>
              <div className="scrollbar-thin min-h-0 flex-1 overflow-y-auto">
                <ContextPanel conversationId={selectedId} />
              </div>
            </aside>
          )}
        </>
      ) : (
        <div className={cn("min-w-0 flex-1", !selectedId && "bg-surface")}>
          {selectedId ? thread : list}
        </div>
      )}

      {!inlinePanel && selectedId && (
        <DialogPrimitive.Root open={sheetOpen} onOpenChange={setSheetOpen}>
          <SheetContent width="md" className="p-0">
            <DialogHeader
              title="Conversation details"
              description="Customer, memory, orders and what PI did."
            />
            <div className="scrollbar-thin min-h-0 flex-1 overflow-y-auto">
              <ContextPanel conversationId={selectedId} />
            </div>
          </SheetContent>
        </DialogPrimitive.Root>
      )}
    </div>
  );
}
