"use client";

import * as React from "react";
import {
  Banknote,
  Building2,
  CreditCard,
  Receipt,
  Settings2,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { PageHeader, PageShell } from "@/components/app/page";
import { ErrorState } from "@/components/app/states";
import { Button } from "@/components/ui/button";
import { Badge, Card, Skeleton } from "@/components/ui/display";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogHeader,
} from "@/components/ui/overlays";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { ApiError } from "@/services/api-client";
import {
  piBillingService as service,
  type BillingPlan,
  type CollectedPayment,
  type CollectionSettings,
  type PlatformSettings,
} from "./service";
import s from "./pi-billing.module.css";

const cash = (value: string, currency = "PKR") =>
  new Intl.NumberFormat("en-PK", {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  }).format(Number(value));
const date = (value: string | null) =>
  value
    ? new Date(value).toLocaleDateString("en-GB", {
        day: "numeric",
        month: "short",
        year: "numeric",
      })
    : "—";
const labels: Record<string, string> = {
  awaiting_payment: "Awaiting payment",
  submitted: "Under review",
  approved: "Verified",
  rejected: "Rejected",
  cancelled: "Cancelled",
  refunded: "Refund recorded",
};
const invalidate = [["pi-billing"]];
function Field({
  label,
  id,
  children,
}: {
  label: string;
  id: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <label className="block text-sm font-medium" htmlFor={id}>
        {label}
      </label>
      {children}
    </div>
  );
}

function PaymentReview({
  payment,
  onDone,
  canManage,
}: {
  payment: CollectedPayment;
  onDone: () => void;
  canManage: boolean;
}) {
  const [action, setAction] = React.useState("approve");
  const [note, setNote] = React.useState("");
  const [reference, setReference] = React.useState("");
  const [verified, setVerified] = React.useState(false);
  const review = useScopedMutation(
    () =>
      service.review(payment, { action, note, verified_received: verified }),
    { invalidate, success: "Payment review saved", onSuccess: onDone },
  );
  const refund = useScopedMutation(
    () =>
      service.refund(payment, {
        reference,
        reason: note,
        already_refunded: verified,
      }),
    { invalidate, success: "Full refund recorded", onSuccess: onDone },
  );
  const path = `/api/v1/operator/pi/billing/accounts/${payment.tenant_id}/payments/${payment.id}`;
  return (
    <div className="space-y-5">
      <div className={s.paymentTotal}>
        <span>
          {payment.business_name} · {payment.plan_name}
        </span>
        <strong>{cash(payment.amount)}</strong>
        <span>
          {payment.months} month{payment.months > 1 ? "s" : ""} ·{" "}
          {payment.method === "cash" ? "Cash" : "Bank transfer"}
        </span>
      </div>
      <dl className={s.details}>
        <div>
          <dt>Status</dt>
          <dd>{labels[payment.status]}</dd>
        </div>
        <div>
          <dt>Payer</dt>
          <dd>{payment.payer_name || "Not submitted"}</dd>
        </div>
        <div>
          <dt>Date paid</dt>
          <dd>{date(payment.paid_on)}</dd>
        </div>
        <div>
          <dt>Reference</dt>
          <dd>{payment.reference || "No reference"}</dd>
        </div>
        {payment.method === "bank_transfer" ? (
          <div>
            <dt>Receiving IBAN</dt>
            <dd>{payment.instructions.iban}</dd>
          </div>
        ) : null}
      </dl>
      {payment.note ? (
        <p className="whitespace-pre-wrap text-sm">{payment.note}</p>
      ) : null}
      <div className="flex flex-wrap gap-2">
        {payment.has_proof ? (
          <Button asChild variant="secondary">
            <a href={path + "/proof"}>Download bank receipt</a>
          </Button>
        ) : null}
        {payment.receipt_number ? (
          <Button asChild variant="secondary">
            <a href={path + "/receipt"} target="_blank" rel="noreferrer">
              Open verified receipt
            </a>
          </Button>
        ) : null}
      </div>
      {payment.review_note ? (
        <p className="text-sm text-muted-foreground">
          Review note: {payment.review_note}
        </p>
      ) : null}
      {canManage && payment.status === "submitted" ? (
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            review.mutate(undefined);
          }}
        >
          <Field id="review-action" label="Decision">
            <NativeSelect
              id="review-action"
              value={action}
              onChange={(e) => {
                setAction(e.target.value);
                setVerified(false);
              }}
            >
              <option value="approve">Approve payment</option>
              <option value="reject">Reject payment</option>
            </NativeSelect>
          </Field>
          <Field id="review-note" label="Verification / rejection note">
            <Textarea
              id="review-note"
              required
              minLength={3}
              maxLength={500}
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </Field>
          {action === "approve" ? (
            <label className={s.check}>
              <input
                type="checkbox"
                checked={verified}
                onChange={(e) => setVerified(e.target.checked)}
              />
              I checked the bank statement or counted the cash and received
              exactly {cash(payment.amount)}.
            </label>
          ) : null}
          <Button
            type="submit"
            disabled={action === "approve" && !verified}
            loading={review.isPending}
          >
            {action === "approve"
              ? "Verify payment & activate plan"
              : "Reject payment"}
          </Button>
        </form>
      ) : null}
      {canManage && payment.status === "approved" ? (
        <details className="rounded-lg border border-border p-4">
          <summary className="cursor-pointer text-sm font-medium">
            Record a full refund
          </summary>
          <form
            className="mt-4 space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              refund.mutate(undefined);
            }}
          >
            <p className="text-sm text-muted-foreground">
              Return the full amount outside this app first. This records the
              refund and removes this renewal from the subscription. Later
              renewals must be resolved first.
            </p>
            <Field
              id="refund-reference"
              label="Refund transaction / cash voucher reference"
            >
              <Input
                id="refund-reference"
                required
                minLength={3}
                maxLength={120}
                value={reference}
                onChange={(e) => setReference(e.target.value)}
              />
            </Field>
            <Field id="refund-reason" label="Reason">
              <Textarea
                id="refund-reason"
                required
                minLength={3}
                maxLength={500}
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
            </Field>
            <label className={s.check}>
              <input
                type="checkbox"
                checked={verified}
                onChange={(e) => setVerified(e.target.checked)}
              />
              The full {cash(payment.amount)} has already been returned.
            </label>
            <Button
              type="submit"
              variant="danger"
              disabled={!verified}
              loading={refund.isPending}
            >
              Record full refund
            </Button>
          </form>
        </details>
      ) : null}
      {payment.refund_reason ? (
        <p className="text-sm text-muted-foreground">
          Refund: {payment.refund_reason}
        </p>
      ) : null}
    </div>
  );
}

function CashForm({
  plans,
  onDone,
}: {
  plans: BillingPlan[];
  onDone: () => void;
}) {
  const [search, setSearch] = React.useState("");
  const [tenant, setTenant] = React.useState("");
  const [plan, setPlan] = React.useState("");
  const [months, setMonths] = React.useState(1);
  const [payer, setPayer] = React.useState("");
  const [reference, setReference] = React.useState("");
  const [paidOn, setPaidOn] = React.useState(
    new Date().toLocaleDateString("en-CA"),
  );
  const [note, setNote] = React.useState("");
  const [verified, setVerified] = React.useState(false);
  const [requestKey] = React.useState(() => crypto.randomUUID());
  const accounts = useScopedQuery(["pi-billing", "accounts", search], () =>
    service.accounts(search),
  );
  const create = useScopedMutation(
    () =>
      service.cash(tenant, {
        request_key: requestKey,
        plan,
        months,
        payer_name: payer,
        reference,
        paid_on: paidOn,
        note,
        verified_received: verified,
      }),
    {
      invalidate,
      success: "Cash receipt recorded and subscription updated",
      onSuccess: onDone,
    },
  );
  const priced = plans.filter(
    (p) => p.status === "available" && p.manual_monthly_price_pkr,
  );
  const selected = priced.find((p) => p.key === plan);
  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        create.mutate(undefined);
      }}
    >
      <Field id="cash-search" label="Find business">
        <Input
          id="cash-search"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setTenant("");
          }}
          placeholder="Search by business name"
        />
      </Field>
      {accounts.isError ? (
        <ErrorState
          compact
          error={accounts.error}
          onRetry={() => accounts.refetch()}
        />
      ) : null}
      <Field id="cash-business" label="Business">
        <NativeSelect
          id="cash-business"
          required
          value={tenant}
          onChange={(e) => setTenant(e.target.value)}
        >
          <option value="">Choose a business</option>
          {accounts.data?.items.map((a) => (
            <option key={a.tenant_id} value={a.tenant_id}>
              {a.name}
            </option>
          ))}
        </NativeSelect>
      </Field>
      <Field id="cash-plan" label="Plan">
        <NativeSelect
          id="cash-plan"
          required
          value={plan}
          onChange={(e) => setPlan(e.target.value)}
        >
          <option value="">Choose a plan</option>
          {priced.map((p) => (
            <option key={p.key} value={p.key}>
              {p.name} · {cash(p.manual_monthly_price_pkr!)}/month
            </option>
          ))}
        </NativeSelect>
      </Field>
      <Field id="cash-months" label="Months paid">
        <NativeSelect
          id="cash-months"
          value={months}
          onChange={(e) => setMonths(Number(e.target.value))}
        >
          {[1, 3, 6, 12].map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </NativeSelect>
      </Field>
      {selected ? (
        <div className={s.paymentTotal}>
          <span>Cash to record</span>
          <strong>
            {cash(
              (Number(selected.manual_monthly_price_pkr) * months).toFixed(2),
            )}
          </strong>
        </div>
      ) : null}
      <Field id="cash-payer" label="Payer name">
        <Input
          id="cash-payer"
          required
          minLength={2}
          maxLength={160}
          value={payer}
          onChange={(e) => setPayer(e.target.value)}
        />
      </Field>
      <Field id="cash-reference" label="Cash voucher reference">
        <Input
          id="cash-reference"
          required
          maxLength={120}
          value={reference}
          onChange={(e) => setReference(e.target.value)}
        />
      </Field>
      <Field id="cash-date" label="Date received">
        <Input
          id="cash-date"
          type="date"
          required
          max={new Date().toLocaleDateString("en-CA")}
          value={paidOn}
          onChange={(e) => setPaidOn(e.target.value)}
        />
      </Field>
      <Field id="cash-note" label="Collection note">
        <Textarea
          id="cash-note"
          required
          minLength={3}
          maxLength={500}
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
      </Field>
      <label className={s.check}>
        <input
          type="checkbox"
          checked={verified}
          onChange={(e) => setVerified(e.target.checked)}
        />
        I received and counted this cash. This creates a paid receipt and
        activates or renews the plan.
      </label>
      <Button
        type="submit"
        loading={create.isPending}
        disabled={!verified || !selected || !tenant}
      >
        Record cash & issue receipt
      </Button>
    </form>
  );
}

function PlanEditor({
  plan,
  canEdit,
}: {
  plan: BillingPlan;
  canEdit: boolean;
}) {
  const [price, setPrice] = React.useState(plan.monthly_price ?? "");
  const [currency, setCurrency] = React.useState(plan.currency);
  const [local, setLocal] = React.useState(plan.manual_monthly_price_pkr ?? "");
  const [stripe, setStripe] = React.useState(plan.stripe_price_id ?? "");
  const [trial, setTrial] = React.useState(plan.trial_days);
  const [status, setStatus] = React.useState(plan.status);
  const save = useScopedMutation(
    () =>
      service.savePlan(plan.key, {
        monthly_price: price || null,
        currency,
        manual_monthly_price_pkr: local || null,
        stripe_price_id: stripe || null,
        trial_days: trial,
        status,
      }),
    { invalidate, success: "Plan pricing saved" },
  );
  return (
    <Card className="p-5">
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate(undefined);
        }}
      >
        <div>
          <h2 className="text-lg font-semibold">{plan.name}</h2>
          <p className="text-sm text-muted-foreground">{plan.description}</p>
        </div>
        <fieldset disabled={!canEdit} className="space-y-4">
          <Field
            id={`pkr-${plan.key}`}
            label="Bank / cash price per month (PKR)"
          >
            <Input
              id={`pkr-${plan.key}`}
              type="number"
              min="0.01"
              max="9999999999.99"
              step="0.01"
              value={local}
              onChange={(e) => setLocal(e.target.value)}
              placeholder="Set your local price"
            />
          </Field>
          <div className="grid grid-cols-[1fr_5rem] gap-2">
            <Field id={`price-${plan.key}`} label="Stripe monthly price">
              <Input
                id={`price-${plan.key}`}
                type="number"
                min="0"
                step="0.01"
                value={price}
                onChange={(e) => setPrice(e.target.value)}
              />
            </Field>
            <Field id={`currency-${plan.key}`} label="Currency">
              <Input
                id={`currency-${plan.key}`}
                maxLength={3}
                pattern="[A-Z]{3}"
                required
                value={currency}
                onChange={(e) => setCurrency(e.target.value.toUpperCase())}
              />
            </Field>
          </div>
          <Field id={`stripe-${plan.key}`} label="Stripe recurring price ID">
            <Input
              id={`stripe-${plan.key}`}
              value={stripe}
              onChange={(e) => setStripe(e.target.value)}
              placeholder="price_…"
            />
          </Field>
          <p className="text-xs text-muted-foreground">
            Use a monthly recurring Stripe price matching the amount and
            currency above. PKR bank/cash pricing is separate; no exchange rate
            is assumed.
          </p>
          <div className="grid grid-cols-2 gap-3">
            <Field id={`trial-${plan.key}`} label="Trial days">
              <Input
                id={`trial-${plan.key}`}
                type="number"
                min="0"
                max="90"
                value={trial}
                onChange={(e) => setTrial(Number(e.target.value))}
              />
            </Field>
            <Field id={`status-${plan.key}`} label="Availability">
              <NativeSelect
                id={`status-${plan.key}`}
                value={status}
                onChange={(e) => setStatus(e.target.value)}
              >
                <option value="draft">Draft</option>
                <option value="available">Available</option>
                <option value="retired">Retired</option>
              </NativeSelect>
            </Field>
          </div>
          {canEdit ? (
            <Button type="submit" loading={save.isPending}>
              Save {plan.name}
            </Button>
          ) : null}
        </fieldset>
      </form>
    </Card>
  );
}

function CollectionForm({ settings }: { settings: PlatformSettings }) {
  const [form, setForm] = React.useState(settings.collection);
  const save = useScopedMutation(() => service.saveSettings(form), {
    invalidate,
    success: "Payment instructions saved",
  });
  const field = (key: keyof CollectionSettings, value: string | boolean) =>
    setForm((f) => ({ ...f, [key]: value }));
  return (
    <Card className="p-5 sm:p-6">
      <form
        className="space-y-5"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate(undefined);
        }}
      >
        <div>
          <h2 className="text-lg font-semibold">Your collection details</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Customers see these details when requesting a payment. Existing
            requests retain the instructions they were issued.
          </p>
        </div>
        <fieldset disabled={!settings.can_edit} className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field id="seller-name" label="Business / receipt issuer">
              <Input
                id="seller-name"
                value={form.seller_name}
                onChange={(e) => field("seller_name", e.target.value)}
                maxLength={160}
              />
            </Field>
            <Field id="billing-email" label="Billing support email">
              <Input
                id="billing-email"
                type="email"
                value={form.support_email}
                onChange={(e) => field("support_email", e.target.value)}
                maxLength={200}
              />
            </Field>
          </div>
          <Field id="seller-address" label="Receipt address">
            <Textarea
              id="seller-address"
              value={form.seller_address}
              onChange={(e) => field("seller_address", e.target.value)}
              maxLength={400}
            />
          </Field>
          <div className={s.methodSettings}>
            <label className={s.check}>
              <input
                type="checkbox"
                checked={form.bank_enabled}
                onChange={(e) => field("bank_enabled", e.target.checked)}
              />
              <Building2 size={18} aria-hidden />
              Enable Pakistan bank transfer (PKR)
            </label>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field id="bank-name" label="Bank name">
                <Input
                  id="bank-name"
                  required={form.bank_enabled}
                  value={form.bank_name}
                  onChange={(e) => field("bank_name", e.target.value)}
                  maxLength={120}
                />
              </Field>
              <Field id="bank-title" label="Account title">
                <Input
                  id="bank-title"
                  required={form.bank_enabled}
                  value={form.account_title}
                  onChange={(e) => field("account_title", e.target.value)}
                  maxLength={160}
                />
              </Field>
            </div>
            <Field id="bank-iban" label="Pakistan IBAN">
              <Input
                id="bank-iban"
                required={form.bank_enabled}
                value={form.iban}
                onChange={(e) => field("iban", e.target.value.toUpperCase())}
                placeholder="PK… (24 characters)"
                maxLength={40}
              />
            </Field>
            <Field id="bank-instructions" label="Transfer instructions">
              <Textarea
                id="bank-instructions"
                value={form.bank_instructions}
                onChange={(e) => field("bank_instructions", e.target.value)}
                maxLength={500}
              />
            </Field>
          </div>
          <div className={s.methodSettings}>
            <label className={s.check}>
              <input
                type="checkbox"
                checked={form.cash_enabled}
                onChange={(e) => field("cash_enabled", e.target.checked)}
              />
              <Banknote size={18} aria-hidden />
              Enable cash collection (PKR)
            </label>
            <Field
              id="cash-instructions"
              label="Where and to whom should customers pay?"
            >
              <Textarea
                id="cash-instructions"
                required={form.cash_enabled}
                value={form.cash_instructions}
                onChange={(e) => field("cash_instructions", e.target.value)}
                maxLength={500}
              />
            </Field>
          </div>
          {settings.can_edit ? (
            <Button type="submit" loading={save.isPending}>
              Save collection settings
            </Button>
          ) : (
            <p className="text-sm text-muted-foreground">
              Only a platform operator owner can change collection details.
            </p>
          )}
        </fieldset>
      </form>
    </Card>
  );
}

function RuntimeSetup({ settings }: { settings: PlatformSettings }) {
  const r = settings.runtime;
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">
          Kapso, AI and Stripe connections
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          API secrets belong in the backend server environment, never the
          customer app. Restart the API and workers after changing them.
          “Configured” means present; it does not verify the provider account.
        </p>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="space-y-3 p-5">
          <h3 className="flex items-center gap-2 font-semibold">
            <ShieldCheck size={18} />
            Kapso · WhatsApp
          </h3>
          <Badge
            tone={
              r.kapso.key_configured && r.kapso.webhook_configured
                ? "success"
                : "warning"
            }
          >
            {r.kapso.key_configured && r.kapso.webhook_configured
              ? "Keys configured"
              : "Configuration needed"}
          </Badge>
          <p className="text-sm text-muted-foreground">
            Used for hosted WhatsApp authorization, number connection, inbound
            webhooks and messaging.
          </p>
          <code className={s.code}>
            KAPSO_API_KEY
            <br />
            KAPSO_WEBHOOK_SECRET
            <br />
            SECRETS_ENCRYPTION_KEY
          </code>
          <p className="break-all text-xs text-muted-foreground">
            Public webhook: {r.kapso.webhook_path}
          </p>
          <p className="text-sm">
            Encrypted token storage:{" "}
            {r.encryption_configured ? "Configured" : "Missing encryption key"}
          </p>
        </Card>
        <Card className="space-y-3 p-5">
          <h3 className="flex items-center gap-2 font-semibold">
            <CreditCard size={18} />
            Stripe · Pi subscriptions
          </h3>
          <Badge
            tone={
              r.stripe.key_configured && r.stripe.webhook_configured
                ? "success"
                : "warning"
            }
          >
            {r.stripe.mode.replaceAll("_", " ")}
          </Badge>
          <p className="text-sm text-muted-foreground">
            Hosted card checkout, recurring subscriptions, invoices and billing
            portal. Add monthly price IDs under Plans.
          </p>
          <code className={s.code}>
            PI_BILLING_STRIPE_SECRET_KEY
            <br />
            PI_BILLING_STRIPE_WEBHOOK_SECRET
          </code>
          <p className="break-all text-xs text-muted-foreground">
            Public webhook: {r.stripe.webhook_path}
          </p>
          <p className="text-sm">
            Signing secret:{" "}
            {r.stripe.webhook_configured ? "Configured" : "Missing"}
          </p>
        </Card>
      </div>
      <Card className="space-y-4 p-5">
        <h3 className="flex items-center gap-2 font-semibold">
          <Sparkles size={18} />
          AI gateway
        </h3>
        <p className="text-sm text-muted-foreground">
          Provider order: {r.provider_order.join(" → ")}. Pi asks this shared
          gateway for a model; Kapso handles WhatsApp transport.
        </p>
        <div className="grid gap-4 lg:grid-cols-3">
          {r.ai.map((p) => (
            <div
              key={p.provider}
              className="min-w-0 space-y-3 rounded-xl border border-border p-4"
            >
              <div className="flex items-center justify-between gap-2">
                <strong className="capitalize">{p.provider}</strong>
                <Badge tone={p.key_configured ? "success" : "warning"}>
                  {p.key_configured ? "Key configured" : "Key missing"}
                </Badge>
              </div>
              <code className={s.code}>
                {p.provider.toUpperCase()}_API_KEY
                <br />
                {p.provider.toUpperCase()}_MODELS
              </code>
              <dl className={s.models}>
                {Object.entries(p.models).map(([alias, model]) => (
                  <div key={alias}>
                    <dt>{alias}</dt>
                    <dd>{model}</dd>
                  </div>
                ))}
              </dl>
            </div>
          ))}
        </div>
        <p className="text-xs text-muted-foreground">
          Model maps are JSON alias-to-model IDs (router, agent, summarize,
          vision, embed, transcribe). Use models enabled for your provider
          account. No API keys are exposed here.
        </p>
      </Card>
    </div>
  );
}

export function PiBillingPage() {
  const [tab, setTab] = React.useState("payments");
  const [filter, setFilter] = React.useState("submitted");
  const [page, setPage] = React.useState(1);
  const [selected, setSelected] = React.useState<CollectedPayment | null>(null);
  const [cashOpen, setCashOpen] = React.useState(false);
  const me = useScopedQuery(["pi-billing", "me"], service.me, { retry: false });
  const canRead = !!me.data?.capabilities.includes("operator.billing.read");
  const canManage = !!me.data?.capabilities.includes("operator.billing.manage");
  const canPlans = !!me.data?.capabilities.includes("operator.plans.manage");
  const settings = useScopedQuery(
    ["pi-billing", "settings"],
    service.settings,
    { enabled: canRead },
  );
  const plans = useScopedQuery(["pi-billing", "plans"], service.plans, {
    enabled: canRead,
  });
  const payments = useScopedQuery(
    ["pi-billing", "payments", filter, page],
    () => service.payments(filter, page),
    { enabled: canRead, refetchInterval: 30000 },
  );
  const summary = useScopedQuery(["pi-billing", "summary"], service.summary, {
    enabled: canRead,
    refetchInterval: 30000,
  });
  return (
    <PageShell width="wide">
      <PageHeader
        title="Pi subscriptions & payments"
        description="Manage card billing, PKR bank transfers and cash collections."
      />
      {me.isPending ? (
        <Skeleton className="h-40" />
      ) : me.isError ? (
        <div>
          {me.error instanceof ApiError && me.error.status === 403 ? (
            <Card className="space-y-2 p-6">
              <h2 className="font-semibold">
                Platform operator access required
              </h2>
              <p className="text-sm text-muted-foreground">
                This area controls Pi subscription collections. Ask your
                platform owner to assign an operator role. A client-business
                billing role does not grant platform access.
              </p>
            </Card>
          ) : (
            <ErrorState error={me.error} onRetry={() => me.refetch()} />
          )}
        </div>
      ) : !canRead ? (
        <Card className="p-6">
          Your operator role does not include billing access.
        </Card>
      ) : (
        <div className={s.console}>
          <div className={s.hero}>
            <div>
              <span>PI BUSINESS OPERATIONS</span>
              <h2>
                Every payment.
                <br />
                <em>A clear record.</em>
              </h2>
              <p>
                Verify collections, renew plans and keep the details in one
                place.
              </p>
            </div>
            {canManage ? (
              <Button
                variant="secondary"
                size="lg"
                onClick={() => setCashOpen(true)}
                disabled={!settings.data?.collection.cash_enabled}
              >
                <Banknote size={18} />
                Record cash payment
              </Button>
            ) : null}
          </div>
          {summary.data ? (
            <div className={s.metrics}>
              {[
                {
                  label: "PKR received",
                  value: cash(summary.data.received_pkr),
                },
                {
                  label: "PKR refunded",
                  value: cash(summary.data.refunded_pkr),
                },
                {
                  label: "Net PKR recorded",
                  value: cash(summary.data.net_pkr),
                },
                {
                  label: "Payments to review",
                  value: String(summary.data.pending_count),
                },
              ].map((m) => (
                <Card className="p-5" key={m.label}>
                  <p>{m.label}</p>
                  <strong>{m.value}</strong>
                  <small>
                    {m.label === "Payments to review"
                      ? "All pending requests"
                      : date(summary.data!.period) + " onwards"}
                  </small>
                </Card>
              ))}
            </div>
          ) : summary.isError ? (
            <ErrorState
              compact
              error={summary.error}
              onRetry={() => summary.refetch()}
            />
          ) : (
            <Skeleton className="h-24" />
          )}
          {summary.data?.stripe_paid.length ? (
            <p className="text-sm text-muted-foreground">
              Stripe invoices paid this month:{" "}
              {summary.data.stripe_paid
                .map((a) => cash(a.amount, a.currency))
                .join(" · ")}
              . Currencies are reported separately.
            </p>
          ) : null}
          <div
            className={s.tabs}
            role="tablist"
            aria-label="Pi billing sections"
          >
            {[
              { key: "payments", label: "Payments", icon: Receipt },
              { key: "plans", label: "Plans & prices", icon: CreditCard },
              {
                key: "collection",
                label: "Bank & cash settings",
                icon: Building2,
              },
              {
                key: "connections",
                label: "API & model setup",
                icon: Settings2,
              },
            ].map((t) => (
              <button
                key={t.key}
                id={`tab-${t.key}`}
                role="tab"
                aria-selected={tab === t.key}
                aria-controls="billing-panel"
                onClick={() => setTab(t.key)}
              >
                <t.icon size={16} aria-hidden />
                {t.label}
              </button>
            ))}
          </div>
          <div
            id="billing-panel"
            role="tabpanel"
            aria-labelledby={`tab-${tab}`}
          >
            {tab === "payments" ? (
              <Card className="p-5">
                <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                  <h2 className="font-semibold">Bank & cash ledger</h2>
                  <NativeSelect
                    aria-label="Payment status"
                    className="w-48"
                    value={filter}
                    onChange={(e) => {
                      setFilter(e.target.value);
                      setPage(1);
                    }}
                  >
                    <option value="">All payments</option>
                    {Object.entries(labels).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </NativeSelect>
                </div>
                {payments.isPending ? (
                  <Skeleton className="h-40" />
                ) : payments.isError ? (
                  <ErrorState
                    error={payments.error}
                    onRetry={() => payments.refetch()}
                  />
                ) : payments.data.items.length ? (
                  <>
                    <div className={s.ledger}>
                      {payments.data.items.map((p) => (
                        <button key={p.id} onClick={() => setSelected(p)}>
                          <span>
                            <strong>{p.business_name}</strong>
                            <small>
                              {p.plan_name} ·{" "}
                              {p.method === "cash" ? "Cash" : "Bank transfer"} ·{" "}
                              {date(p.created_at)}
                            </small>
                          </span>
                          <strong>{cash(p.amount)}</strong>
                          <Badge
                            tone={
                              p.status === "approved"
                                ? "success"
                                : p.status === "submitted"
                                  ? "warning"
                                  : "neutral"
                            }
                          >
                            {labels[p.status]}
                          </Badge>
                          <span className="text-xs text-primary">
                            {p.status === "submitted" && canManage
                              ? "Review"
                              : "View"}
                          </span>
                        </button>
                      ))}
                    </div>
                    <div className="mt-4 flex items-center justify-between gap-3">
                      <Button
                        variant="ghost"
                        disabled={page === 1}
                        onClick={() => setPage((p) => p - 1)}
                      >
                        Previous
                      </Button>
                      <span className="text-xs text-muted-foreground">
                        {payments.data.total} payments · Page {page}
                      </span>
                      <Button
                        variant="ghost"
                        disabled={page * 20 >= payments.data.total}
                        onClick={() => setPage((p) => p + 1)}
                      >
                        Next
                      </Button>
                    </div>
                  </>
                ) : (
                  <div className="py-12 text-center">
                    <Receipt className="mx-auto mb-3 size-7 text-muted-foreground" />
                    <h3 className="font-medium">
                      No {filter ? labels[filter].toLowerCase() : "recorded"}{" "}
                      payments
                    </h3>
                    <p className="mt-1 text-sm text-muted-foreground">
                      Customer payment requests and cash receipts will appear
                      here.
                    </p>
                  </div>
                )}
              </Card>
            ) : null}
            {tab === "plans" ? (
              plans.isPending ? (
                <Skeleton className="h-48" />
              ) : plans.isError ? (
                <ErrorState
                  error={plans.error}
                  onRetry={() => plans.refetch()}
                />
              ) : (
                <div className="grid gap-4 lg:grid-cols-3">
                  {plans.data.map((p) => (
                    <PlanEditor
                      key={JSON.stringify(p)}
                      plan={p}
                      canEdit={canPlans}
                    />
                  ))}
                </div>
              )
            ) : null}
            {tab === "collection" || tab === "connections" ? (
              settings.isPending ? (
                <Skeleton className="h-48" />
              ) : settings.isError ? (
                <ErrorState
                  error={settings.error}
                  onRetry={() => settings.refetch()}
                />
              ) : tab === "collection" ? (
                <CollectionForm
                  key={JSON.stringify(settings.data.collection)}
                  settings={settings.data}
                />
              ) : (
                <RuntimeSetup settings={settings.data} />
              )
            ) : null}
          </div>
          <Dialog
            open={!!selected}
            onOpenChange={(open) => {
              if (!open) setSelected(null);
            }}
          >
            <DialogContent>
              <DialogHeader
                title="Review payment"
                description="Verify money received before activating or renewing a subscription."
              />
              <DialogBody>
                {selected ? (
                  <PaymentReview
                    key={selected.id}
                    payment={selected}
                    canManage={canManage}
                    onDone={() => setSelected(null)}
                  />
                ) : null}
              </DialogBody>
            </DialogContent>
          </Dialog>
          <Dialog open={cashOpen} onOpenChange={setCashOpen}>
            <DialogContent>
              <DialogHeader
                title="Record cash received"
                description="Only record cash you have actually collected."
              />
              <DialogBody>
                {plans.data ? (
                  <CashForm
                    plans={plans.data}
                    onDone={() => setCashOpen(false)}
                  />
                ) : (
                  <Skeleton className="h-32" />
                )}
              </DialogBody>
            </DialogContent>
          </Dialog>
        </div>
      )}
    </PageShell>
  );
}
