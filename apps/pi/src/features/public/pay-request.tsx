"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CreditCard, Download, Lock, ShieldCheck, Upload } from "lucide-react";
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
import { Wordmark } from "@/components/brand";
import { ApiError, errorText } from "@/lib/api";
import { money } from "@/lib/format";
import { publicGet, publicPost } from "@/lib/public-api";

interface RequestView {
  id: string;
  invoice_id: string;
  method: "stripe" | "bank_transfer" | "mobile_wallet" | "cash";
  status: "open" | "awaiting_verification";
  amount: string;
  currency: string;
  reference: string;
  checkout_url: string | null;
  proof_note: string;
  created_at: string;
  expires_at: string | null;
  message: string;
}

const METHOD_LABEL: Record<RequestView["method"], string> = {
  stripe: "Card (Stripe)",
  bank_transfer: "Bank transfer",
  mobile_wallet: "Mobile wallet",
  cash: "Cash",
};

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
  onSubmitted,
}: {
  token: string;
  onSubmitted: (view: RequestView) => void;
}) {
  const [note, setNote] = React.useState("");
  const [reference, setReference] = React.useState("");
  const [file, setFile] = React.useState<File | null>(null);
  const fileTooLarge = Boolean(file && file.size > 5 * 1024 * 1024);
  const submit = useMutation({
    mutationFn: () => {
      const body = new FormData();
      body.append("note", note);
      body.append("reference", reference);
      if (file) body.append("file", file);
      return publicPost<RequestView>(`/pay/request/${token}/proof`, body);
    },
    onSuccess: onSubmitted,
  });
  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (!fileTooLarge) submit.mutate();
      }}
    >
      {submit.isError ? (
        <Notice tone="danger" title="Couldn't submit your proof">
          {errorText(submit.error)}
        </Notice>
      ) : null}
      <Field
        label="Transaction reference (optional)"
        htmlFor="req-reference"
        optional
      >
        <Input
          id="req-reference"
          value={reference}
          onChange={(e) => setReference(e.target.value)}
          maxLength={120}
        />
      </Field>
      <Field
        label="Receipt photo or PDF (optional)"
        htmlFor="req-proof"
        optional
        hint="PDF, PNG or JPEG, up to 5 MB."
      >
        <Input
          id="req-proof"
          type="file"
          accept="application/pdf,image/png,image/jpeg"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          className="h-auto py-2"
        />
      </Field>
      {fileTooLarge ? (
        <p role="alert" className="text-sm text-danger">
          Choose a file smaller than 5 MB.
        </p>
      ) : null}
      <Field label="Note (optional)" htmlFor="req-note" optional>
        <Textarea
          id="req-note"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          maxLength={2000}
          placeholder="e.g. Paid from my JazzCash wallet just now"
        />
      </Field>
      <Button
        type="submit"
        className="w-full"
        loading={submit.isPending}
        disabled={fileTooLarge}
      >
        <Upload size={16} aria-hidden />
        Tell them you&rsquo;ve paid
      </Button>
    </form>
  );
}

function RequestCard({
  token,
  request,
  onChange,
}: {
  token: string;
  request: RequestView;
  onChange: (view: RequestView) => void;
}) {
  const qrUrl = `/api/v1/pi-app/pay/request/${token}/qr.png`;
  return (
    <div className="space-y-5">
      <Card>
        <CardSection className="space-y-4">
          <div>
            <p className="mt-1 text-3xl font-semibold tracking-tight">
              {money(request.amount, request.currency)}
            </p>
            <p className="mt-1 text-sm text-muted-foreground">
              {METHOD_LABEL[request.method]}
              {request.reference ? ` · Ref: ${request.reference}` : ""}
            </p>
          </div>
          <Badge tone={request.status === "awaiting_verification" ? "warning" : "neutral"}>
            {request.status === "awaiting_verification"
              ? "Check your account"
              : "Waiting for payment"}
          </Badge>
          <p className="whitespace-pre-wrap text-sm text-muted-foreground">
            {request.message}
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
      {request.method === "stripe" ? (
        request.checkout_url ? (
          <Button asChild className="w-full">
            <a href={request.checkout_url} target="_blank" rel="noreferrer">
              <CreditCard size={16} aria-hidden />
              Pay by card
            </a>
          </Button>
        ) : (
          <Notice tone="info">
            Card checkout isn&rsquo;t ready yet. Try again shortly.
          </Notice>
        )
      ) : request.status === "awaiting_verification" ? (
        <Notice tone="info" title="Thanks — we've let them know">
          They&rsquo;ll confirm the payment on their end. This does not mark
          the invoice as paid on its own.
        </Notice>
      ) : (
        <Card>
          <CardSection>
            <ProofForm token={token} onSubmitted={onChange} />
          </CardSection>
        </Card>
      )}
    </div>
  );
}

export function PayRequestPage({ token }: { token: string }) {
  const client = useQueryClient();
  const queryKey = ["pay-link-request", token];
  const view = useQuery({
    queryKey,
    queryFn: () => publicGet<RequestView>(`/pay/request/${token}`),
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
            It may have expired, already been used, or the payment may already
            be settled. Ask for a fresh link.
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
      <RequestCard
        token={token}
        request={view.data}
        onChange={(next) => client.setQueryData(queryKey, next)}
      />
      <p className="flex items-center justify-center gap-1.5 text-center text-xs text-muted-foreground">
        <ShieldCheck size={13} aria-hidden />
        Only someone with this exact link can view or act on this payment.
      </p>
    </Shell>
  );
}
