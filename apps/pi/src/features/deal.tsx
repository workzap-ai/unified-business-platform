"use client";

/**
 * One deal: what it needs next, every step from the enquiry to the payment, the brief,
 * the team's notes, what the customer did with the links pi sent, and the invoice with
 * its receipts. API: /pi/deals/leads/{id}/journey (pi_saas/deal_routes.py), /sales/leads
 * (sales/routes.py), /sales/billing/invoices and /billing/invoices/{id}/... .
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  ArrowRightLeft,
  Check,
  Circle,
  Compass,
  Copy,
  Download,
  Eye,
  FileText,
  MessageCircle,
  Pencil,
  Receipt,
  Route,
  Send,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  User,
} from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { PiFace } from "@/components/brand";
import {
  Badge,
  Button,
  Card,
  CardSection,
  Dialog,
  DialogContent,
  ErrorState,
  Field,
  Input,
  LoadingBlock,
  Notice,
  Skeleton,
  Textarea,
} from "@/components/ui";
import { fileDownloadUrl, fileSize } from "@/features/customer-files";
import {
  DELIVERY,
  DeliveryDialog,
  ProposalDialog,
  STAGES,
  type Delivery,
} from "@/features/deals";
import { ApiError, errorText, get, patch, post, put } from "@/lib/api";
import { cn } from "@/lib/cn";
import { piLink } from "@/lib/links";
import { date, dateTime, money, timeAgo } from "@/lib/format";
import { useAction, useBusinessKey, useCan } from "@/lib/session";

interface Lead {
  id: string;
  customer_id: string | null;
  customer_name: string | null;
  title: string;
  stage: string;
  source: string;
  estimated_value: string | null;
  currency: string;
  requirements: Record<string, unknown>;
  missing_information: string[];
  notes: string;
  conversation_id: string | null;
  closed_at: string | null;
  created_at: string;
  updated_at: string;
  next_stages: string[];
}

type JourneyAction =
  "" | "edit" | "proposal_from_brief" | "send_proposal" | "send_invoice";

interface JourneyStep {
  key: string;
  label: string;
  at: string | null;
  done: boolean;
  detail: string;
}

interface Journey {
  lead_id: string;
  stage: string;
  steps: JourneyStep[];
  next: {
    title: string;
    detail: string;
    action: JourneyAction;
    href: string;
    auto: boolean;
  };
  reminder: { kind: string; at: string } | null;
  quote_id: string | null;
  invoice_id: string | null;
  order_id: string | null;
}

interface DealDocument {
  id: string;
  kind: string;
  delivery: string;
  viewed_at: string | null;
  response: "accepted" | "changes" | "rejected" | null;
  response_note: string | null;
  responded_at: string | null;
  created_at: string;
}

interface Invoice {
  id: string;
  number: string;
  status: string;
  currency: string;
  total: string;
  amount_paid: string;
  balance_due: string;
  due_date: string | null;
  is_overdue: boolean;
}

interface PaymentLinkSent {
  whatsapp: Delivery | null;
  pay_link: string | null;
  email: string | null;
  email_error: string | null;
}

interface ReceiptFile {
  id: string;
  name: string;
  size: number;
  created_at: string;
}

const STAGE_BUTTON: Record<string, string> = {
  new: "Reopen as new",
  qualified: "Qualify",
  proposal: "Move to proposal",
  won: "Mark won",
  lost: "Mark lost",
};

const REMINDERS: Record<string, string> = {
  proposal_unopened: "proposal not opened yet",
  proposal_unanswered: "proposal opened, no answer yet",
  invoice_due: "invoice due tomorrow",
  invoice_overdue: "invoice overdue",
};

const INVOICE_STATUS: Record<
  string,
  { label: string; tone: "neutral" | "info" | "warning" | "success" }
> = {
  draft: { label: "Draft", tone: "neutral" },
  issued: { label: "Waiting for payment", tone: "warning" },
  partially_paid: { label: "Part paid", tone: "info" },
  paid: { label: "Paid", tone: "success" },
  void: { label: "Cancelled", tone: "neutral" },
};

/** pi's own block in the lead notes, rewritten from the chat (pi_saas/deals.py). */
const NOTES_START = "── pi's notes (updated from the chat) ──";
const NOTES_END = "── end of pi's notes ──";
/** The lead update accepts up to 4,000 characters of notes. */
const NOTES_MAX = 4000;

function humanize(value: string): string {
  return value.replace(/[_-]+/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

function formatRequirement(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "string") return value;
  if (typeof value === "number") return value.toLocaleString();
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (Array.isArray(value)) return value.map(formatRequirement).join(", ");
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

/** Dates arrive as "2026-10-12" (a day) or a full timestamp. */
function when(value: string): string {
  return value.length === 10 ? date(value) : dateTime(value);
}

function splitNotes(notes: string): { block: string | null; team: string } {
  const start = notes.indexOf(NOTES_START);
  const end = notes.indexOf(NOTES_END);
  if (start === -1 || end <= start) return { block: null, team: notes.trim() };
  return {
    block: notes.slice(start, end + NOTES_END.length),
    team: (notes.slice(0, start) + notes.slice(end + NOTES_END.length)).trim(),
  };
}

function blockBody(block: string): string {
  return block.slice(NOTES_START.length, -NOTES_END.length).trim();
}

/**
 * Where a next-step link from the API goes in the pi app. Proposal pages open the
 * proposal dialog; the invoice is on this page; requests and chats have their own pages.
 */
type NextLink =
  | { kind: "quote"; quoteId: string; edit: boolean }
  | { kind: "invoice" }
  | { kind: "page"; href: string };

function mapHref(href: string): NextLink | null {
  if (!href) return null;
  const quote = href.match(/^\/quotes\/([^/?#]+)(\/edit)?/);
  if (quote)
    return { kind: "quote", quoteId: quote[1], edit: Boolean(quote[2]) };
  if (href.startsWith("/invoices/")) return { kind: "invoice" };
  const page = piLink(href);
  // The deals board is one step back, not a next step; outside links never show here.
  if (!page || page === "/deals" || !page.startsWith("/")) return null;
  return { kind: "page", href: page };
}

export function DealPage({ id }: { id: string }) {
  const can = useCan();
  if (!can("sales.read")) {
    return (
      <div className="space-y-6">
        <BackLink />
        <Notice tone="info" title="No access to deals">
          Your role doesn&apos;t include deals. Ask your business owner if you
          need it.
        </Notice>
      </div>
    );
  }
  return <DealView id={id} />;
}

function BackLink() {
  return (
    <Link
      href="/deals"
      className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
    >
      <ArrowLeft className="size-4 rtl:rotate-180" aria-hidden /> Deals
    </Link>
  );
}

function DealView({ id }: { id: string }) {
  const key = useBusinessKey();
  const can = useCan();
  const client = useQueryClient();
  const lead = useQuery({
    queryKey: key(["deals", "lead", id]),
    queryFn: () => get<Lead>(`/sales/leads/${id}`),
  });
  const journey = useQuery({
    queryKey: key(["deals", "journey", id]),
    queryFn: () => get<Journey>(`/pi/deals/leads/${id}/journey`),
  });
  const [editing, setEditing] = React.useState(false);
  const [proposal, setProposal] = React.useState<string | null>(null);
  const [result, setResult] = React.useState<Delivery | null>(null);

  if (lead.isPending)
    return (
      <div className="space-y-6">
        <BackLink />
        <LoadingBlock rows={4} label="Loading deal" />
      </div>
    );
  if (lead.isError)
    return (
      <div className="space-y-6">
        <BackLink />
        <ErrorState
          message={errorText(lead.error)}
          onRetry={() => lead.refetch()}
        />
      </div>
    );

  const l = lead.data;
  const j = journey.data;
  const stage = STAGES.find((s) => s.key === l.stage);
  const name = l.customer_name ?? l.title;
  const next = j ? (
    <NextStepCard
      journey={j}
      onEdit={() => setEditing(true)}
      onProposal={setProposal}
      onDelivered={setResult}
    />
  ) : null;

  return (
    <div className="space-y-6">
      <BackLink />
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            {stage ? (
              <span
                className={cn(
                  "rounded-full px-2.5 py-0.5 text-xs font-medium",
                  stage.tone,
                )}
              >
                {stage.label}
              </span>
            ) : null}
            {l.source === "pi" ? (
              <Badge tone="accent">
                <PiFace size={14} decorative /> From WhatsApp
              </Badge>
            ) : null}
          </div>
          <h1
            className="mt-2 break-words text-[26px] font-semibold leading-tight tracking-[-0.035em] sm:text-[30px]"
            data-user-text
          >
            {l.title}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {l.customer_id ? (
              <Link
                href={`/customers/${l.customer_id}`}
                className="font-medium text-accent hover:underline"
              >
                {l.customer_name ?? "Customer"}
              </Link>
            ) : (
              "No customer linked"
            )}
            {" · "}
            {l.estimated_value
              ? `${money(l.estimated_value, l.currency)} estimated`
              : "No estimated value"}
            {" · "}Updated {timeAgo(l.updated_at)}
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          {l.conversation_id ? (
            <Button asChild variant="secondary">
              <Link href={`/inbox?conversation=${l.conversation_id}`}>
                <MessageCircle className="size-4" aria-hidden /> Open chat
              </Link>
            </Button>
          ) : null}
          {can("sales.write") ? (
            <Button variant="secondary" onClick={() => setEditing(true)}>
              <Pencil className="size-4" aria-hidden /> Edit
            </Button>
          ) : null}
        </div>
      </div>

      {l.stage === "won" ? (
        <Notice tone="success" title="Won">
          This deal closed on {date(l.closed_at)}. Won is a final stage.
        </Notice>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="min-w-0 space-y-6">
          {next ? <div className="lg:hidden">{next}</div> : null}
          {journey.isPending ? (
            <Skeleton className="h-64 w-full" />
          ) : j ? (
            <JourneyCard journey={j} />
          ) : journey.error instanceof ApiError &&
            journey.error.status >= 500 ? (
            <ErrorState
              message={errorText(journey.error)}
              onRetry={() => journey.refetch()}
            />
          ) : null}
          <RequirementsCard lead={l} />
          <NotesCard lead={l} />
          {j?.invoice_id && can("billing.read") ? (
            <InvoiceCard invoiceId={j.invoice_id} onDelivered={setResult} />
          ) : null}
        </div>
        <div className="min-w-0 space-y-6">
          {next ? <div className="hidden lg:block">{next}</div> : null}
          <StageCard lead={l} />
          {j?.quote_id || j?.invoice_id ? (
            <DocumentsCard quoteId={j.quote_id} invoiceId={j.invoice_id} />
          ) : null}
        </div>
      </div>

      {editing ? (
        <EditLeadDialog lead={l} onClose={() => setEditing(false)} />
      ) : null}
      {proposal ? (
        <ProposalDialog
          name={name}
          quoteId={proposal}
          onClose={() => {
            setProposal(null);
            void client.invalidateQueries({ queryKey: key(["deals"]) });
          }}
          onSent={(r) => {
            setProposal(null);
            setResult(r);
            void client.invalidateQueries({ queryKey: key(["deals"]) });
          }}
        />
      ) : null}
      <DeliveryDialog result={result} onClose={() => setResult(null)} />
    </div>
  );
}

function SectionTitle({
  icon: Icon,
  title,
  description,
}: {
  icon: typeof Route;
  title: string;
  description?: string;
}) {
  return (
    <div className="mb-4">
      <h2 className="flex items-center gap-2 text-base font-semibold">
        <Icon className="size-4 text-muted-foreground" aria-hidden />
        {title}
      </h2>
      {description ? (
        <p className="text-sm text-muted-foreground">{description}</p>
      ) : null}
    </div>
  );
}

/** "Next step": the one thing this deal needs now, with the button that does it. */
function NextStepCard({
  journey,
  onEdit,
  onProposal,
  onDelivered,
}: {
  journey: Journey;
  onEdit: () => void;
  onProposal: (quoteId: string) => void;
  onDelivered: (r: Delivery) => void;
}) {
  const can = useCan();
  const next = journey.next;
  const make = useAction(
    () =>
      post<{ quote_id: string; number: string }>(
        `/pi/deals/leads/${journey.lead_id}/proposal`,
      ),
    {
      invalidate: [["deals"]],
      success: (r) => `Proposal ${r.number} created. Add the prices.`,
      onSuccess: (r) => onProposal(r.quote_id),
    },
  );
  const sendProposal = useAction(
    (quoteId: string) => post<Delivery>(`/pi/deals/quotes/${quoteId}/send`),
    { invalidate: [["deals"]], onSuccess: onDelivered },
  );
  const sendInvoice = useAction(
    (invoiceId: string) =>
      post<Delivery>(`/pi/deals/invoices/${invoiceId}/send`),
    { invalidate: [["deals"]], onSuccess: onDelivered },
  );

  let button: React.ReactNode = null;
  if (next.action === "proposal_from_brief" && can("quotes.write")) {
    button = (
      <Button
        size="sm"
        variant={next.auto ? "secondary" : "primary"}
        loading={make.isPending}
        onClick={() => make.mutate(undefined)}
      >
        <Sparkles className="size-4" aria-hidden />
        {next.auto ? "Make it now" : "Proposal from brief"}
      </Button>
    );
  } else if (
    next.action === "send_proposal" &&
    journey.quote_id &&
    can("quotes.write")
  ) {
    const quoteId = journey.quote_id;
    button = (
      <Button
        size="sm"
        variant={next.auto ? "secondary" : "primary"}
        loading={sendProposal.isPending}
        onClick={() => sendProposal.mutate(quoteId)}
      >
        <Send className="size-4" aria-hidden />
        {next.auto ? "Send again" : "Send on WhatsApp"}
      </Button>
    );
  } else if (
    next.action === "send_invoice" &&
    journey.invoice_id &&
    can("billing.write")
  ) {
    const invoiceId = journey.invoice_id;
    button = (
      <Button
        size="sm"
        variant="secondary"
        loading={sendInvoice.isPending}
        onClick={() => sendInvoice.mutate(invoiceId)}
      >
        <Receipt className="size-4" aria-hidden /> Send invoice again
      </Button>
    );
  } else if (next.action === "edit" && can("sales.write")) {
    button = (
      <Button size="sm" onClick={onEdit}>
        <Pencil className="size-4" aria-hidden /> Edit deal
      </Button>
    );
  }

  const target = mapHref(next.href);
  let link: React.ReactNode = null;
  const variant = button ? "secondary" : "primary";
  if (target?.kind === "quote" && can("quotes.read")) {
    link = (
      <Button
        size="sm"
        variant={variant}
        onClick={() => onProposal(target.quoteId)}
      >
        <FileText className="size-4" aria-hidden />
        {target.edit ? "Add prices" : "Open proposal"}
      </Button>
    );
  } else if (target?.kind === "invoice" && can("billing.read")) {
    link = (
      <Button
        size="sm"
        variant={variant}
        onClick={() =>
          document
            .getElementById("deal-invoice")
            ?.scrollIntoView({ behavior: "smooth", block: "start" })
        }
      >
        <Receipt className="size-4" aria-hidden /> See invoice
      </Button>
    );
  } else if (target?.kind === "page") {
    link = (
      <Button asChild size="sm" variant={variant}>
        <Link href={target.href}>
          Open <ArrowRight className="size-4 rtl:rotate-180" aria-hidden />
        </Link>
      </Button>
    );
  }

  return (
    <Card className="border-accent/30">
      <CardSection>
        <SectionTitle
          icon={Compass}
          title="Next step"
          description="What this deal needs now"
        />
        <p className="flex flex-wrap items-center gap-2 font-semibold">
          {next.title}
          {next.auto ? (
            <Badge tone="accent">
              <PiFace size={14} decorative /> pi does this
            </Badge>
          ) : null}
        </p>
        <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
          {next.detail}
        </p>
        {button || link ? (
          <div className="mt-4 flex flex-wrap gap-2">
            {button}
            {link}
          </div>
        ) : null}
      </CardSection>
    </Card>
  );
}

/** "Journey": every step from the first message to the payment. */
function JourneyCard({ journey }: { journey: Journey }) {
  const current = journey.steps.findIndex((s) => !s.done);
  const lost = journey.stage === "lost";
  return (
    <Card>
      <CardSection>
        <SectionTitle
          icon={Route}
          title="Journey"
          description="From the first message to the payment"
        />
        <ol>
          {journey.steps.map((step, i) => {
            const now = !lost && i === current;
            return (
              <li key={step.key} className="relative flex gap-3 pb-4 last:pb-0">
                {i < journey.steps.length - 1 ? (
                  <span
                    aria-hidden
                    className={cn(
                      "absolute start-[11px] top-6 h-[calc(100%-1.25rem)] w-px",
                      step.done ? "bg-success/50" : "bg-border",
                    )}
                  />
                ) : null}
                <span
                  aria-hidden
                  className={cn(
                    "relative z-10 mt-0.5 flex size-[22px] shrink-0 items-center justify-center rounded-full border",
                    step.done
                      ? "border-transparent bg-success-soft text-success"
                      : now
                        ? "border-accent bg-accent-soft text-accent"
                        : "border-border bg-surface text-muted-foreground",
                  )}
                >
                  {step.done ? (
                    <Check className="size-3.5" />
                  ) : (
                    <Circle className={cn("size-2", now && "fill-current")} />
                  )}
                </span>
                <div className="min-w-0 flex-1">
                  <p
                    className={cn(
                      "text-sm",
                      step.done || now
                        ? "font-medium"
                        : "text-muted-foreground",
                    )}
                  >
                    {step.label}
                    <span className="sr-only">
                      {step.done ? " (done)" : now ? " (now)" : " (later)"}
                    </span>
                  </p>
                  {step.detail || step.at ? (
                    <p
                      className="mt-0.5 break-words text-xs text-muted-foreground"
                      data-user-text
                    >
                      {[step.detail, step.at ? when(step.at) : ""]
                        .filter(Boolean)
                        .join(" · ")}
                    </p>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ol>
        {journey.reminder ? (
          <p className="mt-4 flex items-start gap-1.5 border-t border-border pt-3 text-xs text-muted-foreground">
            <PiFace size={14} decorative className="mt-px shrink-0" />
            <span>
              Next reminder from pi:{" "}
              {REMINDERS[journey.reminder.kind] ?? "a follow-up"},{" "}
              {when(journey.reminder.at)}
            </span>
          </p>
        ) : null}
      </CardSection>
    </Card>
  );
}

function RequirementsCard({ lead }: { lead: Lead }) {
  const fromPi = lead.source === "pi";
  // Keys starting with "_" are internal (e.g. "_project": which deal a lead is).
  const entries = Object.entries(lead.requirements ?? {}).filter(
    ([k, v]) => !k.startsWith("_") && v !== null && v !== undefined && v !== "",
  );
  return (
    <Card>
      <CardSection>
        <SectionTitle
          icon={FileText}
          title="Brief"
          description={
            fromPi
              ? "What the customer told pi on WhatsApp"
              : "What the customer needs"
          }
        />
        {entries.length ? (
          <dl className="grid gap-3 text-sm sm:grid-cols-2">
            {entries.map(([k, v]) => (
              <div key={k} className="min-w-0">
                <dt className="text-muted-foreground">{humanize(k)}</dt>
                <dd className="break-words" data-user-text>
                  {formatRequirement(v)}
                </dd>
              </div>
            ))}
          </dl>
        ) : (
          <p className="text-sm text-muted-foreground">
            {fromPi
              ? "pi hasn't recorded the brief for this deal yet."
              : "Nothing recorded. Use the notes for what the customer needs."}
          </p>
        )}
        {lead.missing_information.length ? (
          <div className="mt-4 rounded-lg border border-warning/25 bg-warning-soft p-3">
            <p className="text-sm font-medium">Missing information</p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Confirm these with the customer before pricing.
            </p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {lead.missing_information.map((m) => (
                <Badge key={m} tone="warning">
                  <AlertCircle className="size-3" aria-hidden /> {humanize(m)}
                </Badge>
              ))}
            </div>
          </div>
        ) : null}
      </CardSection>
    </Card>
  );
}

function NotesCard({ lead }: { lead: Lead }) {
  const can = useCan();
  const write = can("sales.write");
  const { block, team } = splitNotes(lead.notes ?? "");
  const [draft, setDraft] = React.useState<string | null>(null);
  const value = draft ?? team;
  const dirty = draft !== null && draft.trim() !== team;
  const combined = block
    ? value.trim()
      ? `${block}\n\n${value.trim()}`
      : block
    : value.trim();
  const tooLong = combined.length > NOTES_MAX;
  const save = useAction(
    () => patch<Lead>(`/sales/leads/${lead.id}`, { notes: combined }),
    {
      success: "Notes saved",
      invalidate: [["deals"]],
      onSuccess: () => setDraft(null),
    },
  );
  return (
    <Card>
      <CardSection>
        <SectionTitle
          icon={Pencil}
          title="Notes"
          description="For your team. The customer never sees these."
        />
        {block ? (
          <div className="mb-4 rounded-lg border border-accent/25 bg-accent-soft/50 p-3">
            <p className="mb-1 flex items-center gap-1.5 text-xs font-medium text-accent-soft-foreground">
              <PiFace size={14} decorative /> pi&apos;s notes, kept up to date
              from the chat
            </p>
            <p
              className="whitespace-pre-wrap break-words text-sm"
              data-user-text
            >
              {blockBody(block)}
            </p>
          </div>
        ) : null}
        {write ? (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (dirty && !tooLong) save.mutate(undefined);
            }}
          >
            <Field
              label="Your notes"
              htmlFor="deal-notes-body"
              error={
                tooLong
                  ? `Notes are limited to ${NOTES_MAX.toLocaleString()} characters${block ? ", including pi's notes" : ""}. Shorten them to save.`
                  : null
              }
            >
              <Textarea
                id="deal-notes-body"
                rows={5}
                value={value}
                placeholder="Budget, timing, who decides, anything else"
                aria-invalid={tooLong || undefined}
                onChange={(e) => setDraft(e.target.value)}
              />
            </Field>
            <div className="mt-3 flex flex-wrap items-center justify-end gap-2">
              <span
                className={cn(
                  "me-auto text-xs tabular-nums text-muted-foreground",
                  tooLong && "text-danger",
                )}
              >
                {combined.length.toLocaleString()} /{" "}
                {NOTES_MAX.toLocaleString()}
              </span>
              {dirty ? (
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  disabled={save.isPending}
                  onClick={() => setDraft(null)}
                >
                  Discard
                </Button>
              ) : null}
              <Button
                type="submit"
                size="sm"
                loading={save.isPending}
                disabled={!dirty || tooLong}
              >
                Save notes
              </Button>
            </div>
          </form>
        ) : team ? (
          <p className="whitespace-pre-wrap break-words text-sm" data-user-text>
            {team}
          </p>
        ) : (
          <p className="text-sm text-muted-foreground">No notes yet.</p>
        )}
      </CardSection>
    </Card>
  );
}

function StageCard({ lead }: { lead: Lead }) {
  const can = useCan();
  const [confirmWon, setConfirmWon] = React.useState(false);
  const move = useAction(
    (stage: string) => put<Lead>(`/sales/leads/${lead.id}/stage`, { stage }),
    {
      invalidate: [["deals"]],
      success: (l) =>
        `Moved to ${STAGES.find((s) => s.key === l.stage)?.label ?? l.stage}`,
      onSuccess: () => setConfirmWon(false),
    },
  );
  const targets = lead.next_stages.filter((s) => s in STAGE_BUTTON);
  return (
    <Card>
      <CardSection>
        <SectionTitle
          icon={ArrowRightLeft}
          title="Move the deal"
          description="Where it can go from here"
        />
        {!targets.length ? (
          <p className="text-sm text-muted-foreground">
            This deal is in a final stage.
          </p>
        ) : can("sales.write") ? (
          <div className="flex flex-wrap gap-2">
            {targets.map((stage) => (
              <Button
                key={stage}
                size="sm"
                variant={
                  stage === "won"
                    ? "primary"
                    : stage === "lost"
                      ? "ghost"
                      : "secondary"
                }
                loading={move.isPending && move.variables === stage}
                disabled={move.isPending}
                onClick={() =>
                  stage === "won" ? setConfirmWon(true) : move.mutate(stage)
                }
              >
                {STAGE_BUTTON[stage]}
              </Button>
            ))}
          </div>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {targets.map((stage) => (
              <Badge key={stage}>
                {STAGES.find((s) => s.key === stage)?.label ?? stage}
              </Badge>
            ))}
          </div>
        )}
        <dl className="mt-4 space-y-1.5 border-t border-border pt-3 text-sm">
          <div className="flex justify-between gap-3">
            <dt className="text-muted-foreground">Created</dt>
            <dd title={dateTime(lead.created_at)}>{date(lead.created_at)}</dd>
          </div>
          {lead.closed_at ? (
            <div className="flex justify-between gap-3">
              <dt className="text-muted-foreground">Closed</dt>
              <dd title={dateTime(lead.closed_at)}>{date(lead.closed_at)}</dd>
            </div>
          ) : null}
        </dl>
      </CardSection>
      <Dialog
        open={confirmWon}
        onOpenChange={(open) =>
          !open && !move.isPending ? setConfirmWon(false) : null
        }
      >
        <DialogContent
          title="Mark this deal as won?"
          description="Won is a final stage: the deal can't be moved again afterwards, and its value counts toward what you closed."
        >
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <Button variant="ghost" onClick={() => setConfirmWon(false)}>
              Cancel
            </Button>
            <Button loading={move.isPending} onClick={() => move.mutate("won")}>
              Mark won
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

function EditLeadDialog({
  lead,
  onClose,
}: {
  lead: Lead;
  onClose: () => void;
}) {
  const [title, setTitle] = React.useState(lead.title);
  const [value, setValue] = React.useState(
    lead.estimated_value ? String(Number(lead.estimated_value)) : "",
  );
  const amount = value.trim();
  const invalid = amount !== "" && !(Number(amount) >= 0);
  const save = useAction(
    () =>
      patch<Lead>(`/sales/leads/${lead.id}`, {
        title: title.trim(),
        estimated_value: amount ? Number(amount).toFixed(2) : null,
      }),
    { success: "Deal saved", invalidate: [["deals"]], onSuccess: onClose },
  );
  return (
    <Dialog open onOpenChange={(open) => (!open ? onClose() : null)}>
      <DialogContent title="Edit deal">
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (title.trim() && !invalid) save.mutate(undefined);
          }}
        >
          <Field label="What they want" htmlFor="lead-title">
            <Input
              id="lead-title"
              value={title}
              maxLength={200}
              onChange={(e) => setTitle(e.target.value)}
            />
          </Field>
          <Field
            label={`Estimated value (${lead.currency})`}
            htmlFor="lead-value"
            optional
            error={invalid ? "Enter an amount, e.g. 25000" : null}
          >
            <Input
              id="lead-value"
              inputMode="decimal"
              value={value}
              onChange={(e) => setValue(e.target.value)}
            />
          </Field>
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <Button type="button" variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button
              type="submit"
              loading={save.isPending}
              disabled={!title.trim() || invalid}
            >
              Save
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** What the customer did with each link pi sent: opened, accepted, changes, declined. */
function DocumentsCard({
  quoteId,
  invoiceId,
}: {
  quoteId: string | null;
  invoiceId: string | null;
}) {
  return (
    <Card>
      <CardSection>
        <SectionTitle
          icon={User}
          title="Customer"
          description="What happened to the links sent on WhatsApp"
        />
        <div className="space-y-4">
          {quoteId ? (
            <DocumentList label="Proposal" filter={{ quote_id: quoteId }} />
          ) : null}
          {invoiceId ? (
            <DocumentList label="Invoice" filter={{ invoice_id: invoiceId }} />
          ) : null}
        </div>
      </CardSection>
    </Card>
  );
}

function DocumentList({
  label,
  filter,
}: {
  label: string;
  filter: { quote_id: string } | { invoice_id: string };
}) {
  const key = useBusinessKey();
  const docs = useQuery({
    queryKey: key(["deals", "documents", filter]),
    queryFn: () => get<DealDocument[]>("/pi/deals/documents", filter),
  });
  return (
    <section>
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {label}
      </h3>
      {docs.isPending ? (
        <Skeleton className="h-12 w-full" />
      ) : docs.isError ? (
        <p className="text-sm text-muted-foreground">
          Couldn&apos;t load what the customer did.
        </p>
      ) : docs.data.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          Nothing sent on WhatsApp yet.
        </p>
      ) : (
        <ul className="space-y-3">
          {docs.data.map((d) => (
            <li
              key={d.id}
              className="space-y-1.5 border-b border-border pb-3 text-sm last:border-0 last:pb-0"
            >
              <p
                className="flex items-center gap-1.5 text-muted-foreground"
                title={dateTime(d.created_at)}
              >
                <MessageCircle className="size-3.5" aria-hidden />
                {DELIVERY[d.delivery] ?? humanize(d.delivery)} ·{" "}
                {date(d.created_at)}
              </p>
              <div className="flex flex-wrap gap-1.5">
                {d.viewed_at ? (
                  <Badge tone="info" title={dateTime(d.viewed_at)}>
                    <Eye className="size-3" aria-hidden /> Opened{" "}
                    {timeAgo(d.viewed_at)}
                  </Badge>
                ) : (
                  <Badge>Not opened yet</Badge>
                )}
                {d.response === "accepted" ? (
                  <Badge
                    tone="success"
                    title={
                      d.responded_at ? dateTime(d.responded_at) : undefined
                    }
                  >
                    <ThumbsUp className="size-3" aria-hidden /> Accepted
                  </Badge>
                ) : null}
                {d.response === "rejected" ? (
                  <Badge
                    tone="danger"
                    title={
                      d.responded_at ? dateTime(d.responded_at) : undefined
                    }
                  >
                    <ThumbsDown className="size-3" aria-hidden /> Declined
                  </Badge>
                ) : null}
                {d.response === "changes" ? (
                  <Badge
                    tone="warning"
                    title={
                      d.responded_at ? dateTime(d.responded_at) : undefined
                    }
                  >
                    Asked for changes
                  </Badge>
                ) : null}
              </div>
              {d.response_note ? (
                <p
                  className={cn(
                    "whitespace-pre-line break-words text-foreground-secondary",
                    d.response === "changes" &&
                      "rounded-md bg-warning-soft px-2.5 py-1.5",
                  )}
                  data-user-text
                >
                  {d.response === "changes"
                    ? `Asked for changes: ${d.response_note}`
                    : `“${d.response_note}”`}
                </p>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** The deal's invoice: what's due, the payment link and a receipt for each payment. */
function InvoiceCard({
  invoiceId,
  onDelivered,
}: {
  invoiceId: string;
  onDelivered: (r: Delivery) => void;
}) {
  const key = useBusinessKey();
  const can = useCan();
  const [payLink, setPayLink] = React.useState<string | null>(null);
  const invoice = useQuery({
    queryKey: key(["deals", "invoice", invoiceId]),
    queryFn: () => get<Invoice>(`/sales/billing/invoices/${invoiceId}`),
  });
  const receipts = useQuery({
    queryKey: key(["deals", "receipts", invoiceId]),
    queryFn: () =>
      get<ReceiptFile[]>(`/billing/invoices/${invoiceId}/receipts`),
  });
  const send = useAction(
    () =>
      post<PaymentLinkSent>(
        `/billing/invoices/${invoiceId}/payment-link/send`,
        {
          whatsapp: true,
          email: true,
        },
      ),
    {
      invalidate: [["deals"]],
      onSuccess: (r) => {
        setPayLink(r.pay_link);
        const parts = [r.whatsapp ? "WhatsApp" : null, r.email ? "email" : null]
          .filter(Boolean)
          .join(" and ");
        if (parts) toast.success(`Payment link sent by ${parts}`);
        if (r.email_error) toast.message(`Email not sent: ${r.email_error}`);
        if (!r.pay_link)
          toast.message(
            "No online payment is set up, so the invoice went without a pay link.",
          );
        if (r.whatsapp && r.whatsapp.delivery !== "sent")
          onDelivered(r.whatsapp);
      },
    },
  );
  const inv = invoice.data;
  const status = inv ? INVOICE_STATUS[inv.status] : null;
  const open =
    inv && ["draft", "issued", "partially_paid"].includes(inv.status);
  return (
    <Card id="deal-invoice" className="scroll-mt-24">
      <CardSection>
        <SectionTitle
          icon={Receipt}
          title="Invoice"
          description="What's due, and a receipt for every payment"
        />
        {invoice.isPending ? (
          <Skeleton className="h-24 w-full" />
        ) : invoice.isError ? (
          <ErrorState
            message={errorText(invoice.error)}
            onRetry={() => invoice.refetch()}
          />
        ) : inv ? (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-semibold">{inv.number}</span>
              {status ? (
                <Badge tone={inv.is_overdue ? "danger" : status.tone}>
                  {inv.is_overdue ? "Overdue" : status.label}
                </Badge>
              ) : (
                <Badge>{humanize(inv.status)}</Badge>
              )}
            </div>
            <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
              <div>
                <dt className="text-muted-foreground">Total</dt>
                <dd className="font-medium tabular-nums">
                  {money(inv.total, inv.currency)}
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Paid</dt>
                <dd className="tabular-nums">
                  {money(inv.amount_paid, inv.currency)}
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Still due</dt>
                <dd className="font-medium tabular-nums">
                  {money(inv.balance_due, inv.currency)}
                </dd>
              </div>
              {inv.due_date ? (
                <div>
                  <dt className="text-muted-foreground">Due</dt>
                  <dd>{date(inv.due_date)}</dd>
                </div>
              ) : null}
            </dl>
            {open && can("billing.write") ? (
              <div className="space-y-2">
                <Button
                  loading={send.isPending}
                  onClick={() => send.mutate(undefined)}
                >
                  <MessageCircle className="size-4" aria-hidden />
                  {inv.status === "draft"
                    ? "Issue and send payment link"
                    : "Send payment link"}
                </Button>
                <p className="text-xs text-muted-foreground">
                  pi sends the invoice and its pay link on WhatsApp and to the
                  customer&apos;s email. A verified payment updates this invoice
                  by itself.
                </p>
              </div>
            ) : null}
            {payLink ? (
              <Notice tone="success" title="Payment link ready">
                <span className="flex flex-wrap items-center gap-2">
                  <a
                    href={payLink}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="min-w-0 break-all underline"
                  >
                    {payLink}
                  </a>
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() =>
                      void navigator.clipboard
                        .writeText(payLink)
                        .then(() => toast.success("Link copied"))
                    }
                  >
                    <Copy className="size-4" aria-hidden /> Copy
                  </Button>
                </span>
              </Notice>
            ) : null}
          </div>
        ) : null}
        <div className="mt-5 border-t border-border pt-4">
          <h3 className="mb-2 text-sm font-semibold">Receipts</h3>
          {receipts.isPending ? (
            <Skeleton className="h-10 w-full" />
          ) : receipts.isError ? (
            <p className="text-sm text-muted-foreground">
              Couldn&apos;t load the receipts.
            </p>
          ) : receipts.data.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No payments yet. A PDF receipt is made for each one and sent to
              the customer.
            </p>
          ) : (
            <ul className="divide-y divide-border">
              {receipts.data.map((r) => (
                <li
                  key={r.id}
                  className="flex items-center gap-3 py-2 first:pt-0 last:pb-0"
                >
                  <div className="min-w-0 flex-1">
                    <a
                      href={fileDownloadUrl(r.id)}
                      className="block truncate text-sm font-medium text-accent hover:underline"
                    >
                      {r.name.replace(/\.pdf$/i, "")}
                    </a>
                    <p
                      className="text-xs text-muted-foreground"
                      title={dateTime(r.created_at)}
                    >
                      {fileSize(r.size)} · {timeAgo(r.created_at)}
                    </p>
                  </div>
                  <Button asChild variant="ghost" size="icon">
                    <a
                      href={fileDownloadUrl(r.id)}
                      aria-label={`Download ${r.name}`}
                    >
                      <Download className="size-4" aria-hidden />
                    </a>
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </CardSection>
    </Card>
  );
}
