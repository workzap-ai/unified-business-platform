"use client";

import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  ChevronsUpDown,
  MessageSquareText,
  MessagesSquare,
  Quote,
  FileText,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/display";
import { Dialog, DialogHeader, SheetContent } from "@/components/ui/overlays";
import { EmptyState, ErrorState } from "@/components/app/states";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import { ApiError, errorMessage } from "@/services/api-client";
import { AgentAvatar, AgentCluster } from "./agent-avatar";
import { AgentChooser } from "./agent-chooser";
import { AssistantBubble, Typing, UserBubble } from "./chat-messages";
import { ChatComposer } from "./chat-composer";
import { ChatRail } from "./chat-rail";
import { ConfirmDialog } from "./confirm-dialog";
import {
  DEFAULT_AGENT_KEY,
  meetingAgentsService,
  PI_AGENT,
  type Chat,
  type ChatDetail,
} from "./meeting-agents-service";
import { agentFor, useAgents } from "./use-agents";

type Pending = {
  token: number;
  text: string;
  sending: boolean;
  error: string;
};

const chatsKey = (id: string) => ["pi", "meeting-intel", id, "chats"];
const chatKey = (id: string, chatId: string) => [...chatsKey(id), chatId];

function failure(e: unknown): string {
  if (e instanceof ApiError && e.code === "MEETING_ASK_UNAVAILABLE")
    return "The answer could not be written right now. Try again in a moment.";
  if (e instanceof ApiError && e.code === "TRANSCRIPT_EMPTY")
    return "This meeting has no transcript yet, so there is nothing to ask.";
  return errorMessage(e, "Something went wrong. Try again.");
}

/**
 * Ask this meeting questions in chats. Answers come only from the transcript and carry the lines
 * they used. A chat is created on the first question.
 */
export function MeetingChat({
  meetingId,
  agentKey,
  hasTranscript,
}: {
  meetingId: string;
  /** the meeting's own agent; new chats start with it */
  agentKey: string | null;
  hasTranscript: boolean;
}) {
  const client = useQueryClient();
  const { scopeKey } = useSession();
  const agents = useAgents();
  const list = useScopedQuery(
    chatsKey(meetingId),
    async () => (await meetingAgentsService.listChats(meetingId)).chats,
    { enabled: hasTranscript },
  );
  const chats = list.data ?? [];

  // undefined: follow the newest chat; null: a new, empty chat; string: that chat
  const [selected, setSelected] = useState<string | null | undefined>(
    undefined,
  );
  const activeId = selected === undefined ? (chats[0]?.id ?? null) : selected;
  const [draftAgent, setDraftAgent] = useState<string | null>(null);
  const [pending, setPending] = useState<Pending | null>(null);
  const [picking, setPicking] = useState(false);
  const [railOpen, setRailOpen] = useState(false);
  const [deleting, setDeleting] = useState<Chat | null>(null);
  const token = useRef(0);

  const detail = useScopedQuery(
    activeId ? chatKey(meetingId, activeId) : ["pi", "no-chat"],
    () => meetingAgentsService.getChat(meetingId, activeId as string),
    { enabled: hasTranscript && activeId !== null },
  );
  const messages = detail.data?.messages ?? [];
  const activeChat = chats.find((c) => c.id === activeId);
  const currentKey = activeId
    ? (activeChat?.agent_key ?? detail.data?.chat.agent_key)
    : (draftAgent ?? agentKey);
  const agent = agentFor(agents.data, currentKey);

  const scroller = useRef<HTMLDivElement>(null);
  const root = useRef<HTMLDivElement>(null);
  // On a phone the panel sits below the meeting header: bring it into view when the tab opens.
  useEffect(() => {
    if (!hasTranscript || window.matchMedia("(min-width: 1024px)").matches)
      return;
    const reduce = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;
    root.current?.scrollIntoView({
      block: "start",
      behavior: reduce ? "auto" : "smooth",
    });
  }, [hasTranscript]);
  useEffect(() => {
    const el = scroller.current;
    if (el) el.scrollTo({ top: el.scrollHeight });
  }, [messages.length, pending, activeId]);

  function pick(id: string | null | undefined) {
    token.current += 1;
    setPending(null);
    setSelected(id);
    setRailOpen(false);
  }

  async function send(text: string) {
    const mine = ++token.current;
    setPending({ token: mine, text, sending: true, error: "" });
    try {
      let chatId = activeId;
      if (!chatId) {
        const c = await meetingAgentsService.createChat(
          meetingId,
          currentKey ?? DEFAULT_AGENT_KEY,
        );
        chatId = c.id;
        if (token.current === mine) setSelected(c.id);
      }
      const r = await meetingAgentsService.sendMessage(meetingId, chatId, text);
      const key = [...scopeKey, ...chatKey(meetingId, chatId)];
      const old = client.getQueryData<ChatDetail>(key);
      if (old)
        client.setQueryData<ChatDetail>(key, {
          ...old,
          messages: [...old.messages, r.user, r.assistant],
        });
      else await client.invalidateQueries({ queryKey: key });
      void client.invalidateQueries({
        queryKey: [...scopeKey, ...chatsKey(meetingId)],
        exact: true,
      });
      setPending((p) => (p?.token === mine ? null : p));
    } catch (e) {
      setPending((p) =>
        p?.token === mine ? { ...p, sending: false, error: failure(e) } : p,
      );
    }
  }

  const changeAgent = useScopedMutation(
    (key: string) =>
      meetingAgentsService.updateChat(meetingId, activeId as string, {
        agent_key: key,
      }),
    { invalidate: [chatsKey(meetingId)], success: "Agent changed" },
  );
  const remove = useScopedMutation(
    (c: Chat) => meetingAgentsService.deleteChat(meetingId, c.id),
    {
      invalidate: [chatsKey(meetingId)],
      success: "Chat deleted",
      onSuccess: (_r, c) => {
        setDeleting(null);
        if (c.id === activeId) pick(undefined);
      },
    },
  );

  if (!hasTranscript)
    return (
      <div className="rounded-2xl border border-dashed border-border bg-surface">
        <EmptyState
          icon={FileText}
          title="Nothing to ask yet"
          description="You can ask this meeting questions as soon as it has a transcript."
        />
      </div>
    );

  const rail = (
    <ChatRail
      chats={chats}
      agents={agents.data}
      activeId={activeId}
      onSelect={pick}
      onNew={() => pick(null)}
      onDelete={setDeleting}
    />
  );
  const loadingChat = activeId !== null && detail.isPending;
  const showEmpty = messages.length === 0 && !pending && !loadingChat;
  const samples = (
    agent.sample_questions.length
      ? agent.sample_questions
      : PI_AGENT.sample_questions
  ).slice(0, 4);

  return (
    <div
      ref={root}
      className="scroll-mt-16 h-[min(46rem,calc(100dvh-13rem))] min-h-[30rem] overflow-hidden rounded-2xl border border-border bg-surface shadow-sm lg:grid lg:grid-cols-[272px_minmax(0,1fr)]"
    >
      <aside
        aria-label="Chats"
        className="hidden min-h-0 border-r border-border bg-surface-muted/40 lg:block"
      >
        {rail}
      </aside>

      <div className="flex h-full min-h-0 flex-col">
        <div className="flex items-center gap-2 border-b border-border px-3 py-2">
          <Button
            variant="secondary"
            size="sm"
            className="min-h-11 lg:hidden"
            onClick={() => setRailOpen(true)}
          >
            <MessagesSquare /> Chats
            {chats.length > 0 ? ` (${chats.length})` : ""}
          </Button>
          <button
            type="button"
            onClick={() => setPicking(true)}
            aria-label={`Agent: ${agent.name}. Change agent`}
            className="flex min-h-11 min-w-0 items-center gap-2 rounded-xl border border-border bg-surface px-2 py-1 pr-2.5 text-left transition-colors hover:bg-surface-muted sm:min-h-10"
          >
            <AgentAvatar agent={agent} size="sm" />
            <span className="truncate text-[13px] font-semibold">
              {agent.name}
            </span>
            <ChevronsUpDown
              className="size-3.5 shrink-0 text-muted-foreground"
              aria-hidden="true"
            />
          </button>
          <span className="ml-auto hidden items-center gap-1 text-xs text-muted-foreground md:flex">
            <Quote className="size-3" aria-hidden="true" /> Sources: this
            meeting only
          </span>
        </div>

        <div
          ref={scroller}
          role="log"
          aria-live="polite"
          aria-label="Conversation"
          className="scrollbar-thin min-h-0 flex-1 space-y-4 overflow-y-auto px-3 py-4 sm:px-5"
        >
          {list.isError ? (
            <ErrorState
              compact
              error={list.error}
              onRetry={() => void list.refetch()}
            />
          ) : detail.isError && activeId ? (
            <ErrorState
              compact
              error={detail.error}
              onRetry={() => void detail.refetch()}
            />
          ) : list.isPending || (loadingChat && !pending) ? (
            <div className="space-y-4" aria-hidden="true">
              <Skeleton className="ml-auto h-9 w-2/3 rounded-2xl" />
              <Skeleton className="h-16 w-4/5 rounded-2xl" />
            </div>
          ) : showEmpty ? (
            <div className="flex min-h-full flex-col items-center justify-center py-6 text-center motion-safe:animate-fade-in">
              <AgentCluster />
              <h3 className="mt-4 text-[15px] font-semibold">
                {chats.length === 0 ? "No chats here yet" : "Start a new chat"}
              </h3>
              <p className="mt-1 max-w-sm text-[13px] text-muted-foreground">
                Ask about anything said in this meeting. {agent.name} answers
                only from the transcript and shows the lines it used.
              </p>
              <ul
                aria-label="Questions to start with"
                className="mt-4 flex max-w-xl flex-wrap justify-center gap-2"
              >
                {samples.map((q) => (
                  <li key={q}>
                    <button
                      type="button"
                      onClick={() => void send(q)}
                      className="flex min-h-11 items-center gap-1.5 rounded-full border border-border bg-surface px-3.5 py-1.5 text-left text-[13px] shadow-sm transition-all hover:-translate-y-px hover:border-primary/40 hover:bg-primary-soft/50 hover:shadow-md motion-reduce:transition-none sm:min-h-9"
                    >
                      <MessageSquareText
                        className="size-3.5 shrink-0 text-primary"
                        aria-hidden="true"
                      />
                      {q}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <>
              {messages.map((m) =>
                m.role === "user" ? (
                  <UserBubble key={m.id} text={m.text} time={m.created_at} />
                ) : (
                  <AssistantBubble key={m.id} agent={agent} message={m} />
                ),
              )}
              {pending && (
                <>
                  <UserBubble
                    text={pending.text}
                    failed={pending.error || undefined}
                    onRetry={
                      pending.error ? () => void send(pending.text) : undefined
                    }
                  />
                  {pending.sending && <Typing agent={agent} />}
                </>
              )}
            </>
          )}
        </div>

        <ChatComposer
          sending={pending?.sending === true}
          placeholder={`Ask ${agent.name} about this meeting`}
          onSend={(t) => void send(t)}
        />
      </div>

      <Dialog open={railOpen} onOpenChange={setRailOpen}>
        <SheetContent side="left" width="sm">
          <DialogHeader title="Chats" />
          <div className="min-h-0 flex-1">{rail}</div>
        </SheetContent>
      </Dialog>

      <AgentChooser
        open={picking}
        onOpenChange={setPicking}
        value={currentKey}
        title="Who should answer?"
        description="The agent changes what pi looks for. Answers still come only from this meeting."
        onSelect={(a) => {
          if (activeId) changeAgent.mutate(a.key);
          else setDraftAgent(a.key);
        }}
      />
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(o) => !o && setDeleting(null)}
        title="Delete this chat?"
        description="The questions and answers in it are removed. The meeting itself is not changed."
        confirmLabel="Delete chat"
        pending={remove.isPending}
        onConfirm={() => deleting && remove.mutate(deleting)}
      />
    </div>
  );
}
