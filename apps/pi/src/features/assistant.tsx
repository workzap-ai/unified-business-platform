"use client";

import * as DialogPrimitive from "@radix-ui/react-dialog";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowUpRight,
  BookOpen,
  Check,
  CircleAlert,
  Copy,
  History,
  LoaderCircle,
  RefreshCw,
  Send,
  Square,
  SquarePen,
  Trash2,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import * as React from "react";

import { PiFace } from "@/components/brand";
import { Button, cn } from "@/components/ui";
import { ApiError, errorText, get, streamEvents } from "@/lib/api";
import { useBusinessKey, useSession } from "@/lib/session";

import { AssistantText } from "./assistant-text";
import {
  type Card,
  type Guide,
  type Reply,
  type Step,
  type Thread,
  type Turn,
  historyFor,
  newId,
  titleFor,
  useThreads,
  when,
} from "./assistant-history";

type Context = {
  ai_enabled: boolean;
  can: Record<
    | "overview"
    | "conversations"
    | "all_conversations"
    | "reports"
    | "work"
    | "campaigns"
    | "billing"
    | "leads",
    boolean
  >;
  guides: { id: string; title: string; page: string | null }[];
};
type StreamEvent =
  | { type: "thinking" }
  | { type: "step"; tool: string; label: string }
  | { type: "step_done"; tool: string; ok: boolean }
  | { type: "reply"; reply: Reply }
  | { type: "error"; message: string };

const value = (v: unknown) =>
  v === null || v === undefined || v === ""
    ? "—"
    : typeof v === "number"
      ? v.toLocaleString()
      : String(v);

function prompts(ctx: Context | undefined): string[] {
  const list = ["How do I connect my WhatsApp number?"];
  if (ctx?.can.overview) list.unshift("How did this week go?");
  if (ctx?.can.conversations) list.push("Which chats need a reply?");
  if (ctx?.can.reports) list.push("Report for the last 30 days");
  if (ctx?.can.overview) list.push("Kitni enquiries aayi?");
  if (ctx?.can.billing) list.push("Mera plan aur usage?");
  return list.slice(0, 5);
}

// -- the conversation, kept while the panel is closed ------------------------------------

function useAssistant() {
  const session = useSession();
  const { threads, update } = useThreads(
    session.data?.business?.id,
    session.data?.user.id,
  );
  const [activeId, setActiveId] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const controller = React.useRef<AbortController | null>(null);
  const active = threads.find((t) => t.id === activeId) ?? null;

  const patchTurn = React.useCallback(
    (threadId: string, turnId: string, change: (turn: Turn) => Turn) =>
      update((all) =>
        all.map((t) =>
          t.id === threadId
            ? {
                ...t,
                updatedAt: Date.now(),
                turns: t.turns.map((x) => (x.id === turnId ? change(x) : x)),
              }
            : t,
        ),
      ),
    [update],
  );

  const send = React.useCallback(
    async (question: string) => {
      const q = question.trim();
      if (!q || busy) return;
      const threadId = active?.id ?? newId();
      const history = historyFor(active?.turns ?? []);
      const turnId = newId();
      const asked: Turn = { id: newId(), question: q };
      const answer: Turn = { id: turnId, steps: [] };
      const now = Date.now();
      update((all) =>
        all.some((t) => t.id === threadId)
          ? all.map((t) =>
              t.id === threadId
                ? { ...t, updatedAt: now, turns: [...t.turns, asked, answer] }
                : t,
            )
          : [
              {
                id: threadId,
                title: titleFor(q),
                createdAt: now,
                updatedAt: now,
                turns: [asked, answer],
              } satisfies Thread,
              ...all,
            ],
      );
      setActiveId(threadId);
      setBusy(true);
      const abort = new AbortController();
      controller.current = abort;
      const timer = setTimeout(() => abort.abort("timeout"), 100_000);
      let replied = false;
      try {
        await streamEvents<StreamEvent>(
          "/assistant/chat/stream",
          { message: q, history },
          (event) => {
            if (event.type === "step")
              patchTurn(threadId, turnId, (t) => ({
                ...t,
                steps: [
                  ...(t.steps ?? []),
                  {
                    tool: event.tool,
                    label: event.label,
                    done: false,
                    ok: true,
                  },
                ],
              }));
            else if (event.type === "step_done")
              patchTurn(threadId, turnId, (t) => {
                const steps = [...(t.steps ?? [])];
                const i = steps.findLastIndex(
                  (s) => s.tool === event.tool && !s.done,
                );
                if (i >= 0)
                  steps[i] = { ...steps[i], done: true, ok: event.ok };
                return { ...t, steps };
              });
            else if (event.type === "reply") {
              replied = true;
              patchTurn(threadId, turnId, (t) => ({
                ...t,
                reply: event.reply,
              }));
            } else if (event.type === "error") {
              replied = true;
              patchTurn(threadId, turnId, (t) => ({
                ...t,
                error: event.message,
              }));
            }
          },
          abort.signal,
        );
        if (!replied)
          throw new ApiError(
            0,
            "CUT_OFF",
            "The answer was cut off. Please try again.",
          );
      } catch (error) {
        const stopped =
          abort.signal.aborted && abort.signal.reason !== "timeout";
        patchTurn(threadId, turnId, (t) =>
          stopped
            ? { ...t, stopped: true }
            : {
                ...t,
                error: abort.signal.aborted
                  ? "That took too long. Please try a narrower question."
                  : errorText(error),
              },
        );
      } finally {
        clearTimeout(timer);
        controller.current = null;
        setBusy(false);
      }
    },
    [active, busy, patchTurn, update],
  );

  const stop = React.useCallback(
    () => controller.current?.abort("stopped"),
    [],
  );
  const startNew = React.useCallback(() => {
    if (!busy) setActiveId(null);
  }, [busy]);
  const open = React.useCallback(
    (id: string) => {
      if (!busy) setActiveId(id);
    },
    [busy],
  );
  const remove = React.useCallback(
    (id: string) => {
      update((all) => all.filter((t) => t.id !== id));
      setActiveId((current) => (current === id ? null : current));
    },
    [update],
  );
  const clear = React.useCallback(() => {
    update(() => []);
    setActiveId(null);
  }, [update]);

  return { threads, active, busy, send, stop, startNew, open, remove, clear };
}

type AssistantState = ReturnType<typeof useAssistant>;

// -- pieces -------------------------------------------------------------------------------

function Bars({ bars }: { bars: Card["bars"] }) {
  if (!bars.length) return null;
  const max = Math.max(1, ...bars.map((b) => b.value));
  return (
    <div>
      <div
        className="flex h-16 items-end gap-0.5"
        role="img"
        aria-label={bars.map((b) => `${b.label}: ${b.value}`).join(", ")}
      >
        {bars.map((b) => (
          <span
            key={b.label}
            title={`${b.label}: ${b.value}`}
            className="min-w-0 flex-1 rounded-t-[3px] bg-accent"
            style={{ height: `${Math.max(4, (b.value / max) * 100)}%` }}
          />
        ))}
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-muted-foreground">
        <span>{bars[0].label}</span>
        <span>{bars[bars.length - 1].label}</span>
      </div>
    </div>
  );
}

function ResultCard({
  card,
  onNavigate,
}: {
  card: Card;
  onNavigate: () => void;
}) {
  const columns = Array.from(
    new Set(card.rows.flatMap((row) => Object.keys(row))),
  );
  return (
    <section className="rounded-xl border border-border bg-surface p-3">
      <header className="mb-2 flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">{card.title}</h3>
        {card.href ? (
          <Link
            href={card.href}
            onClick={onNavigate}
            className="inline-flex items-center gap-0.5 text-xs font-medium text-accent"
          >
            Open
            <ArrowUpRight size={12} aria-hidden />
          </Link>
        ) : null}
      </header>
      {Object.keys(card.metrics).length ? (
        <dl className="mb-2 grid grid-cols-2 gap-2">
          {Object.entries(card.metrics).map(([k, v]) => (
            <div key={k} className="rounded-lg bg-surface-muted px-2.5 py-1.5">
              <dt className="truncate text-[11px] text-muted-foreground">
                {k}
              </dt>
              <dd className="text-base font-semibold tabular-nums">
                {value(v)}
              </dd>
            </div>
          ))}
        </dl>
      ) : null}
      <Bars bars={card.bars} />
      {card.rows.length ? (
        <div className="mt-2 overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr>
                {columns.map((c) => (
                  <th
                    key={c}
                    scope="col"
                    className="px-1.5 py-1 text-left font-medium capitalize text-muted-foreground"
                  >
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {card.rows.map((row, i) => (
                <tr key={i} className="border-t border-border">
                  {columns.map((c) => (
                    <td key={c} className="px-1.5 py-1 align-top" dir="auto">
                      {typeof row[c] === "boolean"
                        ? row[c]
                          ? "Done"
                          : "To do"
                        : value(row[c])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {card.note ? (
        <p className="mt-2 text-[11px] text-muted-foreground">{card.note}</p>
      ) : null}
    </section>
  );
}

function GuideLinks({
  guides,
  onNavigate,
}: {
  guides: Guide[];
  onNavigate: () => void;
}) {
  if (!guides.length) return null;
  return (
    <ul className="space-y-1.5" aria-label="Related guides">
      {guides.map((g) => (
        <li
          key={g.id}
          className="flex items-center justify-between gap-2 rounded-lg bg-accent-soft px-3 py-2 text-sm"
        >
          <span className="flex min-w-0 items-center gap-1.5 text-accent-soft-foreground">
            <BookOpen size={14} aria-hidden />
            <span className="truncate">{g.title}</span>
          </span>
          {g.page ? (
            <Link
              href={g.page}
              onClick={onNavigate}
              className="shrink-0 text-xs font-medium text-accent"
            >
              Go there
            </Link>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

/** The real steps pi is taking right now (or took), with their outcome. */
function Steps({ steps, live }: { steps: Step[]; live: boolean }) {
  if (!steps.length) return null;
  return (
    <ul className="space-y-1" aria-label="What pi checked">
      {steps.map((s, i) => (
        <li
          key={`${s.tool}-${i}`}
          className="flex items-center gap-1.5 text-xs text-muted-foreground"
        >
          {!s.done && live ? (
            <LoaderCircle
              className="size-3.5 animate-spin text-accent"
              aria-hidden
            />
          ) : s.ok ? (
            <Check className="size-3.5 text-success" aria-hidden />
          ) : (
            <CircleAlert className="size-3.5 text-warning" aria-hidden />
          )}
          <span>
            {s.label}
            {s.done && !s.ok ? " · couldn't check this" : ""}
          </span>
        </li>
      ))}
    </ul>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = React.useState(false);
  return (
    <button
      type="button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        } catch {
          // clipboard blocked: nothing to do
        }
      }}
      className="inline-flex h-8 items-center gap-1 rounded-md px-2 text-xs text-muted-foreground hover:bg-surface-muted hover:text-foreground"
    >
      {copied ? (
        <Check className="size-3.5" aria-hidden />
      ) : (
        <Copy className="size-3.5" aria-hidden />
      )}
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

function Chips({
  items,
  onPick,
  disabled,
}: {
  items: string[];
  onPick: (q: string) => void;
  disabled?: boolean;
}) {
  if (!items.length) return null;
  return (
    <div className="flex flex-wrap gap-2">
      {items.map((p) => (
        <button
          key={p}
          type="button"
          disabled={disabled}
          onClick={() => onPick(p)}
          dir="auto"
          className="rounded-full border border-border bg-surface px-3 py-1.5 text-left text-xs text-foreground-secondary hover:border-accent hover:bg-accent-soft hover:text-accent-soft-foreground disabled:opacity-50"
        >
          {p}
        </button>
      ))}
    </div>
  );
}

// -- views --------------------------------------------------------------------------------

function Welcome({
  context,
  onPick,
}: {
  context: Context | undefined;
  onPick: (q: string) => void;
}) {
  return (
    <div>
      <div className="flex items-start gap-3">
        <PiFace expression="greet" size={44} />
        <div className="min-w-0 text-sm">
          <p className="font-semibold">Hi, I&apos;m pi, an AI assistant.</p>
          <p className="mt-1 text-muted-foreground">
            Ask how to set something up, or about your chats, enquiries and
            reports. I remember this chat, and I only show what your role can
            see. I can&apos;t message customers or change settings.
          </p>
        </div>
      </div>
      <div className="mt-4">
        <Chips items={prompts(context)} onPick={onPick} />
      </div>
      {context?.guides.length ? (
        <details className="mt-5 text-sm">
          <summary className="cursor-pointer font-medium">
            Setup guides ({context.guides.length})
          </summary>
          <ul className="mt-2 space-y-1">
            {context.guides.map((g) => (
              <li key={g.id}>
                <button
                  type="button"
                  className="text-left text-accent hover:underline"
                  onClick={() => onPick(g.title)}
                >
                  {g.title}
                </button>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}

function Conversation({
  state,
  context,
  onNavigate,
}: {
  state: AssistantState;
  context: Context | undefined;
  onNavigate: () => void;
}) {
  const { active, busy, send } = state;
  const [text, setText] = React.useState("");
  const input = React.useRef<HTMLTextAreaElement>(null);
  const tail = React.useRef<HTMLDivElement>(null);
  const turns = active?.turns ?? [];
  const last = turns[turns.length - 1];
  React.useEffect(() => {
    tail.current?.scrollIntoView({ block: "nearest" });
  }, [turns.length, last?.steps?.length, last?.reply, busy]);
  React.useEffect(() => {
    const box = input.current;
    if (!box) return;
    box.style.height = "auto";
    box.style.height = `${Math.min(box.scrollHeight, 128)}px`;
  }, [text]);

  const ask = (q: string) => {
    if (!q.trim() || busy) return;
    setText("");
    void send(q);
  };
  const lastQuestion = [...turns].reverse().find((t) => t.question)?.question;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div
        className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-4"
        role="log"
        aria-label="Conversation with pi"
        aria-live="polite"
      >
        {!turns.length ? <Welcome context={context} onPick={ask} /> : null}
        {turns.map((turn, index) => {
          const isLast = index === turns.length - 1;
          if (turn.question)
            return (
              <p
                key={turn.id}
                className="ml-auto max-w-[85%] whitespace-pre-wrap break-words rounded-2xl rounded-tr-sm bg-accent-soft px-3.5 py-2.5 text-sm"
                dir="auto"
              >
                {turn.question}
              </p>
            );
          const live = busy && isLast;
          const steps = turn.steps ?? [];
          if (turn.reply)
            return (
              <div key={turn.id} className="flex items-start gap-2.5">
                <PiFace
                  expression={
                    turn.reply.cards.length || turn.reply.guides.length
                      ? "rest"
                      : "unsure"
                  }
                  size={32}
                />
                <div className="min-w-0 flex-1 space-y-2.5">
                  {steps.length ? (
                    <details className="text-xs text-muted-foreground">
                      <summary className="cursor-pointer select-none">
                        Checked {steps.length}{" "}
                        {steps.length === 1 ? "source" : "sources"}
                      </summary>
                      <div className="mt-1.5">
                        <Steps steps={steps} live={false} />
                      </div>
                    </details>
                  ) : null}
                  <AssistantText
                    text={turn.reply.message}
                    onNavigate={onNavigate}
                  />
                  {turn.reply.notice ? (
                    <p className="text-[11px] text-muted-foreground">
                      {turn.reply.notice}
                    </p>
                  ) : null}
                  <GuideLinks
                    guides={turn.reply.guides}
                    onNavigate={onNavigate}
                  />
                  {turn.reply.cards.map((c, i) => (
                    <ResultCard
                      key={`${c.title}-${i}`}
                      card={c}
                      onNavigate={onNavigate}
                    />
                  ))}
                  <div className="-ms-2 flex items-center">
                    <CopyButton text={turn.reply.message} />
                  </div>
                  {isLast && !busy ? (
                    <Chips
                      items={turn.reply.follow_ups ?? []}
                      onPick={ask}
                      disabled={busy}
                    />
                  ) : null}
                </div>
              </div>
            );
          if (turn.error || turn.stopped)
            return (
              <div key={turn.id} className="flex items-start gap-2.5">
                <PiFace expression="sorry" size={32} />
                <div className="min-w-0 flex-1 space-y-2 pt-1">
                  <Steps steps={steps} live={false} />
                  {turn.stopped ? (
                    <p className="text-sm text-muted-foreground">
                      You stopped this answer.
                    </p>
                  ) : (
                    <p role="alert" className="text-sm text-danger">
                      I couldn&apos;t finish that. {turn.error}
                    </p>
                  )}
                  {isLast && lastQuestion && !busy ? (
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => ask(lastQuestion)}
                    >
                      <RefreshCw className="size-3.5" aria-hidden />
                      Try again
                    </Button>
                  ) : null}
                </div>
              </div>
            );
          return live ? (
            <div
              key={turn.id}
              role="status"
              className="flex items-start gap-2.5"
            >
              <PiFace expression="think" size={32} />
              <div className="min-w-0 flex-1 space-y-1.5 pt-1">
                <p className="text-sm text-muted-foreground">
                  {steps.length ? "pi is working on it…" : "pi is thinking…"}
                </p>
                <Steps steps={steps} live />
              </div>
            </div>
          ) : (
            <div key={turn.id} className="flex items-start gap-2.5">
              <PiFace expression="sorry" size={32} />
              <p className="pt-1 text-sm text-muted-foreground">
                This answer didn&apos;t finish.
              </p>
            </div>
          );
        })}
        <div ref={tail} />
      </div>
      <form
        className="flex items-end gap-2 border-t border-border p-3"
        onSubmit={(e) => {
          e.preventDefault();
          ask(text);
        }}
      >
        <textarea
          ref={input}
          aria-label="Ask pi"
          className="max-h-32 min-h-11 w-full resize-none rounded-xl border border-border bg-surface px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-ring/30"
          maxLength={2000}
          rows={1}
          placeholder={turns.length ? "Ask a follow-up…" : "Ask pi anything…"}
          value={text}
          dir="auto"
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (
              e.key === "Enter" &&
              !e.shiftKey &&
              !e.nativeEvent.isComposing
            ) {
              e.preventDefault();
              ask(text);
            }
          }}
        />
        {busy ? (
          <Button
            type="button"
            size="icon"
            variant="secondary"
            aria-label="Stop the answer"
            onClick={state.stop}
          >
            <Square className="size-3.5 fill-current" aria-hidden />
          </Button>
        ) : (
          <Button
            type="submit"
            size="icon"
            aria-label="Send"
            disabled={!text.trim()}
          >
            <Send className="size-4" aria-hidden />
          </Button>
        )}
      </form>
      {context && !context.ai_enabled ? (
        <p className="px-3 pb-2 text-[11px] text-muted-foreground">
          Smart answers are off, so replies come from guides and exact figures.
        </p>
      ) : null}
    </div>
  );
}

function HistoryList({
  state,
  onOpen,
}: {
  state: AssistantState;
  onOpen: () => void;
}) {
  const [confirming, setConfirming] = React.useState(false);
  if (!state.threads.length)
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-2 p-6 text-center">
        <PiFace expression="rest" size={44} />
        <p className="text-sm font-medium">No chats yet</p>
        <p className="text-xs text-muted-foreground">
          Your chats with pi are kept on this device for you only.
        </p>
      </div>
    );
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <ul className="min-h-0 flex-1 divide-y divide-border overflow-y-auto">
        {state.threads.map((t) => {
          const questions = t.turns.filter((x) => x.question).length;
          return (
            <li key={t.id} className="flex items-center gap-1 pe-2">
              <button
                type="button"
                disabled={state.busy}
                onClick={() => {
                  state.open(t.id);
                  onOpen();
                }}
                className={cn(
                  "min-w-0 flex-1 px-4 py-3 text-left hover:bg-surface-muted disabled:opacity-60",
                  state.active?.id === t.id && "bg-accent-soft",
                )}
              >
                <span className="block truncate text-sm font-medium" dir="auto">
                  {t.title}
                </span>
                <span className="block text-xs text-muted-foreground">
                  {when(t.updatedAt)} · {questions}{" "}
                  {questions === 1 ? "question" : "questions"}
                </span>
              </button>
              <Button
                variant="ghost"
                size="icon"
                aria-label={`Delete chat: ${t.title}`}
                disabled={state.busy && state.active?.id === t.id}
                onClick={() => state.remove(t.id)}
              >
                <Trash2 className="size-4" aria-hidden />
              </Button>
            </li>
          );
        })}
      </ul>
      <div className="flex items-center justify-between gap-2 border-t border-border p-3 text-xs text-muted-foreground">
        <span>Kept on this device, for you only.</span>
        {confirming ? (
          <span className="flex gap-1.5">
            <Button
              size="sm"
              variant="secondary"
              onClick={() => setConfirming(false)}
            >
              Keep
            </Button>
            <Button
              size="sm"
              onClick={() => {
                state.clear();
                setConfirming(false);
              }}
            >
              Delete all
            </Button>
          </span>
        ) : (
          <Button
            size="sm"
            variant="ghost"
            disabled={state.busy}
            onClick={() => setConfirming(true)}
          >
            Clear history
          </Button>
        )}
      </div>
    </div>
  );
}

// -- launcher and panel -------------------------------------------------------------------

const GAP = 20;
const INTERACTIVE =
  "button, a[href], input, select, textarea, [role='button'], [role='link']";

/** Raise the launcher above any control under it (sticky save bars, wizard buttons). */
function useLift(base: number) {
  const [lift, setLift] = React.useState(0);
  React.useEffect(() => {
    let frame = 0;
    const measure = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const self = document.querySelector<HTMLElement>("[data-pi-assistant]");
        if (!self) return;
        const own = self.getBoundingClientRect();
        const bottom = window.innerHeight - base;
        let highest = Infinity;
        document.querySelectorAll<HTMLElement>(INTERACTIVE).forEach((node) => {
          if (
            node.closest("[data-pi-assistant]") ||
            node.closest("nav[aria-label='Main']")
          )
            return;
          const r = node.getBoundingClientRect();
          if (!r.width || !r.height) return;
          if (
            r.right < own.left - 8 ||
            r.left > own.right + 8 ||
            r.bottom < bottom - own.height - 8 ||
            r.top > bottom + 8
          )
            return;
          highest = Math.min(highest, r.top);
        });
        const next =
          highest === Infinity
            ? 0
            : Math.max(0, window.innerHeight - highest + 12 - base);
        setLift((current) => (Math.abs(current - next) < 1 ? current : next));
      });
    };
    measure();
    const observer = new MutationObserver(measure);
    observer.observe(document.body, { childList: true, subtree: true });
    window.addEventListener("scroll", measure, true);
    window.addEventListener("resize", measure);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      window.removeEventListener("scroll", measure, true);
      window.removeEventListener("resize", measure);
    };
  }, [base]);
  return lift;
}

function useMobile() {
  const [mobile, setMobile] = React.useState(false);
  React.useEffect(() => {
    const query = window.matchMedia("(max-width: 767px)");
    const update = () => setMobile(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  return mobile;
}

/** Floating "Ask pi" button and the side panel, mounted once in the app shell. */
export function PiAssistant() {
  const session = useSession();
  const pathname = usePathname();
  const mobile = useMobile();
  const key = useBusinessKey();
  // Above the mobile bottom nav (3.5rem + safe area); bottom-right on desktop.
  const base = mobile ? 76 : GAP;
  const lift = useLift(base);
  const [open, setOpen] = React.useState(false);
  const [view, setView] = React.useState<"chat" | "history">("chat");
  const state = useAssistant();
  const context = useQuery({
    queryKey: key(["assistant", "context"]),
    queryFn: () => get<Context>("/assistant/context"),
    staleTime: 60_000,
    enabled: open && Boolean(session.data?.business),
  });
  // Following a link closes the panel on phones, where it covers the page.
  const onNavigate = React.useCallback(() => {
    if (mobile) setOpen(false);
  }, [mobile]);
  if (!session.data?.business || pathname.startsWith("/setup")) return null;
  return (
    <DialogPrimitive.Root open={open} onOpenChange={setOpen}>
      <DialogPrimitive.Trigger asChild>
        <button
          type="button"
          data-pi-assistant=""
          aria-label="Ask pi, the AI assistant"
          className="fixed right-4 z-30 inline-flex items-center gap-2 rounded-full border border-border bg-surface py-1.5 pl-1.5 pr-1.5 text-sm font-semibold text-foreground shadow-md transition-[bottom,box-shadow] duration-150 hover:shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 sm:pr-4"
          style={{
            bottom: `calc(${base + lift}px + env(safe-area-inset-bottom))`,
          }}
        >
          <PiFace expression={state.busy ? "think" : "rest"} size={36} />
          <span className="hidden sm:inline">
            {state.busy ? "pi is working…" : "Ask pi"}
          </span>
        </button>
      </DialogPrimitive.Trigger>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-black/30 animate-fade-in" />
        <DialogPrimitive.Content
          className={cn(
            "fixed inset-y-0 right-0 z-50 flex w-full flex-col border-l border-border bg-background shadow-md animate-rise sm:max-w-md",
          )}
        >
          <header className="flex items-center justify-between gap-2 border-b border-border bg-surface px-3 py-3 sm:px-4">
            <div className="flex min-w-0 items-center gap-3">
              {view === "history" ? (
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label="Back to the chat"
                  onClick={() => setView("chat")}
                >
                  <ArrowLeft className="size-5" aria-hidden />
                </Button>
              ) : (
                <PiFace expression="rest" size={40} />
              )}
              <div className="min-w-0">
                <DialogPrimitive.Title className="truncate text-base font-semibold">
                  {view === "history" ? "Your chats with pi" : "pi"}
                </DialogPrimitive.Title>
                <DialogPrimitive.Description className="truncate text-xs text-muted-foreground">
                  {view === "history"
                    ? `${state.threads.length} saved`
                    : (state.active?.title ?? "AI assistant · by Workzap")}
                </DialogPrimitive.Description>
              </div>
            </div>
            <div className="flex shrink-0 items-center">
              {view === "chat" ? (
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label="Chat history"
                  title="Chat history"
                  onClick={() => setView("history")}
                >
                  <History className="size-5" aria-hidden />
                </Button>
              ) : null}
              <Button
                variant="ghost"
                size="icon"
                aria-label="New chat"
                title="New chat"
                disabled={state.busy}
                onClick={() => {
                  state.startNew();
                  setView("chat");
                }}
              >
                <SquarePen className="size-5" aria-hidden />
              </Button>
              <DialogPrimitive.Close asChild>
                <Button variant="ghost" size="icon" aria-label="Close">
                  <X className="size-5" aria-hidden />
                </Button>
              </DialogPrimitive.Close>
            </div>
          </header>
          {view === "history" ? (
            <HistoryList state={state} onOpen={() => setView("chat")} />
          ) : (
            <Conversation
              state={state}
              context={context.data}
              onNavigate={onNavigate}
            />
          )}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
