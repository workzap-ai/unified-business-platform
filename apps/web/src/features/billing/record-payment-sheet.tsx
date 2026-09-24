"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { formatMoney, toCents } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input, NativeSelect } from "@/components/ui/input";
import { Dialog, DialogHeader, SheetContent } from "@/components/ui/overlays";
import { FormField } from "@/components/app/forms";
import { InlineError } from "@/components/app/states";
import { useScopedMutation } from "@/hooks/use-scoped";
import { errorMessage } from "@/services/api-client";
import type { InvoiceDetail, Payment } from "@/features/business/types";
import { billingService } from "./service";
import { MONEY_PATTERN, PAYMENT_METHODS, todayISO } from "./utils";

export function RecordPaymentSheet({
  invoice,
  open,
  onOpenChange,
}: {
  invoice: InvoiceDetail;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <SheetContent width="md">
        {open && <PaymentForm invoice={invoice} onDone={() => onOpenChange(false)} />}
      </SheetContent>
    </Dialog>
  );
}

function PaymentForm({ invoice, onDone }: { invoice: InvoiceDetail; onDone: () => void }) {
  const balance = toCents(invoice.balance_due);
  const [serverError, setServerError] = useState<string | null>(null);
  const schema = z.object({
    amount: z
      .string()
      .trim()
      .regex(MONEY_PATTERN, "Use an amount like 250.00")
      .refine((v) => toCents(v) > BigInt(0), "Enter an amount greater than zero")
      .refine(
        (v) => toCents(v) <= balance,
        `Can't exceed the balance due of ${formatMoney(invoice.balance_due, invoice.currency)}`,
      ),
    method: z.enum(["cash", "bank_transfer", "card", "mobile_wallet", "other"]),
    received_on: z
      .string()
      .min(1, "Choose the date the money arrived")
      .refine((v) => v <= todayISO(), "The date can't be in the future"),
    reference: z.string().trim().max(120, "Keep the reference under 120 characters"),
  });
  type Values = z.infer<typeof schema>;
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { amount: invoice.balance_due, method: "bank_transfer", received_on: todayISO(), reference: "" },
  });
  const { register, handleSubmit, formState } = form;
  const { errors } = formState;

  const record = useScopedMutation(
    (input: { amount: string; method: Payment["method"]; received_on: string; reference: string }) =>
      billingService.recordPayment(invoice.id, input),
    {
      invalidate: [["invoices"], ["billing"], ["payments"], ["finance"]],
      success: (payment) => `Payment ${payment.number} recorded`,
      onSuccess: onDone,
    },
  );

  const onSubmit = handleSubmit((values) => {
    setServerError(null);
    record.mutate(
      { amount: values.amount.trim(), method: values.method, received_on: values.received_on, reference: values.reference.trim() },
      { onError: (e) => setServerError(errorMessage(e, "The payment couldn't be recorded.")) },
    );
  });

  const saving = record.isPending;

  return (
    <form onSubmit={onSubmit} noValidate className="flex h-full min-h-0 flex-col">
      <DialogHeader
        title="Record payment"
        description={`Money received against ${invoice.number}${invoice.customer_name ? ` from ${invoice.customer_name}` : ""}.`}
      />
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-4">
        <dl className="grid grid-cols-2 gap-3 rounded-lg bg-surface-muted/70 p-3 text-[13px]">
          <div>
            <dt className="text-xs text-muted-foreground">Invoice total</dt>
            <dd className="tabular font-medium">{formatMoney(invoice.total, invoice.currency)}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Balance due</dt>
            <dd className="tabular font-semibold">{formatMoney(invoice.balance_due, invoice.currency)}</dd>
          </div>
        </dl>
        {serverError && <InlineError message={serverError} />}
        <FormField
          label={`Amount (${invoice.currency})`}
          htmlFor="payment-amount"
          required
          error={errors.amount?.message}
          help="A partial amount leaves the rest of the balance open."
        >
          <Input
            id="payment-amount"
            inputMode="decimal"
            className="tabular"
            autoFocus
            aria-invalid={Boolean(errors.amount) || undefined}
            disabled={saving}
            {...register("amount")}
          />
        </FormField>
        <FormField label="Method" htmlFor="payment-method" required error={errors.method?.message}>
          <NativeSelect id="payment-method" disabled={saving} {...register("method")}>
            {PAYMENT_METHODS.map((m) => (
              <option key={m.value} value={m.value}>
                {m.label}
              </option>
            ))}
          </NativeSelect>
        </FormField>
        <FormField label="Received on" htmlFor="payment-date" required error={errors.received_on?.message}>
          <Input
            id="payment-date"
            type="date"
            max={todayISO()}
            aria-invalid={Boolean(errors.received_on) || undefined}
            disabled={saving}
            {...register("received_on")}
          />
        </FormField>
        <FormField
          label="Reference"
          htmlFor="payment-reference"
          optional
          error={errors.reference?.message}
          help="Bank reference, receipt or transaction ID."
        >
          <Input id="payment-reference" disabled={saving} {...register("reference")} />
        </FormField>
      </div>
      <div className="flex flex-col-reverse gap-2 border-t border-border bg-surface-muted/60 px-5 py-3 sm:flex-row sm:justify-end">
        <Button type="button" variant="secondary" onClick={onDone} disabled={saving}>
          Cancel
        </Button>
        <Button type="submit" loading={saving}>
          Record payment
        </Button>
      </div>
    </form>
  );
}
