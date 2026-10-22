"use client";

import { useState } from "react";
import Link from "next/link";
import {
  BadgeCheck,
  Banknote,
  Eye,
  FileText,
  MessageSquare,
  Pencil,
  Send,
} from "lucide-react";
import { formatDateTime, relativeTime } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Badge, Card, CardBody } from "@/components/ui/display";
import { Input, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/controls";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/overlays";
import {
  PageHeader,
  PageShell,
  RequirePermission,
} from "@/components/app/page";
import { EmptyState, ErrorState } from "@/components/app/states";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useUrlState } from "@/hooks/use-url-state";
import { useSession } from "@/features/auth/session-provider";
import {
  brainDocumentsService,
  type BrainDocument,
  type BrainPayment,
  type DocumentPatch,
} from "../brain-documents-service";
import { inboxHref } from "./lib";

const TABS = [
  { key: "review", label: "To review" },
  { key: "ready", label: "Approved or sent" },
  { key: "payments", label: "Payments" },
] as const;

const DONE_STATUSES = ["approved", "sent"];

function money(total: string | null, currency: string | null) {
  return total ? `${currency ?? ""} ${total}`.trim() : "No price yet";
}

function lines(value: unknown): string[] {
  return Array.isArray(value) ? value.map((x) => String(x)) : [];
}

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function nested(value: unknown, key: string): string {
  if (value && typeof value === "object" && key in value) {
    return text((value as Record<string, unknown>)[key]);
  }
  return "";
}

export function BrainDocumentsPage() {
  return (
    <RequirePermission permission="pi.read" area="pi">
      <BrainDocumentsView />
    </RequirePermission>
  );
}

function BrainDocumentsView() {
  const [url, setUrl] = useUrlState({ tab: "review" });
  const tab = TABS.some((t) => t.key === url.tab) ? url.tab : "review";
  const documents = useScopedQuery(["pi", "brain-documents"], () =>
    brainDocumentsService.list(),
  );
  const payments = useScopedQuery(["pi", "brain-payments"], () =>
    brainDocumentsService.payments(),
  );
  const [editing, setEditing] = useState<BrainDocument | null>(null);
  const [confirming, setConfirming] = useState<BrainPayment | null>(null);
  const all = documents.data?.items ?? [];
  const review = all.filter(
    (d) => !DONE_STATUSES.includes(d.status) && d.status !== "superseded",
  );
  const ready = all.filter((d) => DONE_STATUSES.includes(d.status));
  const claimed = (payments.data?.items ?? []).filter(
    (p) => p.status === "claimed",
  ).length;
  const shown = tab === "review" ? review : ready;
  return (
    <PageShell>
      <PageHeader
        title="Documents and payments"
        description="The solution documents and quotes pi drafted. Nothing reaches the customer until a person approves it, and only you confirm that a transfer arrived."
      />
      <div className="mb-4 flex gap-1 rounded-lg bg-surface-sunken p-1 sm:w-fit">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setUrl({ tab: t.key })}
            className={
              "flex-1 rounded-md px-3 py-1.5 text-[13px] font-medium sm:flex-none " +
              (tab === t.key
                ? "bg-surface text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground")
            }
          >
            {t.label}
            {t.key === "review" && review.length > 0 ? (
              <Badge tone="warning" className="ml-1.5">
                {review.length}
              </Badge>
            ) : null}
            {t.key === "payments" && claimed > 0 ? (
              <Badge tone="warning" className="ml-1.5">
                {claimed}
              </Badge>
            ) : null}
          </button>
        ))}
      </div>
      {tab === "payments" ? (
        <PaymentsList query={payments} onConfirm={(p) => setConfirming(p)} />
      ) : documents.isError ? (
        <ErrorState
          error={documents.error}
          onRetry={() => void documents.refetch()}
        />
      ) : documents.isPending ? (
        <div className="h-40 animate-pulse rounded-xl bg-surface-sunken" />
      ) : shown.length === 0 ? (
        <EmptyState
          icon={FileText}
          title={
            tab === "review" ? "Nothing to review" : "Nothing approved yet"
          }
          description={
            tab === "review"
              ? "When a customer says yes to a solution document and a quote, pi drafts them and they wait here for you."
              : "Approved and sent documents appear here."
          }
        />
      ) : (
        <ul className="space-y-3">
          {shown.map((d) => (
            <DocumentCard key={d.id} doc={d} onEdit={setEditing} />
          ))}
        </ul>
      )}
      <EditDialog
        key={editing?.id ?? "none"}
        doc={editing}
        onClose={() => setEditing(null)}
      />
      <ConfirmDialog
        key={confirming?.id ?? "none-payment"}
        payment={confirming}
        onClose={() => setConfirming(null)}
      />
    </PageShell>
  );
}

function DocumentCard({
  doc: d,
  onEdit,
}: {
  doc: BrainDocument;
  onEdit: (d: BrainDocument) => void;
}) {
  const { can } = useSession();
  const canEdit = can("quotes.write");
  const approve = useScopedMutation(() => brainDocumentsService.approve(d.id), {
    invalidate: [["pi", "brain-documents"]],
    success: "Approved",
  });
  const send = useScopedMutation(
    () => brainDocumentsService.send(d.offer_id ?? ""),
    {
      invalidate: [["pi", "brain-documents"]],
      success: "Queued to send on WhatsApp",
    },
  );
  const [opening, setOpening] = useState(false);
  async function preview() {
    setOpening(true);
    try {
      const blob = await brainDocumentsService.pdf(d.id);
      window.open(URL.createObjectURL(blob), "_blank", "noopener");
    } finally {
      setOpening(false);
    }
  }
  const approved = DONE_STATUSES.includes(d.status);
  return (
    <li>
      <Card>
        <CardBody className="space-y-3">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-[14px] font-semibold">
              {d.kind === "quote" ? "Quote" : "Solution document"} {d.ref}
            </span>
            <Badge tone="neutral">v{d.version}</Badge>
            <Badge
              tone={
                d.status === "sent"
                  ? "success"
                  : d.status === "approved"
                    ? "info"
                    : "warning"
              }
            >
              {d.status.replace("_", " ")}
            </Badge>
            {d.blockers.length > 0 && <Badge tone="danger">Needs fixing</Badge>}
          </div>
          <p className="text-xs text-muted-foreground">
            <span title={formatDateTime(d.created_at)}>
              Drafted {relativeTime(d.created_at)}
            </span>
            {d.kind === "quote" && <> · {money(d.total, d.currency)}</>}
            {d.valid_until && <> · valid until {d.valid_until.slice(0, 10)}</>}
          </p>
          {d.blockers.length > 0 && (
            <ul className="list-disc space-y-0.5 rounded-lg bg-surface-muted px-6 py-2 text-[13px]">
              {d.blockers.map((b) => (
                <li key={b}>{b}</li>
              ))}
            </ul>
          )}
          {d.review_notes && (
            <p className="rounded-lg bg-surface-muted px-3 py-2 text-[13px] whitespace-pre-wrap">
              {d.review_notes}
            </p>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              variant="secondary"
              loading={opening}
              onClick={() => void preview()}
            >
              <Eye /> Preview PDF
            </Button>
            {canEdit && (
              <Button size="sm" variant="secondary" onClick={() => onEdit(d)}>
                <Pencil /> {d.status === "sent" ? "New version" : "Edit"}
              </Button>
            )}
            {canEdit && !approved && (
              <Button
                size="sm"
                loading={approve.isPending}
                disabled={d.blockers.length > 0}
                onClick={() => approve.mutate(undefined)}
              >
                <BadgeCheck /> Approve
              </Button>
            )}
            {canEdit && d.status === "approved" && d.offer_id && (
              <Button
                size="sm"
                loading={send.isPending}
                onClick={() => send.mutate(undefined)}
              >
                <Send /> Send to customer
              </Button>
            )}
            <Button size="sm" variant="ghost" asChild>
              <Link href={inboxHref(d.conversation_id)}>
                <MessageSquare /> Chat
              </Link>
            </Button>
          </div>
        </CardBody>
      </Card>
    </li>
  );
}

function PaymentsList({
  query,
  onConfirm,
}: {
  query: ReturnType<typeof useScopedQuery<{ items: BrainPayment[] }>>;
  onConfirm: (p: BrainPayment) => void;
}) {
  const { can } = useSession();
  if (query.isError)
    return (
      <ErrorState error={query.error} onRetry={() => void query.refetch()} />
    );
  if (query.isPending)
    return <div className="h-40 animate-pulse rounded-xl bg-surface-sunken" />;
  const items = query.data?.items ?? [];
  if (items.length === 0)
    return (
      <EmptyState
        icon={Banknote}
        title="No payments yet"
        description="When a customer approves a quote, the bank transfer is tracked here. Confirm it only after the money arrives."
      />
    );
  return (
    <ul className="space-y-3">
      {items.map((p) => (
        <li key={p.id}>
          <Card>
            <CardBody className="space-y-2">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-[14px] font-semibold">
                  {p.quote_ref ?? "Quote"} · {money(p.total, p.currency)}
                </span>
                <Badge
                  tone={
                    p.status === "confirmed"
                      ? "success"
                      : p.status === "claimed"
                        ? "warning"
                        : "neutral"
                  }
                >
                  {p.status === "claimed"
                    ? "Customer says they paid"
                    : p.status}
                </Badge>
              </div>
              <p className="text-xs text-muted-foreground">
                {p.confirmed_at
                  ? `Confirmed ${relativeTime(p.confirmed_at)}${p.reference ? ` · ref ${p.reference}` : ""}`
                  : p.claimed_at
                    ? `Claimed ${relativeTime(p.claimed_at)}`
                    : `Waiting since ${relativeTime(p.created_at)}`}
              </p>
              <div className="flex flex-wrap gap-2">
                {p.status !== "confirmed" && can("billing.write") && (
                  <Button size="sm" onClick={() => onConfirm(p)}>
                    <Banknote /> Confirm transfer arrived
                  </Button>
                )}
                <Button size="sm" variant="ghost" asChild>
                  <Link href={inboxHref(p.conversation_id)}>
                    <MessageSquare /> Chat
                  </Link>
                </Button>
              </div>
            </CardBody>
          </Card>
        </li>
      ))}
    </ul>
  );
}

function ConfirmDialog({
  payment,
  onClose,
}: {
  payment: BrainPayment | null;
  onClose: () => void;
}) {
  const [reference, setReference] = useState("");
  const [note, setNote] = useState("");
  const confirm = useScopedMutation(
    () =>
      brainDocumentsService.confirmPayment(
        payment!.id,
        reference.trim(),
        note.trim(),
      ),
    {
      invalidate: [["pi", "brain-payments"], ["pi"]],
      success: "Confirmed. pi tells the customer.",
      onSuccess: onClose,
    },
  );
  return (
    <Dialog
      open={payment !== null}
      onOpenChange={(next) => !next && !confirm.isPending && onClose()}
    >
      <DialogContent size="md">
        <DialogHeader
          title="Confirm the transfer arrived"
          description="Only do this when the money is in the bank. pi then tells the customer and offers a kickoff time."
        />
        <DialogBody className="space-y-3">
          {payment && (
            <p className="rounded-lg bg-surface-muted px-3 py-2 text-[13px]">
              {payment.quote_ref ?? "Quote"} ·{" "}
              {money(payment.total, payment.currency)}
            </p>
          )}
          <div>
            <Label htmlFor="payment-reference">Bank reference</Label>
            <Input
              id="payment-reference"
              maxLength={120}
              value={reference}
              onChange={(e) => setReference(e.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="payment-note">Note (only your team sees it)</Label>
            <Textarea
              id="payment-note"
              rows={3}
              maxLength={1000}
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </div>
        </DialogBody>
        <DialogFooter>
          <Button
            variant="secondary"
            onClick={onClose}
            disabled={confirm.isPending}
          >
            Cancel
          </Button>
          <Button
            loading={confirm.isPending}
            onClick={() => confirm.mutate(undefined)}
          >
            Confirm payment
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function EditDialog({
  doc,
  onClose,
}: {
  doc: BrainDocument | null;
  onClose: () => void;
}) {
  const quote = doc?.kind === "quote";
  const cost = doc?.content.cost;
  const time = doc?.content.time;
  const [covers, setCovers] = useState(lines(doc?.content.covers).join("\n"));
  const [needs, setNeeds] = useState(lines(doc?.content.needs).join("\n"));
  const [included, setIncluded] = useState(
    lines(doc?.content.included).join("\n"),
  );
  const [notIncluded, setNotIncluded] = useState(
    lines(doc?.content.not_included).join("\n"),
  );
  const [total, setTotal] = useState(nested(cost, "total"));
  const [currency, setCurrency] = useState(nested(cost, "currency"));
  const [estimate, setEstimate] = useState(nested(time, "estimate"));
  const [payment, setPayment] = useState(text(doc?.content.payment));
  const [validUntil, setValidUntil] = useState(
    doc?.valid_until?.slice(0, 10) ?? "",
  );
  const [notes, setNotes] = useState(doc?.review_notes ?? "");
  const split = (v: string) =>
    v
      .split("\n")
      .map((x) => x.trim())
      .filter(Boolean);
  function patch(): DocumentPatch {
    if (!quote)
      return {
        covers: split(covers),
        needs: split(needs),
        review_notes: notes,
      };
    return {
      included: split(included),
      not_included: split(notIncluded),
      payment,
      cost: { total, currency },
      time: { estimate },
      ...(validUntil ? { valid_until: validUntil } : {}),
      review_notes: notes,
    };
  }
  const sent = doc?.status === "sent";
  const save = useScopedMutation(
    () =>
      sent
        ? brainDocumentsService.revise(doc!.id, patch())
        : brainDocumentsService.edit(doc!.id, patch()),
    {
      invalidate: [["pi", "brain-documents"]],
      success: sent ? "New version drafted" : "Saved",
      onSuccess: onClose,
    },
  );
  return (
    <Dialog
      open={doc !== null}
      onOpenChange={(next) => !next && !save.isPending && onClose()}
    >
      <DialogContent size="lg">
        <DialogHeader
          title={
            sent
              ? `New version of ${doc?.ref}`
              : `Edit ${doc?.ref ?? "document"}`
          }
          description={
            sent
              ? "This version was already sent, so your changes make a new version for review."
              : "Editing sends an approved document back to review. One item per line."
          }
        />
        <DialogBody className="space-y-3">
          {quote ? (
            <>
              <div className="grid gap-3 sm:grid-cols-3">
                <div>
                  <Label htmlFor="doc-total">Total</Label>
                  <Input
                    id="doc-total"
                    inputMode="decimal"
                    value={total}
                    onChange={(e) => setTotal(e.target.value)}
                  />
                </div>
                <div>
                  <Label htmlFor="doc-currency">Currency</Label>
                  <Input
                    id="doc-currency"
                    maxLength={3}
                    value={currency}
                    onChange={(e) => setCurrency(e.target.value.toUpperCase())}
                  />
                </div>
                <div>
                  <Label htmlFor="doc-valid">Valid until</Label>
                  <Input
                    id="doc-valid"
                    type="date"
                    value={validUntil}
                    onChange={(e) => setValidUntil(e.target.value)}
                  />
                </div>
              </div>
              <div>
                <Label htmlFor="doc-estimate">How long it takes</Label>
                <Input
                  id="doc-estimate"
                  value={estimate}
                  onChange={(e) => setEstimate(e.target.value)}
                />
              </div>
              <div>
                <Label htmlFor="doc-included">What is included</Label>
                <Textarea
                  id="doc-included"
                  rows={4}
                  value={included}
                  onChange={(e) => setIncluded(e.target.value)}
                />
              </div>
              <div>
                <Label htmlFor="doc-not-included">What is not included</Label>
                <Textarea
                  id="doc-not-included"
                  rows={3}
                  value={notIncluded}
                  onChange={(e) => setNotIncluded(e.target.value)}
                />
              </div>
              <div>
                <Label htmlFor="doc-payment">How payment works</Label>
                <Textarea
                  id="doc-payment"
                  rows={3}
                  value={payment}
                  onChange={(e) => setPayment(e.target.value)}
                />
              </div>
            </>
          ) : (
            <>
              <div>
                <Label htmlFor="doc-covers">What it covers</Label>
                <Textarea
                  id="doc-covers"
                  rows={5}
                  value={covers}
                  onChange={(e) => setCovers(e.target.value)}
                />
              </div>
              <div>
                <Label htmlFor="doc-needs">What Workzap needs from them</Label>
                <Textarea
                  id="doc-needs"
                  rows={4}
                  value={needs}
                  onChange={(e) => setNeeds(e.target.value)}
                />
              </div>
            </>
          )}
          <div>
            <Label htmlFor="doc-notes">
              Review notes (only your team sees them)
            </Label>
            <Textarea
              id="doc-notes"
              rows={2}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </div>
        </DialogBody>
        <DialogFooter>
          <Button
            variant="secondary"
            onClick={onClose}
            disabled={save.isPending}
          >
            Cancel
          </Button>
          <Button
            loading={save.isPending}
            onClick={() => save.mutate(undefined)}
          >
            {sent ? "Create new version" : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
