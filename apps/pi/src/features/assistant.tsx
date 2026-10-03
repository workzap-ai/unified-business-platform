"use client";

import * as DialogPrimitive from "@radix-ui/react-dialog";
import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight, BookOpen, Send, Sparkles, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import * as React from "react";

import { Button, cn } from "@/components/ui";
import { errorText, get, post } from "@/lib/api";
import { useBusinessKey, useSession } from "@/lib/session";

type Card = {
  title: string;
  href: string | null;
  metrics: Record<string, string | number | null>;
  rows: Record<string, unknown>[];
  bars: { label: string; value: number }[];
  note: string;
};
type Guide = { id: string; title: string; body: string; page: string | null };
type Reply = {
  message: string;
  mode: "ai" | "tools";
  cards: Card[];
  guides: Guide[];
  notice?: string;
};
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
type Turn = { id: number; question?: string; reply?: Reply; error?: string };

const value = (v: unknown) =>
  v === null || v === undefined || v === ""
    ? "—"
    : typeof v === "number"
      ? v.toLocaleString()
      : String(v);

function prompts(ctx: Context | undefined): string[] {
  const list = ["How do I connect my WhatsApp number?"];
  if (ctx?.can.overview) list.unshift("How did this week go?");
  if (ctx?.can.conversations) list.push("Summarize today's chats");
  if (ctx?.can.reports) list.push("Report for the last 30 days");
  if (ctx?.can.overview) list.push("Kitni enquiries aayi?");
  if (ctx?.can.billing) list.push("Mera plan aur usage?");
  return list.slice(0, 5);
}

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

function ResultCard({ card }: { card: Card }) {
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

function GuideLinks({ guides }: { guides: Guide[] }) {
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

function Chat() {
  const key = useBusinessKey();
  const context = useQuery({
    queryKey: key(["assistant", "context"]),
    queryFn: () => get<Context>("/assistant/context"),
    staleTime: 60_000,
  });
  const [turns, setTurns] = React.useState<Turn[]>([]);
  const [text, setText] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const tail = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => {
    tail.current?.scrollIntoView({ block: "nearest" });
  }, [turns, busy]);

  const send = async (question: string) => {
    const q = question.trim();
    if (!q || busy) return;
    setBusy(true);
    setText("");
    const history = turns
      .flatMap((t) => (t.question ? [t.question] : []))
      .slice(-6);
    setTurns((t) => [...t.slice(-30), { id: Date.now(), question: q }]);
    try {
      const reply = await post<Reply>("/assistant/chat", {
        message: q,
        history,
      });
      setTurns((t) => [...t, { id: Date.now() + 1, reply }]);
    } catch (e) {
      setTurns((t) => [...t, { id: Date.now() + 1, error: errorText(e) }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div
        className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-4"
        role="log"
        aria-label="Pi Assistant conversation"
        aria-live="polite"
      >
        {!turns.length ? (
          <div>
            <p className="text-sm text-muted-foreground">
              Ask how to set something up, or about your chats, enquiries and
              reports. I only show what your role can see, and I can&apos;t
              message customers or change settings.
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              {prompts(context.data).map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => void send(p)}
                  className="rounded-full border border-border bg-surface px-3 py-1.5 text-xs text-foreground-secondary hover:bg-surface-muted"
                >
                  {p}
                </button>
              ))}
            </div>
            {context.data?.guides.length ? (
              <details className="mt-5 text-sm">
                <summary className="cursor-pointer font-medium">
                  Setup guides ({context.data.guides.length})
                </summary>
                <ul className="mt-2 space-y-1">
                  {context.data.guides.map((g) => (
                    <li key={g.id}>
                      <button
                        type="button"
                        className="text-left text-accent hover:underline"
                        onClick={() => void send(g.title)}
                      >
                        {g.title}
                      </button>
                    </li>
                  ))}
                </ul>
              </details>
            ) : null}
          </div>
        ) : null}
        {turns.map((turn) =>
          turn.question ? (
            <p
              key={turn.id}
              className="ml-auto max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-tr-sm bg-accent-soft px-3.5 py-2.5 text-sm"
              dir="auto"
            >
              {turn.question}
            </p>
          ) : turn.error ? (
            <p key={turn.id} role="alert" className="text-sm text-danger">
              {turn.error}
            </p>
          ) : turn.reply ? (
            <div key={turn.id} className="space-y-2.5">
              <p className="whitespace-pre-wrap text-sm leading-6" dir="auto">
                {turn.reply.message}
              </p>
              {turn.reply.notice ? (
                <p className="text-[11px] text-muted-foreground">
                  {turn.reply.notice}
                </p>
              ) : null}
              <GuideLinks guides={turn.reply.guides} />
              {turn.reply.cards.map((c, i) => (
                <ResultCard key={`${c.title}-${i}`} card={c} />
              ))}
            </div>
          ) : null,
        )}
        {busy ? (
          <p role="status" className="text-sm text-muted-foreground">
            Checking your workspace…
          </p>
        ) : null}
        <div ref={tail} />
      </div>
      <form
        className="flex items-end gap-2 border-t border-border p-3"
        onSubmit={(e) => {
          e.preventDefault();
          void send(text);
        }}
      >
        <textarea
          aria-label="Ask Pi Assistant"
          className="max-h-32 min-h-11 w-full resize-none rounded-xl border border-border bg-surface px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-ring/30"
          maxLength={2000}
          rows={1}
          placeholder="Ask anything about your Pi…"
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
              void send(text);
            }
          }}
        />
        <Button
          type="submit"
          size="icon"
          aria-label="Send"
          disabled={busy || !text.trim()}
        >
          <Send className="size-4" aria-hidden />
        </Button>
      </form>
      {context.data && !context.data.ai_enabled ? (
        <p className="px-3 pb-2 text-[11px] text-muted-foreground">
          Smart answers are off, so replies come from guides and exact figures.
        </p>
      ) : null}
    </div>
  );
}

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

/** Floating "Ask Pi" button and the side panel, mounted once in the app shell. */
export function PiAssistant() {
  const session = useSession();
  const pathname = usePathname();
  const mobile = useMobile();
  // Above the mobile bottom nav (3.5rem + safe area); bottom-right on desktop.
  const base = mobile ? 76 : GAP;
  const lift = useLift(base);
  const [open, setOpen] = React.useState(false);
  if (!session.data?.business || pathname.startsWith("/setup")) return null;
  return (
    <DialogPrimitive.Root open={open} onOpenChange={setOpen}>
      <DialogPrimitive.Trigger asChild>
        <Button
          data-pi-assistant=""
          aria-label="Open Pi Assistant"
          className="fixed right-4 z-30 rounded-full shadow-md transition-[bottom] duration-150"
          style={{
            bottom: `calc(${base + lift}px + env(safe-area-inset-bottom))`,
          }}
        >
          <Sparkles className="size-4" aria-hidden />
          <span className="hidden sm:inline">Ask Pi</span>
        </Button>
      </DialogPrimitive.Trigger>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-black/30 animate-fade-in" />
        <DialogPrimitive.Content
          className={cn(
            "fixed inset-y-0 right-0 z-50 flex w-full flex-col border-l border-border bg-background shadow-md animate-rise sm:max-w-md",
          )}
        >
          <header className="flex items-start justify-between gap-3 border-b border-border bg-surface px-4 py-3">
            <div>
              <DialogPrimitive.Title className="flex items-center gap-1.5 text-base font-semibold">
                <Sparkles className="size-4 text-accent" aria-hidden />
                Pi Assistant
              </DialogPrimitive.Title>
              <DialogPrimitive.Description className="text-xs text-muted-foreground">
                Setup help and your business at a glance.
              </DialogPrimitive.Description>
            </div>
            <DialogPrimitive.Close asChild>
              <Button variant="ghost" size="icon" aria-label="Close">
                <X className="size-5" aria-hidden />
              </Button>
            </DialogPrimitive.Close>
          </header>
          <Chat />
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
