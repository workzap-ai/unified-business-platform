"use client";

/**
 * Deals: every enquiry from interest to paid, with what each one needs next.
 *
 *   New → Qualified (brief confirmed) → Proposal (sent on WhatsApp) → Won / Lost
 *
 * The team prices a proposal (lines come from pi's brief) and pi sends it on WhatsApp.
 * When the customer accepts on the proposal page, the order, invoice and payment link
 * follow by themselves (see "Automation"). A deal can also start from just a WhatsApp
 * number. API: app/modules/pi_saas/deal_routes.py.
 */
import { useQuery } from "@tanstack/react-query";
import {
  Copy,
  ExternalLink,
  FileText,
  MessageCircle,
  Plus,
  Receipt,
  Send,
  Settings2,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import {
  Badge,
  Button,
  Card,
  CardSection,
  Dialog,
  DialogContent,
  EmptyState,
  ErrorState,
  Field,
  Input,
  Notice,
  PageHeader,
  Select,
  Skeleton,
  Switch,
} from "@/components/ui";
import { ApiError, errorText, get, patch, post, put } from "@/lib/api";
import { cn } from "@/lib/cn";
import { date, money } from "@/lib/format";
import { useAction, useBusinessKey, useCan } from "@/lib/session";

type Stage = "new" | "qualified" | "proposal" | "won" | "lost";

interface Deal {
  id: string;
  title: string;
  stage: Stage;
  source: string;
  updated_at: string;
  conversation_id: string | null;
  customer: { id: string; name: string; phone: string | null } | null;
  proposal: {
    id: string;
    number: string;
    status: string;
    total: string;
    currency: string;
    delivery: "sent" | "waiting" | "manual" | "pending" | "failed" | null;
    viewed: boolean;
    response: "accepted" | "changes" | "rejected" | null;
  } | null;
  invoice: {
    id: string;
    number: string;
    status: string;
    total: string;
    amount_paid: string;
    currency: string;
  } | null;
  next: string;
}

interface Board {
  items: Deal[];
  counts: Partial<Record<Stage, number>>;
}

interface Delivery {
  delivery: "sent" | "waiting" | "manual" | "pending" | "failed";
  link: string;
  share: string | null;
  message: string;
}

interface QuoteDetail {
  id: string;
  number: string;
  status: string;
  currency: string;
  total: string;
  lines: { description: string; quantity: string; unit_price: string }[];
}

interface DealSettings {
  auto_proposal: boolean;
  auto_followups: boolean;
  auto_order: boolean;
  auto_invoice: boolean;
  auto_payment_request: boolean;
  thank_you_on_paid: boolean;
  payment_method: string;
  template_name: string;
  template_language: string;
}

const STAGES: { key: Stage; label: string; tone: string }[] = [
  { key: "new", label: "New", tone: "bg-info-soft text-info" },
  { key: "qualified", label: "Qualified", tone: "bg-accent-soft text-accent" },
  {
    key: "proposal",
    label: "Proposal sent",
    tone: "bg-warning-soft text-warning",
  },
  { key: "won", label: "Won", tone: "bg-success-soft text-success" },
  {
    key: "lost",
    label: "Lost",
    tone: "bg-surface-muted text-foreground-secondary",
  },
];

const DELIVERY: Record<string, string> = {
  sent: "Sent on WhatsApp",
  waiting: "Waiting for their reply on WhatsApp",
  manual: "Share the link yourself",
  pending: "Not sent yet",
  failed: "Couldn't send",
};

export function DealsPage() {
  const key = useBusinessKey();
  const can = useCan();
  const board = useQuery({
    queryKey: key(["deals", "board"]),
    queryFn: () => get<Board>("/pi/deals/board"),
  });
  const [filter, setFilter] = React.useState<Stage | "open">("open");
  const [starting, setStarting] = React.useState(false);
  const [settings, setSettings] = React.useState(false);
  const [editing, setEditing] = React.useState<{
    deal: Deal;
    quoteId: string;
  } | null>(null);
  const [result, setResult] = React.useState<Delivery | null>(null);
  const write = can("sales.write");

  const makeProposal = useAction(
    (deal: Deal) =>
      post<{ quote_id: string }>(`/pi/deals/leads/${deal.id}/proposal`).then(
        (r) => ({
          deal,
          quoteId: r.quote_id,
        }),
      ),
    { invalidate: [["deals"]], onSuccess: (r) => setEditing(r) },
  );
  const sendInvoice = useAction(
    (deal: Deal) =>
      post<Delivery>(`/pi/deals/invoices/${deal.invoice?.id}/send`),
    { invalidate: [["deals"]], onSuccess: setResult },
  );
  const resend = useAction(
    (deal: Deal) =>
      post<Delivery>(`/pi/deals/quotes/${deal.proposal?.id}/send`),
    { invalidate: [["deals"]], onSuccess: setResult },
  );

  const items = (board.data?.items ?? []).filter((d) =>
    filter === "open"
      ? ["new", "qualified", "proposal"].includes(d.stage)
      : d.stage === filter,
  );

  return (
    <div>
      <PageHeader
        title="Deals"
        description="Every enquiry from interest to paid. pi sends proposals and invoices on WhatsApp; you set the prices."
        action={
          write ? (
            <div className="flex gap-2">
              <Button variant="secondary" onClick={() => setSettings(true)}>
                <Settings2 className="size-4" aria-hidden />
                <span className="hidden sm:inline">Automation</span>
              </Button>
              <Button onClick={() => setStarting(true)}>
                <Plus className="size-4" aria-hidden /> New deal
              </Button>
            </div>
          ) : null
        }
      />

      <div className="mb-4 grid grid-cols-3 gap-2 sm:grid-cols-6">
        <StageTile
          label="Open"
          count={
            (board.data?.counts.new ?? 0) +
            (board.data?.counts.qualified ?? 0) +
            (board.data?.counts.proposal ?? 0)
          }
          active={filter === "open"}
          onClick={() => setFilter("open")}
          tone="bg-surface text-foreground"
        />
        {STAGES.map((s) => (
          <StageTile
            key={s.key}
            label={s.label}
            count={board.data?.counts[s.key] ?? 0}
            active={filter === s.key}
            onClick={() => setFilter(s.key)}
            tone={s.tone}
          />
        ))}
      </div>

      {board.isPending ? (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-28 w-full" />
          ))}
        </div>
      ) : board.isError ? (
        <ErrorState
          message={errorText(board.error)}
          onRetry={() => board.refetch()}
        />
      ) : items.length === 0 ? (
        <EmptyState
          title={filter === "open" ? "No open deals" : "Nothing here yet"}
        >
          Deals appear when customers ask about your work on WhatsApp, or when
          you start one from a number.
        </EmptyState>
      ) : (
        <ul className="space-y-3">
          {items.map((deal) => (
            <li key={deal.id}>
              <DealCard
                deal={deal}
                write={write}
                busy={
                  (makeProposal.isPending &&
                    makeProposal.variables?.id === deal.id) ||
                  (sendInvoice.isPending &&
                    sendInvoice.variables?.id === deal.id) ||
                  (resend.isPending && resend.variables?.id === deal.id)
                }
                onPropose={() =>
                  deal.proposal && deal.proposal.status === "draft"
                    ? setEditing({ deal, quoteId: deal.proposal.id })
                    : makeProposal.mutate(deal)
                }
                onResend={() => resend.mutate(deal)}
                onInvoice={() => sendInvoice.mutate(deal)}
              />
            </li>
          ))}
        </ul>
      )}

      <StartDealDialog open={starting} onOpenChange={setStarting} />
      <SettingsDialog open={settings} onOpenChange={setSettings} />
      {editing ? (
        <ProposalDialog
          deal={editing.deal}
          quoteId={editing.quoteId}
          onClose={() => setEditing(null)}
          onSent={(r) => {
            setEditing(null);
            setResult(r);
          }}
        />
      ) : null}
      <DeliveryDialog result={result} onClose={() => setResult(null)} />
    </div>
  );
}

function StageTile({
  label,
  count,
  active,
  onClick,
  tone,
}: {
  label: string;
  count: number;
  active: boolean;
  onClick: () => void;
  tone: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "min-w-0 rounded-xl border px-3 py-2 text-left transition-colors",
        active
          ? "border-accent ring-2 ring-accent/30"
          : "border-border hover:border-accent/40",
        tone,
      )}
    >
      <span className="block text-xl font-semibold tabular-nums">{count}</span>
      <span className="block truncate text-xs font-medium">{label}</span>
    </button>
  );
}

function DealCard({
  deal,
  write,
  busy,
  onPropose,
  onResend,
  onInvoice,
}: {
  deal: Deal;
  write: boolean;
  busy: boolean;
  onPropose: () => void;
  onResend: () => void;
  onInvoice: () => void;
}) {
  const stage = STAGES.find((s) => s.key === deal.stage);
  const p = deal.proposal;
  const inv = deal.invoice;
  const needsProposal =
    ["new", "qualified"].includes(deal.stage) &&
    (!p || ["draft", "rejected", "expired", "cancelled"].includes(p.status));
  const canResend = p && ["sent", "approved"].includes(p.status);
  const canInvoice = inv && ["issued", "partially_paid"].includes(inv.status);
  return (
    <Card>
      <CardSection className="space-y-3">
        <div className="flex flex-wrap items-start gap-2">
          <div className="min-w-0 flex-1">
            <p className="truncate font-semibold">{deal.title}</p>
            <p className="truncate text-sm text-muted-foreground">
              {deal.customer?.name ?? "No customer"}
              {deal.customer?.phone ? ` · ${deal.customer.phone}` : ""} ·{" "}
              {date(deal.updated_at)}
            </p>
          </div>
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
        </div>
        <div className="flex flex-wrap gap-1.5 text-xs">
          {p ? (
            <Badge tone="neutral">
              <FileText className="size-3.5" aria-hidden /> {p.number} ·{" "}
              {money(p.total, p.currency)}
            </Badge>
          ) : null}
          {p?.delivery ? (
            <Badge tone="info">{DELIVERY[p.delivery]}</Badge>
          ) : null}
          {p?.viewed && !p.response ? (
            <Badge tone="accent">Opened</Badge>
          ) : null}
          {p?.response === "accepted" ? (
            <Badge tone="success">Accepted</Badge>
          ) : null}
          {p?.response === "changes" ? (
            <Badge tone="warning">Asked for changes</Badge>
          ) : null}
          {p?.response === "rejected" ? (
            <Badge tone="neutral">Declined</Badge>
          ) : null}
          {inv ? (
            <Badge tone={inv.status === "paid" ? "success" : "warning"}>
              <Receipt className="size-3.5" aria-hidden /> {inv.number} ·{" "}
              {inv.status === "paid"
                ? "Paid"
                : `${money(
                    (Number(inv.total) - Number(inv.amount_paid)).toFixed(2),
                    inv.currency,
                  )} due`}
            </Badge>
          ) : null}
        </div>
        <div className="flex flex-col gap-2 rounded-lg bg-surface-muted px-3 py-2 sm:flex-row sm:items-center">
          <p className="min-w-0 flex-1 text-sm">
            <span className="text-muted-foreground">Next: </span>
            <span className="font-medium">{deal.next}</span>
          </p>
          <div className="flex flex-wrap gap-2">
            {deal.conversation_id ? (
              <Button asChild variant="ghost" size="sm">
                <Link href={`/inbox?conversation=${deal.conversation_id}`}>
                  <MessageCircle className="size-4" aria-hidden /> Chat
                </Link>
              </Button>
            ) : null}
            {write && needsProposal ? (
              <Button size="sm" loading={busy} onClick={onPropose}>
                <FileText className="size-4" aria-hidden />
                {p?.status === "draft" ? "Finish proposal" : "Make proposal"}
              </Button>
            ) : null}
            {write && canResend ? (
              <Button
                size="sm"
                variant="secondary"
                loading={busy}
                onClick={onResend}
              >
                <Send className="size-4" aria-hidden /> Resend
              </Button>
            ) : null}
            {write && canInvoice ? (
              <Button
                size="sm"
                variant="secondary"
                loading={busy}
                onClick={onInvoice}
              >
                <Receipt className="size-4" aria-hidden /> Send invoice
              </Button>
            ) : null}
          </div>
        </div>
      </CardSection>
    </Card>
  );
}

interface EditLine {
  description: string;
  quantity: string;
  unit_price: string;
}

function ProposalDialog({
  deal,
  quoteId,
  onClose,
  onSent,
}: {
  deal: Deal;
  quoteId: string;
  onClose: () => void;
  onSent: (r: Delivery) => void;
}) {
  const key = useBusinessKey();
  const quote = useQuery({
    queryKey: key(["deals", "quote", quoteId]),
    queryFn: () => get<QuoteDetail>(`/quotes/${quoteId}`),
  });
  const [lines, setLines] = React.useState<EditLine[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState<"save" | "send" | null>(null);
  const current: EditLine[] =
    lines ??
    quote.data?.lines.map((l) => ({
      description: l.description,
      quantity: String(Number(l.quantity)),
      unit_price: Number(l.unit_price) ? String(Number(l.unit_price)) : "",
    })) ??
    [];
  const currency = quote.data?.currency ?? "";
  const total = current.reduce(
    (sum, l) => sum + (Number(l.quantity) || 0) * (Number(l.unit_price) || 0),
    0,
  );
  const ready =
    current.length > 0 &&
    current.every(
      (l) =>
        l.description.trim() &&
        Number(l.quantity) > 0 &&
        Number(l.unit_price) > 0,
    );

  function update(i: number, field: keyof EditLine, value: string) {
    setLines(current.map((l, n) => (n === i ? { ...l, [field]: value } : l)));
  }

  async function save(andSend: boolean) {
    setError(null);
    setBusy(andSend ? "send" : "save");
    try {
      await patch(`/quotes/${quoteId}`, {
        lines: current.map((l) => ({
          description: l.description.trim(),
          quantity: String(Number(l.quantity)),
          unit_price: Number(l.unit_price).toFixed(2),
        })),
      });
      if (andSend) {
        onSent(await post<Delivery>(`/pi/deals/quotes/${quoteId}/send`));
      } else {
        toast.success("Proposal saved");
        onClose();
      }
    } catch (e) {
      setError(
        e instanceof ApiError && e.code === "QUOTE_NEEDS_APPROVAL"
          ? "Saved. A manager needs to approve this proposal before it can be sent."
          : errorText(e),
      );
    } finally {
      setBusy(null);
    }
  }

  return (
    <Dialog open onOpenChange={(open) => (!open ? onClose() : null)}>
      <DialogContent
        title={`Proposal for ${deal.customer?.name ?? deal.title}`}
        description="pi filled the lines from the brief. Set the prices, then send it on WhatsApp."
      >
        {quote.isPending ? (
          <Skeleton className="h-40 w-full" />
        ) : quote.isError ? (
          <ErrorState message={errorText(quote.error)} />
        ) : (
          <div className="space-y-4">
            {error ? <Notice tone="warning">{error}</Notice> : null}
            <ul className="space-y-3">
              {current.map((line, i) => (
                <li
                  key={i}
                  className="space-y-2 rounded-lg border border-border p-3"
                >
                  <Input
                    aria-label={`Line ${i + 1} description`}
                    value={line.description}
                    maxLength={300}
                    onChange={(e) => update(i, "description", e.target.value)}
                  />
                  <div className="grid grid-cols-[5rem_1fr_auto] items-center gap-2">
                    <Input
                      aria-label={`Line ${i + 1} quantity`}
                      inputMode="decimal"
                      value={line.quantity}
                      onChange={(e) => update(i, "quantity", e.target.value)}
                    />
                    <Input
                      aria-label={`Line ${i + 1} price`}
                      inputMode="decimal"
                      placeholder={`Price (${currency})`}
                      value={line.unit_price}
                      onChange={(e) => update(i, "unit_price", e.target.value)}
                    />
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`Remove line ${i + 1}`}
                      disabled={current.length === 1}
                      onClick={() =>
                        setLines(current.filter((_, n) => n !== i))
                      }
                    >
                      <Trash2 className="size-4" aria-hidden />
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
            <Button
              variant="ghost"
              size="sm"
              onClick={() =>
                setLines([
                  ...current,
                  { description: "", quantity: "1", unit_price: "" },
                ])
              }
            >
              <Plus className="size-4" aria-hidden /> Add a line
            </Button>
            <div className="flex items-center justify-between border-t border-border pt-3">
              <span className="text-sm text-muted-foreground">
                Total before tax
              </span>
              <span className="text-lg font-semibold tabular-nums">
                {money(total.toFixed(2), currency || "PKR")}
              </span>
            </div>
            <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
              <Button
                variant="ghost"
                loading={busy === "save"}
                disabled={!ready || busy !== null}
                onClick={() => void save(false)}
              >
                Save draft
              </Button>
              <Button
                loading={busy === "send"}
                disabled={!ready || busy !== null}
                onClick={() => void save(true)}
              >
                <Send className="size-4" aria-hidden /> Save and send on
                WhatsApp
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function DeliveryDialog({
  result,
  onClose,
}: {
  result: Delivery | null;
  onClose: () => void;
}) {
  return (
    <Dialog
      open={Boolean(result)}
      onOpenChange={(open) => (!open ? onClose() : null)}
    >
      {result ? (
        <DialogContent
          title={
            result.delivery === "sent"
              ? "Sent on WhatsApp"
              : result.delivery === "waiting"
                ? "Waiting for their reply"
                : "Share it yourself"
          }
          description={
            result.delivery === "sent"
              ? "pi posted it in their WhatsApp chat."
              : result.delivery === "waiting"
                ? "They haven't written in 24 hours, so pi sent your approved template. The link goes out the moment they reply."
                : "WhatsApp doesn't let pi message them first. Send it from your own WhatsApp in one tap."
          }
        >
          <div className="space-y-3">
            <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-lg bg-surface-muted p-3 text-sm">
              {result.message}
            </pre>
            <div className="flex flex-col gap-2 sm:flex-row">
              {result.share && result.delivery !== "sent" ? (
                <Button asChild>
                  <a href={result.share} target="_blank" rel="noreferrer">
                    <MessageCircle className="size-4" aria-hidden /> Open in
                    WhatsApp
                  </a>
                </Button>
              ) : null}
              <Button
                variant="secondary"
                onClick={() =>
                  void navigator.clipboard
                    .writeText(result.link)
                    .then(() => toast.success("Link copied"))
                }
              >
                <Copy className="size-4" aria-hidden /> Copy link
              </Button>
              <Button asChild variant="ghost">
                <a href={result.link} target="_blank" rel="noreferrer">
                  <ExternalLink className="size-4" aria-hidden /> Preview
                </a>
              </Button>
            </div>
          </div>
        </DialogContent>
      ) : null}
    </Dialog>
  );
}

function StartDealDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [phone, setPhone] = React.useState("");
  const [name, setName] = React.useState("");
  const [title, setTitle] = React.useState("");
  const start = useAction(
    () => post<{ lead_id: string }>("/pi/deals/start", { phone, name, title }),
    {
      success: "Deal started",
      invalidate: [["deals"]],
      onSuccess: () => {
        setPhone("");
        setName("");
        setTitle("");
        onOpenChange(false);
      },
    },
  );
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        title="New deal"
        description="Start from a WhatsApp number, even if they haven't messaged you yet."
      >
        <div className="space-y-4">
          <Field
            label="WhatsApp number"
            htmlFor="deal-phone"
            hint="With country code, e.g. +92 300 1234567"
          >
            <Input
              id="deal-phone"
              inputMode="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
            />
          </Field>
          <Field label="Name" htmlFor="deal-name">
            <Input
              id="deal-name"
              value={name}
              maxLength={160}
              onChange={(e) => setName(e.target.value)}
            />
          </Field>
          <Field label="What they want" htmlFor="deal-title">
            <Input
              id="deal-title"
              placeholder="e.g. Logo and website"
              value={title}
              maxLength={200}
              onChange={(e) => setTitle(e.target.value)}
            />
          </Field>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button
              loading={start.isPending}
              disabled={phone.replace(/\D/g, "").length < 8}
              onClick={() => start.mutate(undefined)}
            >
              Start deal
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function SettingsDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const key = useBusinessKey();
  const current = useQuery({
    queryKey: key(["deals", "settings"]),
    queryFn: () => get<DealSettings>("/pi/deals/settings"),
    enabled: open,
  });
  const [draft, setDraft] = React.useState<DealSettings | null>(null);
  const value = draft ?? current.data ?? null;
  const save = useAction(
    // Only the saved fields: the settings read also lists the payment methods.
    (body: DealSettings) =>
      put("/pi/deals/settings", {
        auto_proposal: body.auto_proposal ?? true,
        auto_followups: body.auto_followups ?? true,
        auto_order: body.auto_order,
        auto_invoice: body.auto_invoice,
        auto_payment_request: body.auto_payment_request,
        thank_you_on_paid: body.thank_you_on_paid,
        payment_method: body.payment_method,
        template_name: body.template_name,
        template_language: body.template_language,
      }),
    {
      success: "Automation saved",
      invalidate: [["deals"]],
      onSuccess: () => {
        setDraft(null);
        onOpenChange(false);
      },
    },
  );
  const set = <K extends keyof DealSettings>(k: K, v: DealSettings[K]) =>
    value && setDraft({ ...value, [k]: v });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        title="Automation"
        description="What pi does by itself, from the confirmed brief to the payment."
      >
        {!value ? (
          <Skeleton className="h-48 w-full" />
        ) : (
          <div className="space-y-4">
            <Switch
              id="auto-proposal"
              label="Make and send the proposal when they confirm the brief"
              checked={value.auto_proposal ?? true}
              onCheckedChange={(v) => set("auto_proposal", v)}
            />
            <p className="-mt-2 text-xs text-muted-foreground">
              pi uses your catalog prices. Anything without a price waits for
              you.
            </p>
            <Switch
              id="auto-followups"
              label="Remind the customer when a deal goes quiet"
              checked={value.auto_followups ?? true}
              onCheckedChange={(v) => set("auto_followups", v)}
            />
            <p className="-mt-2 text-xs text-muted-foreground">
              Proposal unopened (2 days) or unanswered (3 days), invoice due
              tomorrow or overdue. Once each.
            </p>
            <Switch
              id="auto-order"
              label="Confirm the order when they accept"
              checked={value.auto_order}
              onCheckedChange={(v) => set("auto_order", v)}
            />
            <Switch
              id="auto-invoice"
              label="Issue the invoice"
              checked={value.auto_invoice}
              disabled={!value.auto_order}
              onCheckedChange={(v) => set("auto_invoice", v)}
            />
            <Switch
              id="auto-pay"
              label="Send the payment link on WhatsApp"
              checked={value.auto_payment_request}
              disabled={!value.auto_order}
              onCheckedChange={(v) => set("auto_payment_request", v)}
            />
            <Switch
              id="thank-you"
              label="Thank them when they pay"
              checked={value.thank_you_on_paid}
              onCheckedChange={(v) => set("thank_you_on_paid", v)}
            />
            <Field label="Payment method in the link" htmlFor="pay-method">
              <Select
                id="pay-method"
                value={value.payment_method}
                onChange={(e) => set("payment_method", e.target.value)}
              >
                <option value="auto">
                  Best available (card, then bank, wallet, cash)
                </option>
                <option value="stripe">Card (Stripe)</option>
                <option value="bank_transfer">Bank transfer</option>
                <option value="mobile_wallet">Mobile wallet</option>
                <option value="cash">Cash</option>
              </Select>
            </Field>
            <div className="space-y-2 rounded-lg border border-border p-3">
              <p className="text-sm font-medium">
                Customers who haven&apos;t written in 24 hours
              </p>
              <p className="text-xs text-muted-foreground">
                WhatsApp only allows an approved template then. Add one with no
                variables, e.g. &ldquo;Your document is ready. Reply to this
                message to see it.&rdquo; Leave empty to share links yourself.
              </p>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-[1fr_8rem]">
                <Input
                  aria-label="Template name"
                  placeholder="document_ready"
                  value={value.template_name}
                  onChange={(e) => set("template_name", e.target.value.trim())}
                />
                <Input
                  aria-label="Template language"
                  placeholder="en"
                  value={value.template_language}
                  onChange={(e) =>
                    set("template_language", e.target.value.trim())
                  }
                />
              </div>
            </div>
            {save.isError ? (
              <Notice tone="danger">{errorText(save.error)}</Notice>
            ) : null}
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button
                loading={save.isPending}
                onClick={() => save.mutate(value)}
              >
                Save
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
