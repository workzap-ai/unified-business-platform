"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Banknote,
  Building2,
  CheckCircle2,
  FileText,
  Receipt,
  Upload,
} from "lucide-react";
import * as React from "react";
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
  Select,
  Textarea,
} from "@/components/ui";
import { errorText, get, post } from "@/lib/api";
import { date, money } from "@/lib/format";
import { useAction, useBusinessKey, useCan } from "@/lib/session";
import type { BillingView } from "@/lib/types";

interface Payment {
  id: string;
  plan: string;
  plan_name: string;
  method: "bank_transfer" | "cash";
  status:
    | "awaiting_payment"
    | "submitted"
    | "approved"
    | "rejected"
    | "cancelled"
    | "refunded";
  amount: string;
  currency: string;
  months: number;
  instructions: Record<string, string>;
  payer_name: string;
  reference: string;
  paid_on: string | null;
  note: string;
  has_proof: boolean;
  review_note: string;
  receipt_number: string | null;
  period_start: string | null;
  period_end: string | null;
  created_at: string;
  refund_reference: string | null;
  refund_reason: string | null;
}

const STATUS: Record<Payment["status"], string> = {
  awaiting_payment: "Awaiting payment",
  submitted: "Under review",
  approved: "Verified",
  rejected: "Not approved",
  cancelled: "Cancelled",
  refunded: "Refund recorded",
};

function PaymentDetails({
  payment,
  onChange,
  canManage,
}: {
  payment: Payment;
  onChange: (payment: Payment) => void;
  canManage: boolean;
}) {
  const [payer, setPayer] = React.useState(payment.payer_name);
  const [reference, setReference] = React.useState(payment.reference);
  const [paidOn, setPaidOn] = React.useState(
    payment.paid_on ?? new Date().toLocaleDateString("en-CA"),
  );
  const [note, setNote] = React.useState(payment.note);
  const [file, setFile] = React.useState<File | null>(null);
  const [confirmed, setConfirmed] = React.useState(false);
  const invalidates = [["manual-payments"], ["billing"]];
  const upload = useAction(
    () => {
      const body = new FormData();
      if (file) body.append("file", file);
      return post<Payment>(`/billing/payments/${payment.id}/proof`, body);
    },
    {
      invalidate: invalidates,
      success: "Receipt uploaded",
      onSuccess: onChange,
    },
  );
  const submit = useAction(
    () =>
      post<Payment>(`/billing/payments/${payment.id}/submit`, {
        payer_name: payer,
        reference,
        paid_on: paidOn,
        note,
      }),
    {
      invalidate: invalidates,
      success: "Sent to the billing team for verification",
      onSuccess: onChange,
    },
  );
  const cancel = useAction(
    () => post<Payment>(`/billing/payments/${payment.id}/cancel`),
    {
      invalidate: invalidates,
      success: "Payment request cancelled",
      onSuccess: onChange,
    },
  );
  const bank = payment.method === "bank_transfer";
  const pending = payment.status === "awaiting_payment";
  return (
    <div className="space-y-5">
      <div className="rounded-xl bg-accent-soft p-4">
        <p className="text-sm">
          {payment.plan_name} · {payment.months} month
          {payment.months > 1 ? "s" : ""}
        </p>
        <p className="mt-1 text-3xl font-semibold tracking-tight">
          {money(payment.amount, "PKR")}
        </p>
        <p className="mt-2 text-xs text-muted-foreground">
          Pay exactly this amount. Your plan activates after verification.
        </p>
      </div>
      <Badge
        tone={
          payment.status === "approved"
            ? "success"
            : payment.status === "submitted"
              ? "warning"
              : "neutral"
        }
      >
        {STATUS[payment.status]}
      </Badge>
      <dl className="space-y-2 text-sm">
        <div>
          <dt className="text-muted-foreground">Pay to</dt>
          <dd className="font-medium">{payment.instructions.seller_name}</dd>
        </div>
        {bank ? (
          <>
            <div>
              <dt className="text-muted-foreground">Bank</dt>
              <dd>{payment.instructions.bank_name}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Account title</dt>
              <dd>{payment.instructions.account_title}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Pakistan IBAN</dt>
              <dd className="select-all break-all rounded-lg border border-border bg-background p-3 font-mono">
                {payment.instructions.iban}
              </dd>
            </div>
          </>
        ) : null}
      </dl>
      <p className="whitespace-pre-wrap text-sm text-muted-foreground">
        {bank
          ? payment.instructions.bank_instructions
          : payment.instructions.cash_instructions}
      </p>
      {payment.status === "submitted" ? (
        <Notice tone="info" title="The billing team is checking your payment">
          Submitting a receipt does not mark it as paid. Your subscription
          updates after verification.
        </Notice>
      ) : null}
      {payment.review_note ? (
        <Notice
          tone={payment.status === "rejected" ? "warning" : "info"}
          title="Billing team note"
        >
          {payment.review_note}
        </Notice>
      ) : null}
      {payment.status === "refunded" ? (
        <Notice tone="warning" title="Full refund recorded">
          {payment.refund_reason} · Reference: {payment.refund_reference}
        </Notice>
      ) : null}
      {payment.receipt_number ? (
        <Button asChild variant="secondary">
          <a
            href={`/api/v1/pi-app/billing/payments/${payment.id}/receipt`}
            target="_blank"
            rel="noreferrer"
          >
            <Receipt size={16} aria-hidden />
            Open receipt / print
          </a>
        </Button>
      ) : null}
      {payment.has_proof ? (
        <a
          className="block text-sm text-accent underline"
          href={`/api/v1/pi-app/billing/payments/${payment.id}/proof`}
        >
          Download submitted bank receipt
        </a>
      ) : null}
      {pending && canManage ? (
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            submit.mutate(undefined);
          }}
        >
          <Field label="Name of payer" htmlFor="payment-payer">
            <Input
              id="payment-payer"
              value={payer}
              onChange={(e) => setPayer(e.target.value)}
              required
              minLength={2}
              maxLength={160}
            />
          </Field>
          <Field
            label={
              bank
                ? "Bank transaction reference"
                : "Cash receipt reference (optional)"
            }
            htmlFor="payment-reference"
          >
            <Input
              id="payment-reference"
              value={reference}
              onChange={(e) => setReference(e.target.value)}
              required={bank}
              minLength={bank ? 3 : undefined}
              maxLength={120}
            />
          </Field>
          <Field label="Date paid" htmlFor="payment-date">
            <Input
              id="payment-date"
              type="date"
              value={paidOn}
              onChange={(e) => setPaidOn(e.target.value)}
              required
              max={new Date().toLocaleDateString("en-CA")}
            />
          </Field>
          {bank ? (
            <div className="space-y-2">
              <Field
                label="Bank receipt"
                htmlFor="payment-proof"
                hint="PDF, PNG or JPEG, up to 5 MB. Do not include account passwords or PINs."
              >
                <Input
                  id="payment-proof"
                  type="file"
                  accept="application/pdf,image/png,image/jpeg"
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                  className="h-auto py-2"
                />
              </Field>
              <Button
                type="button"
                variant="secondary"
                size="sm"
                disabled={!file || file.size > 5 * 1024 * 1024}
                loading={upload.isPending}
                onClick={() => upload.mutate(undefined)}
              >
                <Upload size={15} aria-hidden />
                {payment.has_proof ? "Replace receipt" : "Upload receipt"}
              </Button>
              {file && file.size > 5 * 1024 * 1024 ? (
                <p role="alert" className="text-sm text-danger">
                  Choose a file smaller than 5 MB.
                </p>
              ) : null}
            </div>
          ) : null}
          <Field label="Note (optional)" htmlFor="payment-note">
            <Textarea
              id="payment-note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              maxLength={500}
            />
          </Field>
          <label className="flex items-start gap-3 text-sm">
            <input
              type="checkbox"
              className="mt-1 size-4 accent-accent"
              checked={confirmed}
              onChange={(e) => setConfirmed(e.target.checked)}
            />
            I have paid the exact amount shown above.
          </label>
          <div className="flex flex-wrap gap-2">
            <Button
              type="submit"
              loading={submit.isPending}
              disabled={
                !confirmed || upload.isPending || (bank && !payment.has_proof)
              }
            >
              Submit for verification
            </Button>
            <Button
              type="button"
              variant="ghost"
              loading={cancel.isPending}
              onClick={() => cancel.mutate(undefined)}
            >
              Cancel request
            </Button>
          </div>
        </form>
      ) : null}
    </div>
  );
}

export function ManualBilling({ billing }: { billing: BillingView }) {
  const key = useBusinessKey();
  const can = useCan();
  const canManage = can("pi.billing.manage");
  const [page, setPage] = React.useState(1);
  const [selected, setSelected] = React.useState<Payment | null>(null);
  const [createOpen, setCreateOpen] = React.useState(false);
  const [method, setMethod] = React.useState<"bank_transfer" | "cash">(
    "bank_transfer",
  );
  const [planKey, setPlan] = React.useState(billing.plan?.key ?? "");
  const [months, setMonths] = React.useState(1);
  const [requestKey, setRequestKey] = React.useState("");
  const methods = useQuery({
    queryKey: key(["payment-methods"]),
    queryFn: () =>
      get<{ bank_transfer: boolean; cash: boolean; support_email: string }>(
        "/billing/payment-methods",
      ),
  });
  const payments = useQuery({
    queryKey: key(["manual-payments", page]),
    queryFn: () =>
      get<{ items: Payment[]; total: number }>("/billing/payments", {
        page,
        page_size: 10,
      }),
    refetchInterval: 30_000,
  });
  const create = useAction(
    () =>
      post<Payment>("/billing/payments", {
        request_key: requestKey,
        plan: planKey,
        method,
        months,
      }),
    {
      invalidate: [["manual-payments"], ["billing"]],
      onSuccess: (payment) => {
        setCreateOpen(false);
        setSelected(payment);
        setPage(1);
      },
    },
  );
  const pricedPlans = billing.plans.filter((p) => p.manual_monthly_price_pkr);
  const plan = pricedPlans.find((p) => p.key === planKey);
  const open = (next: "bank_transfer" | "cash") => {
    setMethod(next);
    setPlan(
      pricedPlans.some((p) => p.key === billing.plan?.key)
        ? billing.plan!.key
        : (pricedPlans[0]?.key ?? ""),
    );
    setMonths(1);
    setRequestKey(crypto.randomUUID());
    setCreateOpen(true);
  };
  return (
    <section className="space-y-4" aria-labelledby="local-payments">
      <div>
        <h2 id="local-payments" className="text-lg font-semibold">
          Pay locally in Pakistan
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Bank transfer or cash, with a clear record of every payment. Local
          payments are in PKR.
        </p>
      </div>
      {methods.isPending ? (
        <LoadingBlock rows={1} />
      ) : methods.isError ? (
        <ErrorState
          message={errorText(methods.error)}
          onRetry={() => methods.refetch()}
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {(
            [
              {
                key: "bank_transfer",
                title: "Bank transfer",
                icon: Building2,
                body: "Send PKR to our Pakistan bank account, then upload your receipt.",
              },
              {
                key: "cash",
                title: "Cash payment",
                icon: Banknote,
                body: "Pay at the location provided. Our billing team confirms collection.",
              },
            ] as const
          ).map((item) => (
            <Card key={item.key}>
              <CardSection className="flex h-full flex-col gap-3">
                <item.icon className="size-6 text-accent" aria-hidden />
                <div>
                  <h3 className="font-semibold">{item.title}</h3>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {item.body}
                  </p>
                </div>
                {methods.data[item.key] && pricedPlans.length ? (
                  <Button
                    variant="secondary"
                    className="mt-auto"
                    disabled={!canManage}
                    onClick={() => open(item.key)}
                  >
                    Pay by {item.title.toLowerCase()}
                  </Button>
                ) : (
                  <p className="mt-auto text-sm text-muted-foreground">
                    {methods.data[item.key]
                      ? "PKR plan prices are being configured."
                      : "Not enabled by the billing team yet."}
                  </p>
                )}
              </CardSection>
            </Card>
          ))}
        </div>
      )}
      <Card>
        <CardSection>
          <div className="mb-4 flex items-center gap-2">
            <FileText size={18} className="text-accent" aria-hidden />
            <h3 className="font-semibold">Bank & cash payment history</h3>
          </div>
          {payments.isPending ? (
            <LoadingBlock rows={2} />
          ) : payments.isError ? (
            <ErrorState
              message={errorText(payments.error)}
              onRetry={() => payments.refetch()}
            />
          ) : payments.data.items.length ? (
            <>
              <ul className="divide-y divide-border">
                {payments.data.items.map((payment) => (
                  <li key={payment.id}>
                    <button
                      onClick={() => setSelected(payment)}
                      className="flex w-full flex-wrap items-center gap-3 py-4 text-left hover:text-accent"
                    >
                      <span className="flex-1">
                        <strong className="block text-sm font-medium">
                          {payment.plan_name} ·{" "}
                          {payment.method === "cash" ? "Cash" : "Bank transfer"}
                        </strong>
                        <span className="text-xs text-muted-foreground">
                          {date(payment.created_at)} · {payment.months} month
                          {payment.months > 1 ? "s" : ""}
                        </span>
                      </span>
                      <span className="text-sm font-medium tabular-nums">
                        {money(payment.amount, "PKR")}
                      </span>
                      <Badge
                        tone={
                          payment.status === "approved"
                            ? "success"
                            : payment.status === "submitted"
                              ? "warning"
                              : "neutral"
                        }
                      >
                        {STATUS[payment.status]}
                      </Badge>
                    </button>
                  </li>
                ))}
              </ul>
              <div className="mt-3 flex items-center justify-between gap-3">
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={page === 1}
                  onClick={() => setPage((p) => p - 1)}
                >
                  Previous
                </Button>
                <span className="text-xs text-muted-foreground">
                  Page {page} · {payments.data.total} payments
                </span>
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={page * 10 >= payments.data.total}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Next
                </Button>
              </div>
            </>
          ) : (
            <div className="py-5 text-center">
              <CheckCircle2
                className="mx-auto mb-2 size-6 text-muted-foreground"
                aria-hidden
              />
              <p className="text-sm text-muted-foreground">
                Your payment requests and verified receipts will appear here.
              </p>
            </div>
          )}
        </CardSection>
      </Card>
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent
          title={method === "cash" ? "Pay with cash" : "Pay by bank transfer"}
          description="Review the price first. Creating a request does not charge you."
        >
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              create.mutate(undefined);
            }}
          >
            <Field label="Plan" htmlFor="local-plan">
              <Select
                id="local-plan"
                value={planKey}
                onChange={(e) => {
                  setPlan(e.target.value);
                  setRequestKey(crypto.randomUUID());
                }}
              >
                {pricedPlans.map((p) => (
                  <option key={p.key} value={p.key}>
                    {p.name} · {money(p.manual_monthly_price_pkr!, "PKR")} /
                    month
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Pay for" htmlFor="local-months">
              <Select
                id="local-months"
                value={months}
                onChange={(e) => {
                  setMonths(Number(e.target.value));
                  setRequestKey(crypto.randomUUID());
                }}
              >
                {[1, 3, 6, 12].map((n) => (
                  <option key={n} value={n}>
                    {n} month{n > 1 ? "s" : ""}
                  </option>
                ))}
              </Select>
            </Field>
            {plan ? (
              <div className="rounded-xl bg-accent-soft p-4">
                <p className="text-sm">Total payable</p>
                <p className="mt-1 text-2xl font-semibold">
                  {money(
                    (Number(plan.manual_monthly_price_pkr) * months).toFixed(2),
                    "PKR",
                  )}
                </p>
              </div>
            ) : null}
            <p className="text-sm text-muted-foreground">
              Manual payments do not renew automatically. A verified renewal
              extends your current paid period.
            </p>
            <Button
              className="w-full"
              type="submit"
              disabled={!plan}
              loading={create.isPending}
            >
              Continue to payment instructions
            </Button>
          </form>
        </DialogContent>
      </Dialog>
      <Dialog
        open={!!selected}
        onOpenChange={(v) => {
          if (!v) setSelected(null);
        }}
      >
        <DialogContent
          title="Payment details"
          description="Your payment instructions, status and receipt."
        >
          {selected ? (
            <PaymentDetails
              key={selected.id}
              payment={selected}
              onChange={setSelected}
              canManage={canManage}
            />
          ) : null}
        </DialogContent>
      </Dialog>
    </section>
  );
}
