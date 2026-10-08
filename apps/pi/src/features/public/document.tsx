"use client";

/**
 * The page a customer opens from WhatsApp to read a proposal or an invoice, accept the
 * proposal, ask for changes, or pay. No sign-in: the link's token is the credential
 * (see app/modules/pi_saas/deal_routes.py).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  CreditCard,
  FileText,
  MessageSquare,
  XCircle,
} from "lucide-react";
import * as React from "react";

import { Wordmark } from "@/components/brand";
import {
  Badge,
  Button,
  Card,
  CardSection,
  ErrorState,
  Field,
  LoadingBlock,
  Notice,
  Textarea,
} from "@/components/ui";
import { errorText } from "@/lib/api";
import { date, money } from "@/lib/format";
import { publicGet, publicPost } from "@/lib/public-api";

interface Line {
  description: string;
  quantity: string;
  unit_price: string;
  discount: string;
  line_total: string;
}

interface DocumentView {
  kind: "proposal" | "invoice";
  business: string;
  customer: string;
  number: string;
  status: string;
  currency: string;
  lines: Line[];
  subtotal: string;
  discount_total: string;
  tax_total: string;
  total: string;
  amount_paid?: string;
  valid_until?: string;
  issue_date?: string | null;
  due_date?: string | null;
  notes: string;
  pay_link?: string | null;
  response: "accepted" | "changes" | "rejected" | null;
  can_respond: boolean;
}

const quantity = (value: string) => {
  const n = Number(value);
  return Number.isInteger(n) ? String(n) : value;
};

export function DocumentPage({ token }: { token: string }) {
  const client = useQueryClient();
  const key = ["pi-document", token];
  const doc = useQuery({
    queryKey: key,
    queryFn: () => publicGet<DocumentView>(`/docs/${token}`),
    retry: false,
  });
  const [mode, setMode] = React.useState<"changes" | "rejected" | null>(null);
  const [note, setNote] = React.useState("");
  const answer = useMutation({
    mutationFn: (action: "accepted" | "changes" | "rejected") =>
      publicPost<DocumentView>(`/docs/${token}/respond`, { action, note }),
    onSuccess: (view) => {
      client.setQueryData(key, view);
      setMode(null);
    },
  });

  return (
    <div className="mx-auto flex min-h-dvh max-w-2xl flex-col gap-6 px-4 py-8 sm:py-12">
      <div className="flex items-center justify-between">
        <Wordmark className="text-xl" />
        <span className="text-xs text-muted-foreground">Secure document</span>
      </div>
      {doc.isPending ? (
        <LoadingBlock />
      ) : doc.isError ? (
        <ErrorState message="This link isn't available. It may have expired: ask the business on WhatsApp for a new one." />
      ) : (
        <Document
          view={doc.data}
          mode={mode}
          setMode={setMode}
          note={note}
          setNote={setNote}
          answer={(action) => answer.mutate(action)}
          busy={answer.isPending}
          error={answer.isError ? errorText(answer.error) : null}
        />
      )}
    </div>
  );
}

function Document({
  view,
  mode,
  setMode,
  note,
  setNote,
  answer,
  busy,
  error,
}: {
  view: DocumentView;
  mode: "changes" | "rejected" | null;
  setMode: (m: "changes" | "rejected" | null) => void;
  note: string;
  setNote: (v: string) => void;
  answer: (action: "accepted" | "changes" | "rejected") => void;
  busy: boolean;
  error: string | null;
}) {
  const proposal = view.kind === "proposal";
  const due =
    view.amount_paid !== undefined
      ? (Number(view.total) - Number(view.amount_paid)).toFixed(2)
      : view.total;
  return (
    <>
      <Card>
        <CardSection className="space-y-1">
          <p className="text-sm text-muted-foreground">
            {proposal ? "Proposal" : "Invoice"} from
          </p>
          <h1 className="text-2xl font-semibold">{view.business}</h1>
          <div className="flex flex-wrap items-center gap-2 pt-1 text-sm text-muted-foreground">
            <span className="inline-flex items-center gap-1">
              <FileText className="size-4" aria-hidden /> {view.number}
            </span>
            <span>for {view.customer}</span>
            <StatusBadge view={view} />
          </div>
        </CardSection>
      </Card>

      {view.response === "accepted" ? (
        <Notice tone="success" title="Accepted. Thank you!">
          The business has been told. Your order and invoice follow on WhatsApp.
        </Notice>
      ) : view.response === "changes" ? (
        <Notice tone="info" title="Changes asked">
          The business will send you an updated proposal on WhatsApp.
        </Notice>
      ) : view.response === "rejected" ? (
        <Notice tone="info" title="Declined">
          Thanks for letting them know.
        </Notice>
      ) : null}

      <Card>
        <CardSection>
          <ul className="divide-y divide-border">
            {view.lines.map((line, i) => (
              <li key={i} className="flex items-start gap-3 py-3 first:pt-0">
                <div className="min-w-0 flex-1">
                  <p className="font-medium">{line.description}</p>
                  <p className="text-sm text-muted-foreground">
                    {quantity(line.quantity)} ×{" "}
                    {money(line.unit_price, view.currency)}
                    {Number(line.discount) > 0
                      ? ` − ${money(line.discount, view.currency)}`
                      : ""}
                  </p>
                </div>
                <p className="shrink-0 font-medium tabular-nums">
                  {money(line.line_total, view.currency)}
                </p>
              </li>
            ))}
          </ul>
          <dl className="mt-4 space-y-1.5 border-t border-border pt-4 text-sm">
            {Number(view.discount_total) > 0 ? (
              <Row
                label="Discount"
                value={`− ${money(view.discount_total, view.currency)}`}
              />
            ) : null}
            {Number(view.tax_total) > 0 ? (
              <Row label="Tax" value={money(view.tax_total, view.currency)} />
            ) : null}
            <Row
              label="Total"
              value={money(view.total, view.currency)}
              strong
            />
            {!proposal && Number(view.amount_paid ?? 0) > 0 ? (
              <>
                <Row
                  label="Paid"
                  value={money(view.amount_paid ?? "0", view.currency)}
                />
                <Row
                  label="Still due"
                  value={money(due, view.currency)}
                  strong
                />
              </>
            ) : null}
          </dl>
          {view.notes ? (
            <p className="mt-4 whitespace-pre-line rounded-lg bg-surface-muted p-3 text-sm text-muted-foreground">
              {view.notes}
            </p>
          ) : null}
          <p className="mt-4 text-xs text-muted-foreground">
            {proposal && view.valid_until
              ? `Valid until ${date(view.valid_until)}`
              : view.due_date
                ? `Due ${date(view.due_date)}`
                : ""}
          </p>
        </CardSection>
      </Card>

      {proposal && view.can_respond ? (
        <Card>
          <CardSection className="space-y-3">
            {error ? <Notice tone="danger">{error}</Notice> : null}
            {mode ? (
              <>
                <Field
                  label={
                    mode === "changes"
                      ? "What would you like changed?"
                      : "Anything you'd like to tell them? (optional)"
                  }
                  htmlFor="answer-note"
                >
                  <Textarea
                    id="answer-note"
                    rows={3}
                    maxLength={2000}
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                  />
                </Field>
                <div className="flex flex-col gap-2 sm:flex-row">
                  <Button
                    className="sm:flex-1"
                    loading={busy}
                    disabled={mode === "changes" && !note.trim()}
                    onClick={() => answer(mode)}
                  >
                    {mode === "changes"
                      ? "Send my changes"
                      : "Decline proposal"}
                  </Button>
                  <Button variant="ghost" onClick={() => setMode(null)}>
                    Back
                  </Button>
                </div>
              </>
            ) : (
              <>
                <Button
                  size="lg"
                  className="w-full"
                  loading={busy}
                  onClick={() => answer("accepted")}
                >
                  <CheckCircle2 className="size-5" aria-hidden /> Accept
                  proposal
                </Button>
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  <Button
                    variant="secondary"
                    onClick={() => setMode("changes")}
                  >
                    <MessageSquare className="size-4" aria-hidden /> Ask for
                    changes
                  </Button>
                  <Button variant="ghost" onClick={() => setMode("rejected")}>
                    <XCircle className="size-4" aria-hidden /> Not now
                  </Button>
                </div>
              </>
            )}
          </CardSection>
        </Card>
      ) : null}

      {!proposal && view.pay_link ? (
        <Button asChild size="lg" className="w-full">
          <a href={view.pay_link}>
            <CreditCard className="size-5" aria-hidden /> Pay{" "}
            {money(due, view.currency)}
          </a>
        </Button>
      ) : null}
    </>
  );
}

function StatusBadge({ view }: { view: DocumentView }) {
  const label =
    view.kind === "invoice"
      ? {
          issued: "Unpaid",
          partially_paid: "Part paid",
          paid: "Paid",
          void: "Cancelled",
        }[view.status]
      : {
          sent: "Waiting for you",
          accepted: "Accepted",
          rejected: "Closed",
          expired: "Expired",
        }[view.status];
  const tone =
    view.status === "paid" || view.status === "accepted"
      ? "success"
      : view.status === "sent" || view.status === "issued"
        ? "accent"
        : "neutral";
  return label ? <Badge tone={tone}>{label}</Badge> : null;
}

function Row({
  label,
  value,
  strong,
}: {
  label: string;
  value: string;
  strong?: boolean;
}) {
  return (
    <div
      className={`flex justify-between gap-3 ${strong ? "text-base font-semibold" : ""}`}
    >
      <dt className={strong ? "" : "text-muted-foreground"}>{label}</dt>
      <dd className="tabular-nums">{value}</dd>
    </div>
  );
}
