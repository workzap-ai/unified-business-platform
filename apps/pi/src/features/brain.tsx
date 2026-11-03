"use client";

/**
 * The brain tools for Workzap staff (platform spec 8.11.1, 8.13, 10.7, 5.1): the review queue of
 * conversations that need a person, brain health, and the documents queue, with moderation
 * (put a stopped chat back to listening) and erasure (delete what pi keeps about one person)
 * inside the conversation review. Every call is an existing endpoint:
 *   GET  /pi/review/attention, /pi/review/conversations/{id}   (pi.handoffs.manage)
 *   GET  /pi/brain-health                                     (pi.settings.manage)
 *   GET  /pi/brain-documents, POST /pi/brain-documents/{id}/approve  (sales.read, quotes.write)
 *   POST /pi/brain-moderation/{id}/unblock                    (pi.inbox.reply)
 *   POST /pi/brain-erasure/{customer_id}                      (pi.settings.manage)
 * Read-only except those three actions; the server decides what each person may do.
 */

import { useQuery } from "@tanstack/react-query";
import { ShieldCheck, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";

import { SubNav } from "@/components/shell";
import {
  Badge,
  Button,
  Card,
  CardSection,
  Dialog,
  DialogClose,
  DialogContent,
  EmptyState,
  ErrorState,
  Field,
  Input,
  LoadingBlock,
  Notice,
  PageHeader,
  Select,
  cn,
} from "@/components/ui";
import { errorText, get, post } from "@/lib/api";
import { dateTime, timeAgo } from "@/lib/format";
import { useAction, useBusinessKey, useCan } from "@/lib/session";

export const SECTIONS = [
  { href: "/brain/review", label: "Review queue" },
  { href: "/brain/health", label: "Brain health" },
  { href: "/brain/documents", label: "Documents" },
  { href: "/brain/profile", label: "Business profile" },
];

function BrainShell({
  title,
  description,
  permission,
  needs,
  children,
}: {
  title: string;
  description: string;
  permission: string;
  needs: string;
  children: React.ReactNode;
}) {
  const can = useCan();
  return (
    <div className="min-w-0">
      <PageHeader title={title} description={description} />
      <SubNav items={SECTIONS} />
      <div className="mt-6 min-w-0">
        {can(permission) ? (
          children
        ) : (
          <Notice tone="warning" title={`You can't ${needs}`}>
            Ask your business owner to give you access.
          </Notice>
        )}
      </div>
    </div>
  );
}

/* ----------------------------------------------------------- review queue */

type Alert = { level: string; key: string; label: string; detail: string };

type QueueItem = {
  conversation_id: string;
  customer_ref: string;
  phone: string;
  language: string | null;
  mode: string;
  unread_count: number;
  last_message_at: string;
  alerts: Alert[];
};

type Review = {
  conversation: {
    id: string;
    customer_ref: string;
    phone: string;
    language: string | null;
    mode: string;
    status: string;
    flow_state: string | null;
    last_message_at: string;
  };
  map: {
    version: number | null;
    nodes: {
      id: string;
      title: string;
      category_label: string;
      status: string;
    }[];
  };
  thinking: {
    posture: string;
    hypotheses: {
      text: string;
      confidence: string;
      confirmed_by_owner: boolean;
    }[];
  };
  diagnosis: {
    main_problem: string;
    likely_causes: string[];
    suggested_next_question: string;
  } | null;
  ideas: {
    given_for_business: number;
    per_business_cap: number;
    business_remaining: number;
  };
  handover: {
    handoff: {
      status: string;
      origin_text: string;
      summary: string;
      priority: string;
    } | null;
  };
  box: {
    box: { state: string; version: number; reviewer: string | null } | null;
    offers: {
      rule: string;
      allowed: boolean;
      blocked_reason: string | null;
      at: string;
    }[];
  };
  labels: { alerts: Alert[] };
};

type Context = {
  conversation: { id: string; customer_id: string; customer_name: string };
};

const LEVEL_TONE: Record<string, "danger" | "warning" | "info" | "neutral"> = {
  red: "danger",
  amber: "warning",
  yellow: "warning",
  blue: "info",
};

const STOPPED = ["X_BLOCKED", "X_OUT_OF_SCOPE"];

export function ReviewQueuePage() {
  return (
    <BrainShell
      title="Review queue"
      description="Conversations where pi needs a person: churn risk, a request that has waited, frustration, or an open handover."
      permission="pi.handoffs.manage"
      needs="review conversations"
    >
      <ReviewQueue />
    </BrainShell>
  );
}

function ReviewQueue() {
  const key = useBusinessKey();
  const params = useSearchParams();
  const selected = params.get("c");
  const queue = useQuery({
    queryKey: key(["brain-attention"]),
    queryFn: () =>
      get<{ items: QueueItem[]; total: number }>("/pi/review/attention"),
    refetchInterval: 30_000,
  });
  return (
    <div className="grid min-w-0 grid-cols-1 gap-5 lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)]">
      <section aria-label="Conversations needing attention" className="min-w-0">
        {queue.isPending ? (
          <LoadingBlock rows={4} label="Loading the review queue" />
        ) : queue.isError ? (
          <ErrorState
            message={errorText(queue.error)}
            onRetry={() => queue.refetch()}
          />
        ) : queue.data.items.length === 0 ? (
          <Card>
            <EmptyState
              icon={<ShieldCheck className="size-6" aria-hidden />}
              title="Nothing needs a person right now"
            >
              Chats with a live alert appear here, most urgent first.
            </EmptyState>
          </Card>
        ) : (
          <ul className="space-y-2">
            {queue.data.items.map((item) => (
              <li key={item.conversation_id}>
                <Link
                  href={`/brain/review?c=${encodeURIComponent(item.conversation_id)}`}
                  aria-current={
                    item.conversation_id === selected ? "true" : undefined
                  }
                  className={cn(
                    "block rounded-xl border border-border bg-surface p-3 hover:bg-surface-muted",
                    item.conversation_id === selected &&
                      "border-accent bg-accent-soft/40",
                  )}
                >
                  <span className="flex items-center justify-between gap-2 text-sm font-semibold">
                    <span>{item.phone}</span>
                    <span className="text-xs font-normal text-muted-foreground">
                      {timeAgo(item.last_message_at)}
                    </span>
                  </span>
                  <span className="mt-1 flex flex-wrap gap-1">
                    {item.alerts.map((a) => (
                      <Badge
                        key={a.key}
                        tone={LEVEL_TONE[a.level] ?? "neutral"}
                      >
                        {a.label}
                      </Badge>
                    ))}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
      <section aria-label="Conversation review" className="min-w-0">
        {selected ? (
          <ReviewDetail id={selected} />
        ) : (
          <Card>
            <CardSection className="text-sm text-muted-foreground">
              Choose a conversation to see what pi understood, why it handed
              over, and the state of the Solution Box.
            </CardSection>
          </Card>
        )}
      </section>
    </div>
  );
}

function Block({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {title}
      </h3>
      <div className="text-sm">{children}</div>
    </div>
  );
}

function ReviewDetail({ id }: { id: string }) {
  const key = useBusinessKey();
  const can = useCan();
  const query = useQuery({
    queryKey: key(["brain-review", id]),
    queryFn: () => get<Review>(`/pi/review/conversations/${id}`),
  });
  if (query.isPending) return <LoadingBlock rows={5} label="Loading review" />;
  if (query.isError)
    return (
      <ErrorState
        message={errorText(query.error)}
        onRetry={() => query.refetch()}
      />
    );
  const r = query.data;
  const stopped = STOPPED.includes(r.conversation.flow_state ?? "");
  return (
    <Card>
      <CardSection className="space-y-5">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-lg font-semibold">{r.conversation.phone}</h2>
          <Badge>{r.conversation.mode === "human" ? "Team" : "pi"}</Badge>
          {r.conversation.flow_state ? (
            <Badge tone={stopped ? "danger" : "neutral"}>
              {r.conversation.flow_state}
            </Badge>
          ) : null}
          <Link
            href={`/inbox?conversation=${encodeURIComponent(r.conversation.id)}`}
            className="ms-auto text-sm text-accent underline"
          >
            Open the chat
          </Link>
        </div>
        {r.labels.alerts.length ? (
          <div className="space-y-2">
            {r.labels.alerts.map((a) => (
              <Notice
                key={a.key}
                tone={a.level === "red" ? "danger" : "warning"}
                title={a.label}
              >
                {a.detail}
              </Notice>
            ))}
          </div>
        ) : null}
        {r.handover.handoff ? (
          <Block title="Why pi handed over">
            <p>{r.handover.handoff.origin_text}</p>
            {r.handover.handoff.summary ? (
              <p className="mt-1 text-muted-foreground" data-user-text>
                {r.handover.handoff.summary}
              </p>
            ) : null}
          </Block>
        ) : null}
        <Block title="Solution Box">
          {r.box.box ? (
            <p>
              Version {r.box.box.version}, {r.box.box.state}
              {r.box.box.reviewer ? `, reviewer ${r.box.box.reviewer}` : ""}.
            </p>
          ) : (
            <p className="text-muted-foreground">No box yet.</p>
          )}
          {r.box.offers.length ? (
            <ul className="mt-1 list-inside list-disc text-muted-foreground">
              {r.box.offers.slice(0, 5).map((o) => (
                <li key={`${o.at}-${o.rule}`}>
                  Rule {o.rule}: {o.allowed ? "offer allowed" : "blocked"}
                  {o.blocked_reason ? ` (${o.blocked_reason})` : ""},{" "}
                  {timeAgo(o.at)}
                </li>
              ))}
            </ul>
          ) : null}
        </Block>
        <Block
          title={`Problems on the map${r.map.version ? ` (version ${r.map.version})` : ""}`}
        >
          {r.map.nodes.length ? (
            <ul className="list-inside list-disc">
              {r.map.nodes.map((n) => (
                <li key={n.id} data-user-text>
                  {n.id}: {n.title}{" "}
                  <span className="text-muted-foreground">
                    ({n.category_label}, {n.status.replace(/_/g, " ")})
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted-foreground">No problems noted yet.</p>
          )}
        </Block>
        {r.thinking.hypotheses.length ? (
          <Block title="What pi thinks (not confirmed unless marked)">
            <ul className="list-inside list-disc">
              {r.thinking.hypotheses.map((h) => (
                <li key={h.text} data-user-text>
                  {h.text}{" "}
                  <span className="text-muted-foreground">
                    ({h.confidence}
                    {h.confirmed_by_owner ? ", confirmed by the owner" : ""})
                  </span>
                </li>
              ))}
            </ul>
          </Block>
        ) : null}
        {r.diagnosis ? (
          <Block title="Diagnosis">
            <p data-user-text>{r.diagnosis.main_problem}</p>
            {r.diagnosis.suggested_next_question ? (
              <p className="mt-1 text-muted-foreground" data-user-text>
                Next question: {r.diagnosis.suggested_next_question}
              </p>
            ) : null}
          </Block>
        ) : null}
        <Block title="Ideas given">
          {r.ideas.given_for_business} of {r.ideas.per_business_cap} for this
          business ({r.ideas.business_remaining} left).
        </Block>
        {stopped && can("pi.inbox.reply") ? (
          <UnblockPanel conversationId={r.conversation.id} />
        ) : null}
        {can("pi.settings.manage") ? (
          <ErasePanel
            conversationId={r.conversation.id}
            customerRef={r.conversation.customer_ref}
          />
        ) : null}
      </CardSection>
    </Card>
  );
}

function UnblockPanel({ conversationId }: { conversationId: string }) {
  const router = useRouter();
  const unblock = useAction(
    () => post(`/pi/brain-moderation/${conversationId}/unblock`),
    {
      invalidate: [["brain-review", conversationId], ["brain-attention"]],
      success: "pi is listening to this chat again",
      onSuccess: () => router.refresh(),
    },
  );
  return (
    <Notice
      tone="warning"
      title="pi stopped answering this chat"
      action={
        <Button
          size="sm"
          variant="secondary"
          loading={unblock.isPending}
          onClick={() => unblock.mutate(undefined)}
        >
          Put it back to listening
        </Button>
      }
    >
      After repeated abuse or a threat, or for spam, pi goes silent. Putting the
      chat back to listening clears its strikes. Do this only after a person has
      read the chat.
    </Notice>
  );
}

type EraseResult = {
  removed: Record<string, number>;
  kept: { documents: number; payments: number };
  conversations: number;
};

const REMOVED_LABEL: Record<string, string> = {
  problems: "problems",
  revisions: "problem changes",
  links: "problem links",
  groups: "problem groups",
  memories: "memory notes",
  learning_examples: "learning examples",
  experiences: "scored replies",
  quarantine: "held copies",
  messages_cleared: "messages (the words are gone)",
  solution_memory: "solution notes",
  idea_feedback: "idea feedback",
};

/** Typing "erase" and the customer reference is required, so it cannot be a stray click. */
export function eraseCode(customerRef: string): string {
  return `erase ${customerRef}`;
}

function ErasePanel({
  conversationId,
  customerRef,
}: {
  conversationId: string;
  customerRef: string;
}) {
  const key = useBusinessKey();
  const [open, setOpen] = React.useState(false);
  const [typed, setTyped] = React.useState("");
  const [result, setResult] = React.useState<EraseResult | null>(null);
  const context = useQuery({
    queryKey: key(["context", conversationId]),
    queryFn: () => get<Context>(`/pi/conversations/${conversationId}/context`),
    enabled: open,
  });
  const code = eraseCode(customerRef);
  const erase = useAction(
    (customerId: string) =>
      post<EraseResult>(`/pi/brain-erasure/${customerId}`, { confirm: true }),
    {
      invalidate: [["brain-review", conversationId], ["brain-attention"]],
      onSuccess: (data) => setResult(data),
    },
  );
  const customerId = context.data?.conversation.customer_id;
  const ready = typed.trim().toLowerCase() === code && Boolean(customerId);
  return (
    <div className="rounded-xl border border-danger/30 p-4">
      <h3 className="text-sm font-semibold">Erase what pi keeps about them</h3>
      <p className="mt-1 text-sm text-muted-foreground">
        For a person who asked pi to delete everything it knows about them.
      </p>
      <Dialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          if (!next) {
            setTyped("");
            setResult(null);
          }
        }}
      >
        <Button
          className="mt-3"
          size="sm"
          variant="danger"
          onClick={() => setOpen(true)}
        >
          <Trash2 className="size-4" aria-hidden /> Erase their data
        </Button>
        <DialogContent
          title={result ? "Their data was erased" : "Erase their data?"}
          description={
            result
              ? undefined
              : "This cannot be undone. Quotes, solution documents and payments are kept."
          }
        >
          {result ? (
            <EraseSummary result={result} />
          ) : (
            <form
              className="space-y-4"
              onSubmit={(event) => {
                event.preventDefault();
                if (ready && customerId) erase.mutate(customerId);
              }}
            >
              <p className="text-sm">
                pi will remove the problems it noted, its memory notes, the
                learning examples from their chats, and the words of their
                messages and pi&apos;s replies. The CRM contact record stays.
              </p>
              <Field
                label={`Type "${code}" to confirm`}
                hint="This is the customer reference shown in the review."
                htmlFor="erase-confirm"
              >
                <Input
                  id="erase-confirm"
                  value={typed}
                  onChange={(e) => setTyped(e.target.value)}
                  autoComplete="off"
                  spellCheck={false}
                />
              </Field>
              {context.isError ? (
                <p className="text-sm text-danger" role="alert">
                  {errorText(context.error)}
                </p>
              ) : null}
              <div className="flex justify-end gap-2">
                <DialogClose asChild>
                  <Button type="button" variant="ghost">
                    Cancel
                  </Button>
                </DialogClose>
                <Button
                  type="submit"
                  variant="danger"
                  disabled={!ready}
                  loading={erase.isPending}
                >
                  Erase for good
                </Button>
              </div>
            </form>
          )}
          {result ? (
            <div className="mt-4 flex justify-end">
              <DialogClose asChild>
                <Button>Done</Button>
              </DialogClose>
            </div>
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function EraseSummary({ result }: { result: EraseResult }) {
  const removed = Object.entries(result.removed).filter(([, n]) => n > 0);
  return (
    <div className="space-y-3 text-sm" data-testid="erase-result">
      <p>
        Cleared across {result.conversations}{" "}
        {result.conversations === 1 ? "conversation" : "conversations"}:
      </p>
      {removed.length ? (
        <ul className="list-inside list-disc">
          {removed.map(([name, n]) => (
            <li key={name}>
              {n} {REMOVED_LABEL[name] ?? name.replace(/_/g, " ")}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-muted-foreground">There was nothing to remove.</p>
      )}
      <p>
        Kept on purpose: {result.kept.documents}{" "}
        {result.kept.documents === 1 ? "document" : "documents"} and{" "}
        {result.kept.payments}{" "}
        {result.kept.payments === 1 ? "payment" : "payments"} (business records
        the company must be able to show), and their contact record. Tell the
        person this plainly.
      </p>
    </div>
  );
}

/* ----------------------------------------------------------- brain health */

type BrainHealth = {
  days: number;
  pi_mode: string;
  learning_frozen: boolean;
  metrics: {
    scored: number;
    average_reward?: number;
    confusion_rate?: number;
    correction_rate?: number;
    opt_out_rate?: number;
    complaint_rate?: number;
    rule_break_rate?: number;
    first_time_confirmation_rate?: number;
    repeat_question_rate?: number;
    average_reward_by_language?: Record<string, number>;
  };
  learning: {
    changes_promoted: number;
    changes_rolled_back: number;
    questions_with_a_proven_best: number;
    waiting_for_review: number;
    packs_by_status: Record<string, number>;
  };
  settings: Record<
    string,
    { value: number; default: number; low: number; high: number }
  >;
};

const pct = (n: number | undefined) =>
  n === undefined ? "n/a" : `${Math.round(n * 1000) / 10}%`;

function Tile({
  label,
  value,
  tone,
  hint,
}: {
  label: string;
  value: string;
  tone?: "ok" | "bad";
  hint?: string;
}) {
  return (
    <div className="rounded-xl border border-border bg-surface p-4">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p
        className={cn(
          "mt-1 text-2xl font-semibold",
          tone === "bad" && "text-danger",
          tone === "ok" && "text-success",
        )}
      >
        {value}
      </p>
      {hint ? (
        <p className="mt-1 text-xs text-muted-foreground">{hint}</p>
      ) : null}
    </div>
  );
}

export function BrainHealthPage() {
  return (
    <BrainShell
      title="Brain health"
      description="How pi's brain is doing, from real replies. Nothing here changes how pi behaves."
      permission="pi.settings.manage"
      needs="see brain health"
    >
      <BrainHealthBody />
    </BrainShell>
  );
}

function BrainHealthBody() {
  const key = useBusinessKey();
  const [days, setDays] = React.useState("7");
  const query = useQuery({
    queryKey: key(["brain-health", days]),
    queryFn: () => get<BrainHealth>("/pi/brain-health", { days }),
  });
  if (query.isPending) return <LoadingBlock rows={4} label="Loading health" />;
  if (query.isError)
    return (
      <ErrorState
        message={errorText(query.error)}
        onRetry={() => query.refetch()}
      />
    );
  const h = query.data;
  const m = h.metrics;
  const brain = h.pi_mode === "brain";
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <Badge tone={brain ? "accent" : "neutral"} data-testid="pi-mode">
          {brain ? "Brain mode" : "Legacy mode"}
        </Badge>
        <Badge tone={h.learning_frozen ? "warning" : "success"}>
          {h.learning_frozen ? "Learning is frozen" : "Learning is on"}
        </Badge>
        <label className="ms-auto flex items-center gap-2 text-sm">
          Period
          <Select
            aria-label="Period"
            value={days}
            onChange={(e) => setDays(e.target.value)}
            className="w-auto"
          >
            <option value="1">Last day</option>
            <option value="7">Last 7 days</option>
            <option value="30">Last 30 days</option>
          </Select>
        </label>
      </div>
      {!brain ? (
        <Notice tone="info" title="This workspace is not in brain mode">
          The numbers below only fill in once pi answers with the brain.
        </Notice>
      ) : null}
      {m.scored === 0 ? (
        <Notice tone="info" title="No scored replies in this period">
          Replies are scored a little after they are sent.
        </Notice>
      ) : (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Tile label="Replies scored" value={String(m.scored)} />
          <Tile
            label="Average reward"
            value={String(m.average_reward ?? "n/a")}
          />
          <Tile
            label="Rule breaks (must be 0)"
            value={pct(m.rule_break_rate)}
            tone={m.rule_break_rate ? "bad" : "ok"}
          />
          <Tile
            label="Confirmed first time"
            value={pct(m.first_time_confirmation_rate)}
          />
          <Tile label="Confusion" value={pct(m.confusion_rate)} />
          <Tile label="Corrections" value={pct(m.correction_rate)} />
          <Tile label="Opt-outs" value={pct(m.opt_out_rate)} />
          <Tile label="Complaints" value={pct(m.complaint_rate)} />
        </div>
      )}
      <Card>
        <CardSection className="space-y-2 text-sm">
          <h2 className="font-semibold">Learning</h2>
          <p>
            {h.learning.changes_promoted} changes promoted,{" "}
            {h.learning.changes_rolled_back} rolled back.{" "}
            {Math.round(h.learning.questions_with_a_proven_best * 100)}% of
            questions have a proven best.
          </p>
          <p>
            {h.learning.waiting_for_review === 0
              ? "Nothing is waiting for a reviewer."
              : `${h.learning.waiting_for_review} items wait for a reviewer.`}
          </p>
        </CardSection>
      </Card>
      <details className="rounded-2xl border border-border bg-surface p-4">
        <summary className="cursor-pointer text-sm font-medium">
          Tunable settings ({Object.keys(h.settings).length})
        </summary>
        <table className="mt-3 w-full text-sm">
          <thead className="text-start text-xs text-muted-foreground">
            <tr>
              <th className="py-1 text-start">Setting</th>
              <th className="py-1 text-start">Now</th>
              <th className="py-1 text-start">Allowed range</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(h.settings).map(([name, s]) => (
              <tr key={name} className="border-t border-border">
                <td className="py-1">{name.replace(/_/g, " ")}</td>
                <td className="py-1">{s.value}</td>
                <td className="py-1 text-muted-foreground">
                  {s.low} to {s.high} (default {s.default})
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}

/* --------------------------------------------------------- documents queue */

type BrainDoc = {
  id: string;
  ref: string;
  kind: string;
  version: number;
  status: string;
  total: string | null;
  currency: string | null;
  language: string | null;
  drafted_by: string | null;
  approved_by: string | null;
  created_at: string;
  blockers: string[];
};

const DOC_STATUS_TONE: Record<
  string,
  "warning" | "success" | "neutral" | "info"
> = {
  draft: "warning",
  in_review: "warning",
  approved: "success",
  sent: "info",
  superseded: "neutral",
};

export function DocumentsQueuePage() {
  return (
    <BrainShell
      title="Documents"
      description="Solution documents and quotes pi drafted. Nothing reaches a customer until a reviewer approves it, and pi never sets a price."
      permission="sales.read"
      needs="see documents"
    >
      <DocumentsQueue />
    </BrainShell>
  );
}

function DocumentsQueue() {
  const key = useBusinessKey();
  const can = useCan();
  const [status, setStatus] = React.useState("");
  const query = useQuery({
    queryKey: key(["brain-documents", status]),
    queryFn: () =>
      get<{ items: BrainDoc[] }>(
        "/pi/brain-documents",
        status ? { status } : undefined,
      ),
  });
  const approve = useAction(
    (id: string) => post(`/pi/brain-documents/${id}/approve`),
    {
      invalidate: [["brain-documents"]],
      success: "Approved",
    },
  );
  const waiting = (d: BrainDoc) =>
    d.status === "draft" || d.status === "in_review";
  return (
    <div className="space-y-4">
      <label className="flex items-center gap-2 text-sm">
        Show
        <Select
          aria-label="Status"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="w-auto"
        >
          <option value="">All</option>
          <option value="draft">Draft</option>
          <option value="in_review">In review</option>
          <option value="approved">Approved</option>
          <option value="sent">Sent</option>
        </Select>
      </label>
      {query.isPending ? (
        <LoadingBlock rows={4} label="Loading documents" />
      ) : query.isError ? (
        <ErrorState
          message={errorText(query.error)}
          onRetry={() => query.refetch()}
        />
      ) : query.data.items.length === 0 ? (
        <Card>
          <EmptyState title="No documents here">
            When an owner says yes to the Solution Box, pi drafts the document
            and quote and they wait here for approval.
          </EmptyState>
        </Card>
      ) : (
        <ul className="space-y-3">
          {[...query.data.items]
            .sort((a, b) => Number(waiting(b)) - Number(waiting(a)))
            .map((d) => (
              <li key={d.id}>
                <Card>
                  <CardSection className="flex flex-wrap items-center gap-3">
                    <div className="min-w-0 flex-1">
                      <p className="font-semibold">
                        {d.ref}{" "}
                        <span className="text-sm font-normal text-muted-foreground">
                          {d.kind === "quote" ? "Quote" : "Solution document"},
                          version {d.version}
                        </span>
                      </p>
                      <p className="text-xs text-muted-foreground">
                        Drafted {timeAgo(d.created_at)} (
                        {dateTime(d.created_at)})
                        {d.total ? ` · ${d.currency ?? ""} ${d.total}` : ""}
                      </p>
                    </div>
                    <Badge tone={DOC_STATUS_TONE[d.status] ?? "neutral"}>
                      {d.status.replace(/_/g, " ")}
                    </Badge>
                    <a
                      className="text-sm text-accent underline"
                      href={`/api/v1/pi-app/pi/brain-documents/${d.id}/pdf`}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      Open PDF
                    </a>
                    {waiting(d) && can("quotes.write") ? (
                      <Button
                        size="sm"
                        loading={
                          approve.isPending && approve.variables === d.id
                        }
                        onClick={() => approve.mutate(d.id)}
                      >
                        Approve
                      </Button>
                    ) : null}
                  </CardSection>
                </Card>
              </li>
            ))}
        </ul>
      )}
    </div>
  );
}
