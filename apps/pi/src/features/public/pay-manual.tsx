"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Lock, ShieldCheck, Upload } from "lucide-react";
import Image from "next/image";
import * as React from "react";

import {
  Badge,
  Button,
  Card,
  CardSection,
  ErrorState,
  Field,
  Input,
  LoadingBlock,
  Notice,
  Textarea,
} from "@/components/ui";
import { ApiError, errorText } from "@/lib/api";
import { money } from "@/lib/format";
import { publicGet, publicPost } from "@/lib/public-api";
import { Wordmark } from "@/components/brand";

interface ManualPayView {
  id: string;
  plan: string;
  plan_name: string;
  method: "bank_transfer" | "cash";
  status: "awaiting_payment" | "submitted";
  months: number;
  amount: string;
  currency: string;
  instructions: Record<string, string>;
  payer_name: string;
  reference: string;
  paid_on: string | null;
  note: string;
  has_proof: boolean;
  review_note: string;
  receipt_number: string | null;
  created_at: string;
  submitted_at: string | null;
  business_name: string;
}

const todayISO = () => new Date().toLocaleDateString("en-CA");

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto flex min-h-dvh max-w-md flex-col gap-6 px-4 py-10 sm:py-14">
      <div className="flex items-center justify-between">
        <Wordmark className="text-xl" />
        <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
          <Lock className="size-3.5" aria-hidden />
          Secure payment page
        </span>
      </div>
      {children}
    </div>
  );
}

function ProofForm({
  token,
  payment,
  onSubmitted,
}: {
  token: string;
  payment: ManualPayView;
  onSubmitted: (view: ManualPayView) => void;
}) {
  const [payerName, setPayerName] = React.useState(payment.payer_name);
  const [reference, setReference] = React.useState(payment.reference);
  const [paidOn, setPaidOn] = React.useState(payment.paid_on ?? todayISO());
  const [note, setNote] = React.useState(payment.note);
  const [file, setFile] = React.useState<File | null>(null);
  const [confirmed, setConfirmed] = React.useState(false);
  const bank = payment.method === "bank_transfer";
  const submit = useMutation({
    mutationFn: () => {
      const body = new FormData();
      body.append("payer_name", payerName);
      body.append("paid_on", paidOn);
      body.append("reference", reference);
      body.append("note", note);
      if (file) body.append("file", file);
      return publicPost<ManualPayView>(`/pay/${token}/proof`, body);
    },
    onSuccess: onSubmitted,
  });
  const fileTooLarge = Boolean(file && file.size > 5 * 1024 * 1024);
  const canSubmit =
    confirmed &&
    payerName.trim().length >= 2 &&
    Boolean(paidOn) &&
    Boolean(file) &&
    !fileTooLarge;
  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (canSubmit) submit.mutate();
      }}
    >
      {submit.isError ? (
        <Notice tone="danger" title="Couldn't submit your proof">
          {errorText(submit.error)}
        </Notice>
      ) : null}
      <Field label="Name of payer" htmlFor="pay-payer">
        <Input
          id="pay-payer"
          value={payerName}
          onChange={(e) => setPayerName(e.target.value)}
          required
          minLength={2}
          maxLength={160}
        />
      </Field>
      <Field
        label={
          bank ? "Bank transaction reference" : "Receipt reference (optional)"
        }
        htmlFor="pay-reference"
        optional={!bank}
      >
        <Input
          id="pay-reference"
          value={reference}
          onChange={(e) => setReference(e.target.value)}
          maxLength={120}
        />
      </Field>
      <Field label="Date paid" htmlFor="pay-date">
        <Input
          id="pay-date"
          type="date"
          value={paidOn}
          onChange={(e) => setPaidOn(e.target.value)}
          required
          max={todayISO()}
        />
      </Field>
      <Field
        label="Receipt photo or PDF"
        htmlFor="pay-proof"
        hint="PDF, PNG or JPEG, up to 5 MB. Do not include account passwords or PINs."
      >
        <Input
          id="pay-proof"
          type="file"
          accept="application/pdf,image/png,image/jpeg"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          className="h-auto py-2"
          required
        />
      </Field>
      {fileTooLarge ? (
        <p role="alert" className="text-sm text-danger">
          Choose a file smaller than 5 MB.
        </p>
      ) : null}
      <Field label="Note (optional)" htmlFor="pay-note" optional>
        <Textarea
          id="pay-note"
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
      <Button
        type="submit"
        className="w-full"
        loading={submit.isPending}
        disabled={!canSubmit}
      >
        <Upload size={16} aria-hidden />
        Submit for verification
      </Button>
    </form>
  );
}

function PaymentCard({
  token,
  payment,
  onChange,
}: {
  token: string;
  payment: ManualPayView;
  onChange: (view: ManualPayView) => void;
}) {
  const bank = payment.method === "bank_transfer";
  const qrUrl = `/api/v1/pi-app/pay/${token}/qr.png`;
  return (
    <div className="space-y-5">
      <Card>
        <CardSection className="space-y-4">
          <div>
            <p className="text-sm text-muted-foreground">
              {payment.business_name}
            </p>
            <p className="mt-1 text-sm">
              {payment.plan_name} · {payment.months} month
              {payment.months > 1 ? "s" : ""}
            </p>
            <p className="mt-1 text-3xl font-semibold tracking-tight">
              {money(payment.amount, payment.currency)}
            </p>
          </div>
          <Badge tone={payment.status === "submitted" ? "warning" : "neutral"}>
            {payment.status === "submitted"
              ? "Under review"
              : "Awaiting payment"}
          </Badge>
          <dl className="space-y-2 text-sm">
            <div>
              <dt className="text-muted-foreground">Pay to</dt>
              <dd className="font-medium">
                {payment.instructions.seller_name}
              </dd>
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
        </CardSection>
      </Card>
      <Card>
        <CardSection className="flex flex-col items-center gap-3 text-center">
          <Image
            src={qrUrl}
            alt="QR code that opens this payment page"
            width={176}
            height={176}
            unoptimized
            className="rounded-lg border border-border"
          />
          <p className="text-xs text-muted-foreground">
            Scan to open this page on another device.
          </p>
          <a
            href={qrUrl}
            download={`pi-payment-qr-${token.slice(0, 8)}.png`}
            className="inline-flex items-center gap-1.5 text-sm text-accent underline"
          >
            <Download size={14} aria-hidden />
            Download QR
          </a>
        </CardSection>
      </Card>
      {payment.status === "submitted" ? (
        <Notice tone="info" title="The billing team is checking your payment">
          Submitting a receipt does not mark it as paid. The business&rsquo;s
          subscription updates once it&rsquo;s verified.
        </Notice>
      ) : (
        <Card>
          <CardSection>
            <ProofForm token={token} payment={payment} onSubmitted={onChange} />
          </CardSection>
        </Card>
      )}
    </div>
  );
}

export function PayManualPage({ token }: { token: string }) {
  const client = useQueryClient();
  const queryKey = ["pay-link-manual", token];
  const view = useQuery({
    queryKey,
    queryFn: () => publicGet<ManualPayView>(`/pay/${token}`),
    retry: false,
    staleTime: Infinity,
  });

  if (view.isPending) {
    return (
      <Shell>
        <LoadingBlock rows={3} />
      </Shell>
    );
  }

  if (view.isError) {
    const status = view.error instanceof ApiError ? view.error.status : 0;
    if (status === 404) {
      return (
        <Shell>
          <Notice tone="warning" title="This link isn't available">
            It may have expired, already been used, or the payment may have
            already been resolved. Ask the business for a fresh link.
          </Notice>
        </Shell>
      );
    }
    if (status === 429) {
      return (
        <Shell>
          <Notice tone="warning" title="Too many attempts">
            Please wait a while before trying this link again.
          </Notice>
        </Shell>
      );
    }
    return (
      <Shell>
        <ErrorState
          message={errorText(view.error)}
          onRetry={() => view.refetch()}
        />
      </Shell>
    );
  }

  return (
    <Shell>
      <PaymentCard
        token={token}
        payment={view.data}
        onChange={(next) => client.setQueryData(queryKey, next)}
      />
      <p className="flex items-center justify-center gap-1.5 text-center text-xs text-muted-foreground">
        <ShieldCheck size={13} aria-hidden />
        Only someone with this exact link can view or act on this payment.
      </p>
    </Shell>
  );
}
