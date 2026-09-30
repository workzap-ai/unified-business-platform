"use client";

import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import * as Dialog from "@radix-ui/react-dialog";
import {
  Activity,
  Bot,
  Check,
  ChevronRight,
  FileUp,
  Loader2,
  MessageSquare,
  RefreshCw,
  Send,
  ShieldCheck,
} from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { SheetContent } from "@/components/ui/overlays";
import { useSession } from "@/features/auth/session-provider";
import { useScopedQuery } from "@/hooks/use-scoped";
import { isDemo } from "@/lib/data-mode";
import { ApiError, errorMessage } from "@/services/api-client";
import {
  agentService,
  type AgentContext,
  type Proposal,
  type Reply,
  type Signal,
  type ToolResult,
} from "./service";

type Turn = { id: number; user?: string; reply?: Reply };
type AgentState = {
  context?: AgentContext;
  turns: Turn[];
  busy: boolean;
  error: string;
  open: boolean;
  setOpen: (open: boolean) => void;
  send: (message: string) => Promise<void>;
  upload: (file: File, purpose: "summary" | "employees") => Promise<void>;
  addReply: (reply: Reply) => void;
  setError: (error: string) => void;
};
const AgentContextValue = createContext<AgentState | null>(null);
const fieldClass =
  "w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/30";
const label = (value: string) =>
  value.replaceAll("_", " ").replaceAll(".", " · ");
// API timestamps look like "2026-09-30 10:24:00.115323+00:00" (space, microseconds).
const isoDateTime = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/;
const formatDateTime = (value: string) => {
  const parsed = new Date(
    value.replace(" ", "T").replace(/(\.\d{3})\d+/, "$1"),
  );
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
};
const display = (value: unknown): string =>
  value === null || value === undefined || value === ""
    ? "—"
    : typeof value === "object"
      ? JSON.stringify(value)
      : typeof value === "string" && isoDateTime.test(value)
        ? formatDateTime(value)
        : String(value);
// /context, /chat and /documents never answer 404 for a record: a 404 there means the
// API process predates Agent Beta (routes not loaded), so say that instead.
const serviceError = (error: unknown) =>
  error instanceof ApiError && error.status === 404
    ? "Pi Agent Beta isn't running on this server yet. Restart the API after applying database migrations (alembic upgrade head), then reload this page."
    : errorMessage(error);
const emptyReply = (message: string): Reply => ({
  message,
  results: [],
  proposals: [],
  signals: [],
  mode: "tools",
});
// Defense in depth: navigation is limited to registered application paths, never model URLs.
const safeRoutes = new Set([
  "/customers",
  "/catalog",
  "/inventory",
  "/sales",
  "/quotes",
  "/orders",
  "/billing",
  "/finance",
  "/hr",
  "/settings/members",
  "/settings/integrations",
  "/workspace-agent",
  "/pi/inbox",
  "/pi/handoffs",
  "/pi/whatsapp",
]);
const severityStyle: Record<Signal["severity"], string> = {
  critical: "border-danger/30 bg-danger-soft text-danger",
  warning: "border-warning/30 bg-warning-soft text-warning",
  info: "border-info/30 bg-info-soft text-info",
};

function useAgent() {
  const value = useContext(AgentContextValue);
  if (!value) throw new Error("WorkspaceAgentProvider is required");
  return value;
}

function useAgentIdentity() {
  const { session } = useSession();
  return [session?.user.id, ...(session?.permissions ?? []).toSorted()].join(
    ":",
  );
}

export function WorkspaceAgentProvider({ children }: { children: ReactNode }) {
  const { session, scopeKey } = useSession();
  const identity = [
    ...scopeKey,
    session?.user.id,
    ...(session?.permissions ?? []).toSorted(),
  ].join(":");
  return <AgentSession key={identity}>{children}</AgentSession>;
}

function AgentSession({ children }: { children: ReactNode }) {
  const identity = useAgentIdentity();
  const context = useScopedQuery(
    ["workspace-agent", "context", identity],
    agentService.context,
    { enabled: !isDemo, retry: false },
  );
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const mounted = useRef(true);
  const pathname = usePathname();
  const router = useRouter();
  const client = useQueryClient();
  const { scopeKey } = useSession();
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      controller.current?.abort();
    };
  }, []);
  const addReply = (reply: Reply) => {
    if (!mounted.current) return;
    setTurns((t) => [...t.slice(-39), { id: Date.now(), reply }]);
    if (reply.proposals.length)
      void client.invalidateQueries({
        queryKey: [...scopeKey, "workspace-agent", "proposals"],
      });
  };
  const run = async (
    user: string,
    request: (signal: AbortSignal) => Promise<Reply>,
  ) => {
    if (controller.current || isDemo) return;
    const active = new AbortController();
    controller.current = active;
    setBusy(true);
    setError("");
    setTurns((t) => [...t.slice(-39), { id: Date.now(), user }]);
    try {
      const reply = await request(active.signal);
      if (!mounted.current) return;
      addReply(reply);
      await client.invalidateQueries({
        queryKey: [...scopeKey, "workspace-agent", "proposals"],
      });
      if (reply.navigate && safeRoutes.has(reply.navigate))
        router.push(reply.navigate);
    } catch (e) {
      if (mounted.current && !active.signal.aborted) setError(serviceError(e));
    } finally {
      if (mounted.current) setBusy(false);
      controller.current = null;
    }
  };
  return (
    <AgentContextValue.Provider
      value={{
        context: context.data,
        turns,
        busy,
        open,
        setOpen,
        error: error || (context.error ? serviceError(context.error) : ""),
        setError,
        addReply,
        send: (message) =>
          run(message, (signal) =>
            agentService.chat(
              message,
              turns.flatMap((t) => (t.user ? [t.user] : [])).slice(-8),
              pathname,
              signal,
            ),
          ),
        upload: (file, purpose) =>
          run(
            `${purpose === "employees" ? "Import employees" : "Summarize document"}: ${file.name}`,
            (signal) => agentService.document(file, purpose, signal),
          ),
      }}
    >
      {children}
      <AgentLauncher />
    </AgentContextValue.Provider>
  );
}

function AgentLauncher() {
  const { open, setOpen } = useAgent();
  const pathname = usePathname();
  if (pathname === "/workspace-agent") return null;
  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <Button
          className="fixed right-5 bottom-5 z-40 gap-2 rounded-full shadow-lg"
          aria-label="Open Pi Agent Beta"
        >
          <Bot className="size-4" />
          <span className="hidden sm:inline">Pi Agent</span>
          <span className="rounded-full bg-white/15 px-1.5 text-[10px]">
            BETA
          </span>
        </Button>
      </Dialog.Trigger>
      <SheetContent
        side="right"
        width="xl"
        className="flex w-full flex-col p-0 sm:max-w-2xl"
      >
        <Dialog.Title className="sr-only">Pi Agent Beta</Dialog.Title>
        <Dialog.Description className="sr-only">
          Manage authorized workspace work, records and employee imports.
        </Dialog.Description>
        <AgentPanel compact />
      </SheetContent>
    </Dialog.Root>
  );
}

export function WorkspaceAgentPage() {
  return (
    <div className="mx-auto max-w-7xl p-4 sm:p-6">
      <AgentPanel />
    </div>
  );
}

function AgentPanel({ compact = false }: { compact?: boolean }) {
  const agent = useAgent();
  const identity = useAgentIdentity();
  const { session } = useSession();
  const [tab, setTab] = useState<"chat" | "monitor" | "tasks" | "drafts">(
    "chat",
  );
  const pending = useScopedQuery(
    ["workspace-agent", "proposals", identity],
    agentService.pending,
    { enabled: !isDemo, retry: false },
  );
  return (
    <section
      className={`flex min-h-0 flex-col ${compact ? "h-full" : "min-h-[calc(100dvh-8rem)] rounded-2xl border border-border bg-surface shadow-sm"}`}
      aria-label="Workspace assistant"
    >
      <header className="border-b border-border p-5 pr-12">
        <div className="flex items-center gap-3">
          <div className="flex size-11 items-center justify-center rounded-xl bg-primary/10 text-primary">
            <Bot className="size-6" />
          </div>
          <div>
            <h1 className="text-lg font-semibold">
              Pi Agent{" "}
              <span className="ml-1 rounded bg-primary/10 px-1.5 py-0.5 text-xs text-primary">
                Beta
              </span>
            </h1>
            <p className="text-xs text-muted-foreground">
              Owner OS · {session?.tenant?.name} · {session?.environment?.name}
            </p>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-2 text-xs">
          <ShieldCheck className="size-3.5 text-success" />
          <span>{agent.context?.name ?? session?.user.display_name}</span>
          <span className="text-muted-foreground">
            {(agent.context?.roles ?? session?.roles ?? []).join(", ")}
          </span>
          <span className="ml-auto rounded-full border border-border px-2 py-1">
            {isDemo
              ? "Demo preview"
              : agent.context?.ai_enabled
                ? "AI + workspace tools"
                : "Workspace tools"}
          </span>
        </div>
      </header>
      <div
        className="flex gap-1 border-b border-border px-4 py-2"
        role="tablist"
        aria-label="Agent views"
      >
        {(["chat", "monitor", "tasks", "drafts"] as const).map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={tab === t}
            onClick={() => setTab(t)}
            className={`rounded-lg px-4 py-2 text-sm capitalize ${tab === t ? "bg-primary/10 font-medium text-primary" : "text-muted-foreground hover:bg-surface-muted"}`}
          >
            {t}
            {t === "drafts" &&
              !!pending.data?.length &&
              ` (${pending.data.length})`}
          </button>
        ))}
        {!compact && (
          <span className="ml-auto hidden self-center text-xs text-muted-foreground md:inline">
            Operations · HR · Finance · CRM · WhatsApp
          </span>
        )}
      </div>
      {isDemo ? (
        <div className="m-5 rounded-xl border border-dashed border-border p-6">
          <h2 className="font-medium">Ready for your live workspace</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            Agent Beta uses your real permissions and records. Sign in to a live
            workspace to chat, manage tasks or preview an employee import. No
            business actions run in this demo.
          </p>
          <a
            className="mt-4 inline-block text-sm text-primary underline"
            href="/templates/agent-employees-10.csv"
            download
          >
            Download 10-employee CSV example
          </a>
        </div>
      ) : (
        <>
          {agent.error && (
            <div
              role="alert"
              className="mx-5 mt-4 rounded-lg border border-danger/30 bg-danger/5 p-3 text-sm"
            >
              {agent.error}
            </div>
          )}
          {tab === "chat" ? (
            <>
              <ChatHistory />
              <Composer />
            </>
          ) : (
            <div className="min-h-0 flex-1 overflow-y-auto p-5">
              {tab === "monitor" ? (
                <MonitorBoard onAsk={() => setTab("chat")} />
              ) : tab === "tasks" ? (
                <TaskBoard />
              ) : (
                <>
                  <p className="mb-4 text-sm text-muted-foreground">
                    Only your drafts are shown. Each expires after 30 minutes.
                    Permissions are checked again when you confirm.
                  </p>
                  {pending.isPending ? (
                    <p>Loading drafts…</p>
                  ) : pending.error ? (
                    <p role="alert">{errorMessage(pending.error)}</p>
                  ) : pending.data?.length ? (
                    pending.data.map((p) => (
                      <ProposalCard key={p.id} proposal={p} />
                    ))
                  ) : (
                    <p className="text-sm text-muted-foreground">
                      No pending drafts.
                    </p>
                  )}
                </>
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}

function ChatHistory() {
  const agent = useAgent();
  const tail = useRef<HTMLDivElement>(null);
  useEffect(() => {
    tail.current?.scrollIntoView({ block: "nearest" });
  }, [agent.turns, agent.busy]);
  return (
    <div
      className="min-h-0 flex-1 space-y-5 overflow-y-auto p-5"
      role="log"
      aria-label="Agent conversation"
      aria-live="polite"
    >
      {!agent.turns.length && (
        <div className="py-6">
          <MessageSquare className="mb-4 size-8 text-primary" />
          <h2 className="text-xl font-semibold">What needs doing today?</h2>
          <p className="mt-2 max-w-lg text-sm leading-6 text-muted-foreground">
            Ask in your language. I can monitor your workspace, summarize CRM
            and WhatsApp conversations, suggest next steps, look up permitted
            records, prepare employee imports and manage your team’s tasks.
          </p>
          <div className="mt-5 flex flex-wrap gap-2">
            {starterPrompts(agent.context?.permissions ?? []).map((prompt) => (
              <Button
                key={prompt}
                variant="secondary"
                size="sm"
                disabled={agent.busy}
                onClick={() => void agent.send(prompt)}
              >
                {prompt}
                <ChevronRight className="ml-1 size-3" />
              </Button>
            ))}
          </div>
          <p className="mt-4 text-xs text-muted-foreground">
            Changes appear as drafts for your review. Chat clears on sign-out,
            workspace or role changes.
          </p>
          <QuickCreate />
        </div>
      )}
      {agent.turns.map((turn) => (
        <div key={turn.id}>
          {turn.user ? (
            <div
              className="ml-auto max-w-[90%] whitespace-pre-wrap rounded-2xl rounded-tr-sm bg-primary/10 px-4 py-3 text-sm"
              dir="auto"
            >
              {turn.user}
            </div>
          ) : (
            turn.reply && (
              <div className="space-y-3">
                <div className="flex items-center gap-2 text-xs font-medium text-primary">
                  <Bot className="size-4" />
                  Pi Agent Beta
                </div>
                <p className="whitespace-pre-wrap text-sm leading-6" dir="auto">
                  {turn.reply.message}
                </p>
                {turn.reply.notice && (
                  <p className="text-xs text-muted-foreground">
                    {turn.reply.notice}
                  </p>
                )}
                {!!turn.reply.signals.length && (
                  <SignalList signals={turn.reply.signals} />
                )}
                {turn.reply.results.map((result, i) => (
                  <ResultsCard key={`${result.area}-${i}`} result={result} />
                ))}
                {turn.reply.proposals.map((p) => (
                  <ProposalCard key={p.id} proposal={p} />
                ))}
              </div>
            )
          )}
        </div>
      ))}
      {agent.busy && (
        <div
          role="status"
          className="flex items-center gap-2 text-sm text-muted-foreground"
        >
          <Loader2 className="size-4 animate-spin" />
          Checking your workspace…
        </div>
      )}
      <div ref={tail} />
    </div>
  );
}

function Composer() {
  const agent = useAgent();
  const [message, setMessage] = useState("");
  const [purpose, setPurpose] = useState<"summary" | "employees">("summary");
  const input = useRef<HTMLInputElement>(null);
  return (
    <form
      className="border-t border-border p-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (message.trim()) {
          void agent.send(message.trim());
          setMessage("");
        }
      }}
    >
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <select
          aria-label="Upload purpose"
          value={purpose}
          onChange={(e) => setPurpose(e.target.value as typeof purpose)}
          className="rounded border border-border bg-surface px-2 py-1 text-xs"
        >
          <option value="summary">Summarize document</option>
          {agent.context?.actions.includes("employees.create") && (
            <option value="employees">Import employees</option>
          )}
        </select>
        <button
          type="button"
          disabled={agent.busy}
          onClick={() => input.current?.click()}
          className="inline-flex items-center gap-1 text-xs text-primary disabled:opacity-50"
        >
          <FileUp className="size-3.5" />
          Upload file
        </button>
        <a
          className="ml-auto text-xs text-primary underline"
          href="/templates/agent-employees-10.csv"
          download
        >
          10-employee CSV
        </a>
      </div>
      <input
        ref={input}
        type="file"
        className="sr-only"
        aria-label="Upload document"
        accept=".csv,.txt,.md,.docx,.pdf"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) {
            if (file.size > 2 * 1024 * 1024)
              agent.setError("Choose a file up to 2 MB.");
            else void agent.upload(file, purpose);
          }
          e.target.value = "";
        }}
      />
      <div className="flex items-end gap-2">
        <textarea
          className={`${fieldClass} min-h-20 resize-y`}
          maxLength={4000}
          aria-label="Message Pi Agent"
          placeholder="Ask, find a record, or describe a task…"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={(e) => {
            if (
              e.key === "Enter" &&
              !e.shiftKey &&
              !e.nativeEvent.isComposing
            ) {
              e.preventDefault();
              if (message.trim() && !agent.busy) {
                void agent.send(message.trim());
                setMessage("");
              }
            }
          }}
        />
        <Button
          type="submit"
          size="icon"
          disabled={agent.busy || !message.trim()}
          aria-label="Send message"
        >
          <Send className="size-4" />
        </Button>
      </div>
      <p className="mt-2 text-[11px] text-muted-foreground">
        CSV, TXT, MD, DOCX or text PDF · 2 MB max · Keep passwords and API keys
        out of chat.
      </p>
    </form>
  );
}

function DataTable({ rows }: { rows: Record<string, unknown>[] }) {
  if (!rows.length)
    return (
      <p className="p-3 text-sm text-muted-foreground">No matching records.</p>
    );
  const columns = Array.from(
    new Set(rows.flatMap((row) => Object.keys(row))),
  ).filter(
    (k) =>
      ![
        "sensitive_visible",
        "has_personal_details",
        "created_at",
        "conversation_id",
      ].includes(k),
  );
  return (
    <div className="max-h-80 overflow-auto rounded-lg border border-border">
      <table className="w-full text-left text-xs">
        <thead className="sticky top-0 bg-surface-muted">
          <tr>
            {columns.map((k) => (
              <th
                key={k}
                className="whitespace-nowrap px-3 py-2 font-medium capitalize"
              >
                {label(k)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-t border-border">
              {columns.map((k) => (
                <td key={k} className="max-w-64 break-words px-3 py-2">
                  {display(row[k])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ResultsCard({ result }: { result: ToolResult }) {
  const agent = useAgent();
  const [busy, setBusy] = useState(false);
  const pageable = agent.context?.read_areas.includes(result.area) ?? false;
  return (
    <details className="rounded-xl border border-border p-3" open>
      <summary className="cursor-pointer text-sm font-medium">
        {result.title ?? (
          <span className="capitalize">{label(result.area)}</span>
        )}{" "}
        <span className="font-normal text-muted-foreground">
          · {result.total} {result.count_unit ?? "records"} ·{" "}
          {result.specialist}
          {result.scope ? ` · ${result.scope}` : ""}
        </span>
      </summary>
      <div className="mt-3">
        {result.untrusted_content && (
          <p className="mb-2 text-xs text-muted-foreground">
            Customer-written messages. Read-only: Agent Beta cannot reply on
            WhatsApp.
          </p>
        )}
        <DataTable rows={result.items} />
        <div className="mt-2 flex items-center justify-between text-xs text-muted-foreground">
          <span>
            {result.exact
              ? "Exact totals"
              : result.sample_only
                ? "Sample records"
                : `Page ${result.page}`}{" "}
            · showing {result.items.length}
          </span>
          {safeRoutes.has(result.route) && (
            <Link className="text-primary underline" href={result.route}>
              Open page
            </Link>
          )}
          {pageable &&
            !result.sample_only &&
            result.page * result.page_size < result.total && (
              <button
                disabled={busy}
                className="text-primary"
                onClick={async () => {
                  setBusy(true);
                  try {
                    const next = await agentService.read(
                      result.area,
                      result.page + 1,
                      result.search,
                    );
                    agent.addReply({
                      ...emptyReply("Next page"),
                      results: [next],
                    });
                  } catch (e) {
                    agent.setError(errorMessage(e));
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                Next page
              </button>
            )}
        </div>
      </div>
    </details>
  );
}

function ProposalCard({ proposal }: { proposal: Proposal }) {
  const [current, setCurrent] = useState(proposal);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const client = useQueryClient();
  const { scopeKey } = useSession();
  const [expired, setExpired] = useState(false);
  useEffect(() => {
    const timer = setTimeout(
      () => setExpired(true),
      Math.max(0, new Date(current.expires_at).getTime() - Date.now()),
    );
    return () => clearTimeout(timer);
  }, [current.expires_at]);
  const rows = Array.isArray(current.preview.rows)
    ? (current.preview.rows as Record<string, unknown>[])
    : [current.preview];
  const decide = async (decision: "confirm" | "cancel") => {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      setCurrent(await agentService.decide(current.id, decision));
      await client.invalidateQueries({ queryKey: [...scopeKey] });
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <article
      className="my-3 rounded-xl border border-primary/25 bg-primary/5 p-4"
      aria-label="Action preview"
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold capitalize">
          {label(current.operation)}
        </h3>
        <span className="text-xs">
          {current.status === "pending" ? "Preview only" : current.status}
        </span>
      </div>
      <DataTable rows={rows} />
      {current.status === "pending" ? (
        <>
          <p className="my-3 text-xs text-muted-foreground">
            {rows.length} record(s). Check the details before confirming.
            Expires at {new Date(current.expires_at).toLocaleTimeString()}.
          </p>
          <div className="flex gap-2">
            <Button
              size="sm"
              disabled={busy || expired}
              onClick={() => void decide("confirm")}
            >
              {busy ? (
                <Loader2 className="mr-1 size-3 animate-spin" />
              ) : (
                <Check className="mr-1 size-3" />
              )}
              Confirm changes
            </Button>
            <Button
              size="sm"
              variant="secondary"
              disabled={busy || expired}
              onClick={() => void decide("cancel")}
            >
              Cancel draft
            </Button>
            {expired && (
              <span className="self-center text-xs">
                Expired. Prepare a fresh draft.
              </span>
            )}
          </div>
        </>
      ) : (
        <p className="mt-3 text-sm">
          {current.status === "applied"
            ? `${current.result?.count ?? 0} record(s) saved.`
            : "Draft cancelled."}
        </p>
      )}
      {error && (
        <p role="alert" className="mt-2 text-sm text-danger">
          {error}
        </p>
      )}
    </article>
  );
}

function QuickCreate() {
  const agent = useAgent();
  const [kind, setKind] = useState("tasks.create");
  const [busy, setBusy] = useState(false);
  const allowed = [
    "tasks.create",
    "employees.create",
    "customers.create",
  ].filter((a) => agent.context?.actions.includes(a));
  if (!allowed.length) return null;
  const active = allowed.includes(kind) ? kind : allowed[0];
  return (
    <details className="mt-5 rounded-xl border border-border p-4">
      <summary className="cursor-pointer text-sm font-medium">
        Prepare a change
      </summary>
      <form
        className="mt-4 grid gap-3 sm:grid-cols-2"
        onSubmit={async (e) => {
          e.preventDefault();
          const values = Object.fromEntries(new FormData(e.currentTarget));
          setBusy(true);
          try {
            const args =
              active === "employees.create" ? { rows: [values] } : values;
            const proposal = await agentService.propose(active, args);
            agent.addReply({
              ...emptyReply("Draft ready. Review and confirm the details."),
              proposals: [proposal],
            });
          } catch (err) {
            agent.setError(errorMessage(err));
          } finally {
            setBusy(false);
          }
        }}
      >
        <label className="text-xs sm:col-span-2">
          Action
          <select
            className={`${fieldClass} mt-1`}
            value={active}
            onChange={(e) => setKind(e.target.value)}
          >
            {allowed.map((a) => (
              <option key={a} value={a}>
                {label(a)}
              </option>
            ))}
          </select>
        </label>
        {active === "employees.create" ? (
          <>
            <label className="text-xs">
              Full name
              <input
                className={`${fieldClass} mt-1`}
                name="full_name"
                required
                maxLength={160}
              />
            </label>
            <label className="text-xs">
              Job title
              <input
                className={`${fieldClass} mt-1`}
                name="job_title"
                required
                maxLength={120}
              />
            </label>
            <label className="text-xs">
              Employment type
              <select className={`${fieldClass} mt-1`} name="employment_type">
                <option value="full_time">Full time</option>
                <option value="part_time">Part time</option>
                <option value="contract">Contract</option>
                <option value="intern">Intern</option>
              </select>
            </label>
            <label className="text-xs">
              Hire date
              <input
                className={`${fieldClass} mt-1`}
                type="date"
                name="hire_date"
                required
              />
            </label>
            <p className="text-xs text-muted-foreground sm:col-span-2">
              Creates an HR record. Login accounts are managed on the Members
              page.
            </p>
          </>
        ) : (
          <>
            <label className="text-xs sm:col-span-2">
              {active === "tasks.create" ? "Task title" : "Customer name"}
              <input
                className={`${fieldClass} mt-1`}
                name={active === "tasks.create" ? "title" : "name"}
                required
                maxLength={160}
              />
            </label>
            {active === "tasks.create" && (
              <>
                <label className="text-xs">
                  Specialist
                  <select className={`${fieldClass} mt-1`} name="specialist">
                    {["operations", "hr", "finance", "crm"].map((s) => (
                      <option key={s}>{s}</option>
                    ))}
                  </select>
                </label>
                <label className="text-xs">
                  Priority
                  <select className={`${fieldClass} mt-1`} name="priority">
                    <option>normal</option>
                    <option>high</option>
                    <option>low</option>
                  </select>
                </label>
              </>
            )}
          </>
        )}
        <Button
          type="submit"
          size="sm"
          disabled={busy}
          className="sm:col-span-2"
        >
          {busy ? "Preparing…" : "Preview change"}
        </Button>
      </form>
    </details>
  );
}

function TaskBoard() {
  const agent = useAgent();
  const identity = useAgentIdentity();
  const allowed = agent.context?.read_areas.includes("tasks") ?? false;
  const query = useScopedQuery(
    ["workspace-agent", "tasks", identity],
    () => agentService.read("tasks"),
    { enabled: allowed, retry: false },
  );
  const [busy, setBusy] = useState<string | null>(null);
  if (!allowed)
    return (
      <p className="text-sm text-muted-foreground">
        Your role does not include workspace task access.
      </p>
    );
  return (
    <>
      <div className="mb-4">
        <h2 className="font-semibold">Workspace tasks</h2>
        <p className="mt-1 text-xs text-muted-foreground">
          {agent.context?.permissions.includes("tasks.manage")
            ? "All team tasks in this environment."
            : "Tasks you created or that are assigned to you."}{" "}
          Specialist labels organize the work; they do not start background
          jobs.
        </p>
      </div>
      <QuickCreate />
      {query.isPending ? (
        <p className="mt-4">Loading tasks…</p>
      ) : query.error ? (
        <p role="alert">{errorMessage(query.error)}</p>
      ) : (
        <div className="mt-5 space-y-3">
          {!query.data?.items.length && (
            <p className="text-sm text-muted-foreground">
              No tasks yet. Prepare your first task above.
            </p>
          )}
          {query.data?.items.map((row) => (
            <article
              key={String(row.id)}
              className="rounded-xl border border-border p-4"
            >
              <div className="flex items-center justify-between gap-2">
                <h3 className="text-sm font-medium">{display(row.title)}</h3>
                <span className="rounded bg-surface-muted px-2 py-1 text-xs">
                  {label(display(row.status))}
                </span>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                {display(row.specialist)} · {display(row.priority)} priority
                {row.due_date ? ` · due ${display(row.due_date)}` : ""}
              </p>
              {agent.context?.actions.includes("tasks.update") &&
                row.status !== "done" &&
                row.status !== "cancelled" && (
                  <Button
                    className="mt-3"
                    variant="secondary"
                    size="sm"
                    disabled={busy !== null}
                    onClick={async () => {
                      setBusy(String(row.id));
                      try {
                        const proposal = await agentService.propose(
                          "tasks.update",
                          { id: row.id, status: "done" },
                        );
                        agent.addReply({
                          ...emptyReply(
                            "Task completion draft ready. Review it in Drafts.",
                          ),
                          proposals: [proposal],
                        });
                      } catch (e) {
                        agent.setError(errorMessage(e));
                      } finally {
                        setBusy(null);
                      }
                    }}
                  >
                    Preview completion
                  </Button>
                )}
            </article>
          ))}
          {!!query.data && query.data.total > 25 && (
            <ResultsCard result={query.data} />
          )}
        </div>
      )}
    </>
  );
}

function starterPrompts(permissions: string[]) {
  const prompts = ["Monitor my workspace", "Aaj kya karna chahiye?"];
  if (
    ["customers.read", "sales.read", "quotes.read", "billing.read"].some((p) =>
      permissions.includes(p),
    )
  )
    prompts.push("Summarize my CRM");
  if (permissions.includes("pi.read"))
    prompts.push("Summarize today's WhatsApp chats");
  prompts.push("Meri permissions kya hain?", "Show my tasks");
  return prompts;
}

function SignalList({ signals }: { signals: Signal[] }) {
  return (
    <ul className="space-y-2" aria-label="Workspace signals">
      {signals.map((signal) => (
        <li
          key={signal.key}
          className="rounded-xl border border-border p-3 text-sm"
        >
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="font-medium">
                <span
                  className={`mr-2 inline-block rounded-full border px-2 py-0.5 text-[10px] uppercase ${severityStyle[signal.severity]}`}
                >
                  {signal.severity}
                </span>
                {signal.title}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                {signal.suggestion}
              </p>
              {!!signal.amounts?.length && (
                <p className="mt-1 text-xs">
                  {signal.amounts
                    .map((a) => `${a.currency} ${a.outstanding}`)
                    .join(" · ")}
                </p>
              )}
            </div>
            <div className="flex shrink-0 flex-col items-end gap-1">
              <span className="text-lg font-semibold tabular-nums">
                {signal.count}
              </span>
              {safeRoutes.has(signal.route) && (
                <Link
                  className="text-xs text-primary underline"
                  href={signal.route}
                >
                  Open
                </Link>
              )}
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
}

function MonitorBoard({ onAsk }: { onAsk: () => void }) {
  const agent = useAgent();
  const identity = useAgentIdentity();
  const query = useScopedQuery(
    ["workspace-agent", "monitor", identity],
    agentService.monitor,
    { retry: false, refetchInterval: 60_000 },
  );
  return (
    <>
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 font-semibold">
            <Activity className="size-4 text-primary" />
            Workspace monitor
          </h2>
          <p className="mt-1 text-xs text-muted-foreground">
            Live checks across the areas your role can see. Refreshes every
            minute.
            {query.data &&
              ` Checked: ${query.data.checked_areas.map(label).join(", ") || "none"}.`}
          </p>
        </div>
        <Button
          variant="secondary"
          size="sm"
          disabled={query.isFetching}
          onClick={() => void query.refetch()}
          aria-label="Refresh monitor"
        >
          <RefreshCw
            className={`size-3.5 ${query.isFetching ? "animate-spin" : ""}`}
          />
        </Button>
      </div>
      {query.isPending ? (
        <p>Checking your workspace…</p>
      ) : query.error ? (
        <p role="alert">{errorMessage(query.error)}</p>
      ) : (
        <>
          {query.data.healthy && (
            <p className="mb-3 rounded-xl border border-success/30 bg-success-soft p-3 text-sm text-success">
              All clear. Nothing urgent needs your attention.
            </p>
          )}
          {query.data.signals.length ? (
            <SignalList signals={query.data.signals} />
          ) : null}
          <Button
            className="mt-4"
            size="sm"
            disabled={agent.busy}
            onClick={() => {
              onAsk();
              void agent.send(
                "Monitor my workspace and suggest what I should do first.",
              );
            }}
          >
            Ask Pi Agent for a plan
          </Button>
        </>
      )}
    </>
  );
}
