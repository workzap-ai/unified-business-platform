"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Banknote,
  CreditCard,
  Link2,
  Plus,
  QrCode,
  Smartphone,
  Trash2,
  Wallet,
} from "lucide-react";
import * as React from "react";

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
  LoadingBlock,
  Notice,
  Select,
  Switch,
  Textarea,
} from "@/components/ui";
import { errorText, get, post, put } from "@/lib/api";
import { date, money } from "@/lib/format";
import { useAction, useBusinessKey, useCan } from "@/lib/session";

interface BankAccount {
  bank: string;
  account_title: string;
  account_number: string;
  iban: string;
  branch: string;
}
interface WalletAccount {
  provider: "jazzcash" | "easypaisa" | "sadapay" | "nayapay";
  account_title: string;
  number: string;
}
export interface PaymentSettings {
  stripe_enabled: boolean;
  stripe_connected: boolean;
  bank_enabled: boolean;
  bank_accounts: BankAccount[];
  wallet_enabled: boolean;
  wallets: WalletAccount[];
  cash_enabled: boolean;
  cash_instructions: string;
  payment_note: string;
  enabled_methods: string[];
  banks: string[];
  wallet_providers: Record<string, string>;
}
export interface PaymentRequest {
  id: string;
  invoice_id: string;
  customer_id: string;
  conversation_id: string | null;
  method: string;
  status: string;
  amount: string;
  currency: string;
  reference: string;
  checkout_url: string | null;
  proof_note: string;
  created_at: string;
  expires_at: string | null;
  message: string;
}

export const METHOD_LABEL: Record<string, string> = {
  stripe: "Card (Stripe)",
  bank_transfer: "Bank transfer",
  mobile_wallet: "Mobile wallet",
  cash: "Cash",
};
const STATUS: Record<
  string,
  [string, "neutral" | "info" | "success" | "warning" | "danger"]
> = {
  open: ["Waiting for payment", "info"],
  awaiting_verification: ["Check your account", "warning"],
  paid: ["Paid", "success"],
  cancelled: ["Cancelled", "neutral"],
  expired: ["Expired", "neutral"],
  needs_review: ["Needs review", "danger"],
};

export function PaymentStatus({ status }: { status: string }) {
  const [text, tone] = STATUS[status] ?? [status, "neutral"];
  return <Badge tone={tone}>{text}</Badge>;
}

function StripeConnect({ connected }: { connected: boolean }) {
  const [secret, setSecret] = React.useState("");
  const [webhook, setWebhook] = React.useState("");
  const [result, setResult] = React.useState<{
    webhook_url: string | null;
    mode: string;
  } | null>(null);
  const connect = useAction(
    () =>
      post<{ connected: boolean; webhook_url: string | null; mode: string }>(
        "/pi/customer-payments/stripe",
        { secret_key: secret.trim(), webhook_secret: webhook.trim() },
      ),
    {
      invalidate: [["payment-settings"]],
      onSuccess: (r) => {
        setResult(r);
        setSecret("");
        setWebhook("");
      },
      success: (r) =>
        r.connected
          ? "Stripe connected"
          : "Saved, but Stripe didn't accept the key. Check it.",
    },
  );
  if (connected && !result) {
    return <Badge tone="success">Stripe connected</Badge>;
  }
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Money goes straight to your own Stripe account. Use a restricted or
        secret key from your Stripe dashboard. Keys are encrypted and never
        shown again.
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Secret key" htmlFor="sk">
          <Input
            id="sk"
            type="password"
            autoComplete="off"
            placeholder="sk_live_… or rk_live_…"
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
          />
        </Field>
        <Field label="Webhook signing secret" htmlFor="whsec">
          <Input
            id="whsec"
            type="password"
            autoComplete="off"
            placeholder="whsec_…"
            value={webhook}
            onChange={(e) => setWebhook(e.target.value)}
          />
        </Field>
      </div>
      <Button
        loading={connect.isPending}
        disabled={!secret || !webhook}
        onClick={() => connect.mutate(undefined)}
      >
        Connect Stripe
      </Button>
      {result?.webhook_url ? (
        <Notice tone="info" title="One more step in Stripe">
          Add this webhook endpoint in Stripe (event:
          checkout.session.completed), so pi only marks payments as paid when
          Stripe confirms them:
          <code className="mt-1 block break-all rounded bg-surface px-2 py-1 text-xs">
            {result.webhook_url}
          </code>
        </Notice>
      ) : null}
    </div>
  );
}

// Mirrors the API's checks so owners see which field to fix instead of a generic error.
function ibanError(value: string): string | null {
  const iban = value.replace(/\s/g, "").toUpperCase();
  if (!iban) return null;
  if (!/^PK\d{2}[A-Z]{4}\d{16}$/.test(iban))
    return "A Pakistani IBAN is PK, 2 digits, 4 bank letters and 16 digits";
  const moved = iban.slice(4) + iban.slice(0, 4);
  let rest = 0;
  for (const ch of moved) {
    const n = parseInt(ch, 36).toString();
    for (const d of n) rest = (rest * 10 + Number(d)) % 97;
  }
  return rest === 1 ? null : "Check the IBAN — it doesn't look right";
}

function titleError(value: string): string | null {
  return value.trim().length >= 2 ? null : "Enter the name on the account";
}

function walletNumberError(value: string): string | null {
  return /^(\+92|0)3\d{9}$/.test(value.trim())
    ? null
    : "Use a mobile number like 03001234567";
}

function accountNumberError(value: string): string | null {
  return /^[0-9 -]*$/.test(value) ? null : "Use digits only";
}

function SettingsForm({ initial }: { initial: PaymentSettings }) {
  const can = useCan();
  const editable = can("billing.write") && can("pi.settings.manage");
  const [form, setForm] = React.useState(initial);
  const [attempted, setAttempted] = React.useState(false);
  const bankErrors = form.bank_accounts.map((a) => ({
    title: titleError(a.account_title),
    iban: ibanError(a.iban),
    number: accountNumberError(a.account_number),
  }));
  const walletErrors = form.wallets.map((w) => ({
    title: titleError(w.account_title),
    number: walletNumberError(w.number),
  }));
  const invalid =
    (form.bank_enabled &&
      bankErrors.some((e) => e.title || e.iban || e.number)) ||
    (form.wallet_enabled && walletErrors.some((e) => e.title || e.number));
  const show = (error: string | null) => (attempted ? error : null);
  const save = useAction(
    () =>
      put<PaymentSettings>("/pi/customer-payments/settings", {
        stripe_enabled: form.stripe_enabled && initial.stripe_connected,
        bank_enabled: form.bank_enabled,
        bank_accounts: form.bank_accounts,
        wallet_enabled: form.wallet_enabled,
        wallets: form.wallets,
        cash_enabled: form.cash_enabled,
        cash_instructions: form.cash_instructions,
        payment_note: form.payment_note,
      }),
    { invalidate: [["payment-settings"]], success: "Payment methods saved" },
  );
  const setBank = (i: number, patch: Partial<BankAccount>) =>
    setForm((f) => ({
      ...f,
      bank_accounts: f.bank_accounts.map((a, j) =>
        j === i ? { ...a, ...patch } : a,
      ),
    }));
  const setWallet = (i: number, patch: Partial<WalletAccount>) =>
    setForm((f) => ({
      ...f,
      wallets: f.wallets.map((w, j) => (j === i ? { ...w, ...patch } : w)),
    }));

  return (
    <div className="space-y-4">
      <Card>
        <CardSection className="space-y-4">
          <div className="flex items-center gap-3">
            <CreditCard className="size-5 text-accent" aria-hidden />
            <h2 className="flex-1 font-semibold">Card payments (Stripe)</h2>
            <Switch
              id="stripe"
              label="Accept card payments"
              checked={form.stripe_enabled}
              disabled={!editable || !initial.stripe_connected}
              onCheckedChange={(v) =>
                setForm((f) => ({ ...f, stripe_enabled: v }))
              }
            />
          </div>
          {editable ? (
            <StripeConnect connected={initial.stripe_connected} />
          ) : null}
        </CardSection>
      </Card>

      <Card>
        <CardSection className="space-y-4">
          <div className="flex items-center gap-3">
            <Banknote className="size-5 text-accent" aria-hidden />
            <h2 className="flex-1 font-semibold">Bank transfer</h2>
            <Switch
              id="bank"
              label="Accept bank transfers"
              checked={form.bank_enabled}
              disabled={!editable}
              onCheckedChange={(v) =>
                setForm((f) => ({ ...f, bank_enabled: v }))
              }
            />
          </div>
          <p className="text-sm text-muted-foreground">
            Customers get your account details and a payment reference. You
            confirm when the money arrives — a screenshot alone never marks a
            payment as paid.
          </p>
          {form.bank_accounts.map((a, i) => (
            <div
              key={i}
              className="grid gap-3 rounded-lg border border-border p-3 sm:grid-cols-2"
            >
              <Field label="Bank" htmlFor={`bank-${i}`}>
                <Select
                  id={`bank-${i}`}
                  value={a.bank}
                  disabled={!editable}
                  onChange={(e) => setBank(i, { bank: e.target.value })}
                >
                  {initial.banks.map((b) => (
                    <option key={b}>{b}</option>
                  ))}
                </Select>
              </Field>
              <Field
                label="Account title"
                htmlFor={`title-${i}`}
                error={
                  form.bank_enabled ? show(bankErrors[i]?.title ?? null) : null
                }
              >
                <Input
                  id={`title-${i}`}
                  value={a.account_title}
                  disabled={!editable}
                  onChange={(e) =>
                    setBank(i, { account_title: e.target.value })
                  }
                />
              </Field>
              <Field
                label="IBAN"
                htmlFor={`iban-${i}`}
                hint="PK followed by 22 characters"
                error={
                  form.bank_enabled ? show(bankErrors[i]?.iban ?? null) : null
                }
              >
                <Input
                  id={`iban-${i}`}
                  value={a.iban}
                  disabled={!editable}
                  placeholder="PK36SCBL0000001123456702"
                  onChange={(e) =>
                    setBank(i, { iban: e.target.value.toUpperCase() })
                  }
                />
              </Field>
              <Field
                label="Account number"
                htmlFor={`acct-${i}`}
                optional
                error={
                  form.bank_enabled ? show(bankErrors[i]?.number ?? null) : null
                }
              >
                <Input
                  id={`acct-${i}`}
                  value={a.account_number}
                  disabled={!editable}
                  inputMode="numeric"
                  onChange={(e) =>
                    setBank(i, { account_number: e.target.value })
                  }
                />
              </Field>
              <Field label="Branch" htmlFor={`branch-${i}`} optional>
                <Input
                  id={`branch-${i}`}
                  value={a.branch}
                  disabled={!editable}
                  onChange={(e) => setBank(i, { branch: e.target.value })}
                />
              </Field>
              {editable ? (
                <div className="flex items-end">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() =>
                      setForm((f) => ({
                        ...f,
                        bank_accounts: f.bank_accounts.filter(
                          (_, j) => j !== i,
                        ),
                      }))
                    }
                  >
                    <Trash2 className="size-4" aria-hidden /> Remove account
                  </Button>
                </div>
              ) : null}
            </div>
          ))}
          {editable && form.bank_accounts.length < 5 ? (
            <Button
              variant="secondary"
              size="sm"
              onClick={() =>
                setForm((f) => ({
                  ...f,
                  bank_accounts: [
                    ...f.bank_accounts,
                    {
                      bank: initial.banks[0] ?? "Other",
                      account_title: "",
                      account_number: "",
                      iban: "",
                      branch: "",
                    },
                  ],
                }))
              }
            >
              <Plus className="size-4" aria-hidden /> Add bank account
            </Button>
          ) : null}
        </CardSection>
      </Card>

      <Card>
        <CardSection className="space-y-4">
          <div className="flex items-center gap-3">
            <Smartphone className="size-5 text-accent" aria-hidden />
            <h2 className="flex-1 font-semibold">Mobile wallets</h2>
            <Switch
              id="wallet"
              label="Accept mobile wallets"
              checked={form.wallet_enabled}
              disabled={!editable}
              onCheckedChange={(v) =>
                setForm((f) => ({ ...f, wallet_enabled: v }))
              }
            />
          </div>
          {form.wallets.map((w, i) => (
            <div
              key={i}
              className="grid gap-3 rounded-lg border border-border p-3 sm:grid-cols-3"
            >
              <Field label="Wallet" htmlFor={`wp-${i}`}>
                <Select
                  id={`wp-${i}`}
                  value={w.provider}
                  disabled={!editable}
                  onChange={(e) =>
                    setWallet(i, {
                      provider: e.target.value as WalletAccount["provider"],
                    })
                  }
                >
                  {Object.entries(initial.wallet_providers).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field
                label="Account title"
                htmlFor={`wt-${i}`}
                error={
                  form.wallet_enabled
                    ? show(walletErrors[i]?.title ?? null)
                    : null
                }
              >
                <Input
                  id={`wt-${i}`}
                  value={w.account_title}
                  disabled={!editable}
                  onChange={(e) =>
                    setWallet(i, { account_title: e.target.value })
                  }
                />
              </Field>
              <Field
                label="Mobile number"
                htmlFor={`wn-${i}`}
                error={
                  form.wallet_enabled
                    ? show(walletErrors[i]?.number ?? null)
                    : null
                }
              >
                <Input
                  id={`wn-${i}`}
                  value={w.number}
                  disabled={!editable}
                  inputMode="tel"
                  placeholder="03001234567"
                  onChange={(e) => setWallet(i, { number: e.target.value })}
                />
              </Field>
            </div>
          ))}
          {editable && form.wallets.length < 5 ? (
            <Button
              variant="secondary"
              size="sm"
              onClick={() =>
                setForm((f) => ({
                  ...f,
                  wallets: [
                    ...f.wallets,
                    { provider: "jazzcash", account_title: "", number: "" },
                  ],
                }))
              }
            >
              <Plus className="size-4" aria-hidden /> Add wallet
            </Button>
          ) : null}
        </CardSection>
      </Card>

      <Card>
        <CardSection className="space-y-4">
          <div className="flex items-center gap-3">
            <Wallet className="size-5 text-accent" aria-hidden />
            <h2 className="flex-1 font-semibold">Cash</h2>
            <Switch
              id="cash"
              label="Accept cash"
              checked={form.cash_enabled}
              disabled={!editable}
              onCheckedChange={(v) =>
                setForm((f) => ({ ...f, cash_enabled: v }))
              }
            />
          </div>
          <Field label="Where and how customers pay cash" htmlFor="cash-i">
            <Textarea
              id="cash-i"
              value={form.cash_instructions}
              disabled={!editable}
              maxLength={1000}
              placeholder="Cash on delivery, or at our office in Gulberg"
              onChange={(e) =>
                setForm((f) => ({ ...f, cash_instructions: e.target.value }))
              }
            />
          </Field>
          <Field
            label="Note added to every payment message"
            htmlFor="note"
            optional
          >
            <Textarea
              id="note"
              value={form.payment_note}
              disabled={!editable}
              maxLength={1000}
              onChange={(e) =>
                setForm((f) => ({ ...f, payment_note: e.target.value }))
              }
            />
          </Field>
        </CardSection>
      </Card>

      {editable ? (
        <div className="flex justify-end">
          <Button
            loading={save.isPending}
            onClick={() => {
              setAttempted(true);
              if (!invalid) save.mutate(undefined);
            }}
          >
            Save payment methods
          </Button>
        </div>
      ) : null}
    </div>
  );
}

function RequestLinkActions({ requestId }: { requestId: string }) {
  const copyLink = useAction(
    () =>
      post<{ token: string; url: string; expires_at: string }>(
        `/pi/payment-requests/${requestId}/link`,
      ),
    {
      success: "Payment link copied — share it with the customer",
      onSuccess: async (link) => {
        try {
          await navigator.clipboard.writeText(link.url);
        } catch {
          // Clipboard access can be denied; the link is still valid, just not copied.
        }
      },
    },
  );
  const downloadQr = useAction(
    () =>
      post<{ token: string; url: string; expires_at: string }>(
        `/pi/payment-requests/${requestId}/link`,
      ),
    {
      onSuccess: (link) => {
        const a = document.createElement("a");
        a.href = `/api/v1/pi-app/pay/request/${link.token}/qr.png`;
        a.download = `pi-payment-qr-${requestId.slice(0, 8)}.png`;
        a.click();
      },
    },
  );
  return (
    <>
      <Button
        size="sm"
        variant="secondary"
        loading={copyLink.isPending}
        onClick={() => copyLink.mutate(undefined)}
      >
        <Link2 size={14} aria-hidden />
        Copy link
      </Button>
      <Button
        size="sm"
        variant="secondary"
        loading={downloadQr.isPending}
        onClick={() => downloadQr.mutate(undefined)}
      >
        <QrCode size={14} aria-hidden />
        QR
      </Button>
    </>
  );
}

function RequestsQueue() {
  const key = useBusinessKey();
  const can = useCan();
  const [filter, setFilter] = React.useState("active");
  const [verifying, setVerifying] = React.useState<PaymentRequest | null>(null);
  const [reference, setReference] = React.useState("");
  const list = useQuery({
    queryKey: key(["payment-requests", filter]),
    queryFn: () =>
      get<PaymentRequest[]>("/pi/payment-requests", {
        status: filter || undefined,
      }),
    refetchInterval: 30_000,
  });
  const verify = useAction(
    ({ id, received }: { id: string; received: boolean }) =>
      post<PaymentRequest>(`/pi/payment-requests/${id}/verify`, {
        received,
        reference,
      }),
    {
      invalidate: [["payment-requests"]],
      success: (r) =>
        r.status === "paid"
          ? "Marked as paid and recorded on the invoice"
          : "Kept open — ask the customer to check",
      onSuccess: () => {
        setVerifying(null);
        setReference("");
      },
    },
  );
  return (
    <Card>
      <CardSection className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="flex-1 font-semibold">Payment requests</h2>
          <Select
            aria-label="Filter requests"
            className="h-9 w-56"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          >
            <option value="active">To handle</option>
            <option value="awaiting_verification">Customer says paid</option>
            <option value="open">Waiting for payment</option>
            <option value="paid">Paid</option>
            <option value="">All</option>
          </Select>
        </div>
        {list.isPending ? (
          <LoadingBlock rows={2} />
        ) : list.isError ? (
          <ErrorState
            message={errorText(list.error)}
            onRetry={() => list.refetch()}
          />
        ) : !list.data.length ? (
          <EmptyState title="Nothing here">
            Requests appear when you or pi send payment details.
          </EmptyState>
        ) : (
          <ul className="divide-y divide-border">
            {list.data.map((r) => (
              <li
                key={r.id}
                className="flex flex-wrap items-center gap-3 py-3 text-sm"
              >
                <span className="min-w-0 flex-1">
                  <span className="font-medium tabular-nums">
                    {money(r.amount, r.currency)}
                  </span>{" "}
                  · {METHOD_LABEL[r.method] ?? r.method}
                  <span className="block text-xs text-muted-foreground">
                    {r.reference} · {date(r.created_at)}
                    {r.proof_note ? ` · customer: “${r.proof_note}”` : ""}
                  </span>
                </span>
                <PaymentStatus status={r.status} />
                {can("billing.write") &&
                ["open", "awaiting_verification"].includes(r.status) ? (
                  <RequestLinkActions requestId={r.id} />
                ) : null}
                {can("billing.write") &&
                r.method !== "stripe" &&
                ["open", "awaiting_verification"].includes(r.status) ? (
                  <Button size="sm" onClick={() => setVerifying(r)}>
                    Verify
                  </Button>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </CardSection>
      <Dialog
        open={Boolean(verifying)}
        onOpenChange={(v) => (!v ? setVerifying(null) : null)}
      >
        <DialogContent
          title="Did the money arrive?"
          description={
            verifying
              ? `Check your ${METHOD_LABEL[verifying.method]?.toLowerCase()} for ${money(verifying.amount, verifying.currency)} with reference ${verifying.reference}.`
              : undefined
          }
        >
          <div className="space-y-4">
            <Field label="Bank or wallet transaction ID" htmlFor="txn" optional>
              <Input
                id="txn"
                value={reference}
                onChange={(e) => setReference(e.target.value)}
                maxLength={120}
              />
            </Field>
            <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
              <Button
                variant="secondary"
                loading={verify.isPending}
                onClick={() =>
                  verifying &&
                  verify.mutate({ id: verifying.id, received: false })
                }
              >
                Not received
              </Button>
              <Button
                loading={verify.isPending}
                onClick={() =>
                  verifying &&
                  verify.mutate({ id: verifying.id, received: true })
                }
              >
                Yes, I received it
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

export function GettingPaid() {
  const key = useBusinessKey();
  const can = useCan();
  const settings = useQuery({
    queryKey: key(["payment-settings"]),
    queryFn: () => get<PaymentSettings>("/pi/customer-payments/settings"),
    enabled: can("billing.read"),
  });
  if (!can("billing.read")) {
    return (
      <Notice tone="info">
        Ask your business owner for access to payments.
      </Notice>
    );
  }
  if (settings.isPending) return <LoadingBlock rows={3} />;
  if (settings.isError)
    return (
      <ErrorState
        message={errorText(settings.error)}
        onRetry={() => settings.refetch()}
      />
    );
  return (
    <div className="space-y-6">
      <Notice tone="info" title="How getting paid works">
        When a customer asks how to pay an invoice, pi sends the exact amount,
        your details and a payment reference. Cards are confirmed by Stripe
        automatically; bank, wallet and cash payments count once you confirm
        them.
      </Notice>
      <RequestsQueue />
      <SettingsForm
        key={JSON.stringify(settings.data)}
        initial={settings.data}
      />
    </div>
  );
}
