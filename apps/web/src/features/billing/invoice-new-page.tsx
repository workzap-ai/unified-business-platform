"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Controller,
  useFieldArray,
  useForm,
  useWatch,
  type Control,
} from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Info, Plus, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { centsToString, formatMoney } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/display";
import {
  PageHeader,
  PageShell,
  RequirePermission,
} from "@/components/app/page";
import {
  FormActions,
  FormField,
  FormSection,
  useUnsavedChangesWarning,
} from "@/components/app/forms";
import { InlineError, Notice } from "@/components/app/states";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { errorMessage } from "@/services/api-client";
import { adminService } from "@/features/admin/service";
import { billingService } from "./service";
import { CustomerPicker } from "./customer-picker";
import {
  MONEY_PATTERN,
  QUANTITY_PATTERN,
  formatRate,
  lineGrossCents,
  scaled,
  taxCents,
  todayISO,
} from "./utils";

const lineSchema = z
  .object({
    description: z
      .string()
      .trim()
      .min(1, "Describe what you're billing for")
      .max(500, "Keep it under 500 characters"),
    quantity: z
      .string()
      .trim()
      .regex(QUANTITY_PATTERN, "Use a number like 1 or 2.5")
      .refine((v) => scaled(v, 3) > BigInt(0), "Must be more than zero"),
    unit_price: z
      .string()
      .trim()
      .regex(MONEY_PATTERN, "Use an amount like 120.00"),
    discount: z.string().trim().regex(MONEY_PATTERN, "Use an amount like 5.00"),
  })
  .superRefine((line, ctx) => {
    if (
      !MONEY_PATTERN.test(line.discount) ||
      !MONEY_PATTERN.test(line.unit_price)
    )
      return;
    if (!QUANTITY_PATTERN.test(line.quantity)) return;
    if (
      scaled(line.discount, 2) > lineGrossCents(line.unit_price, line.quantity)
    ) {
      ctx.addIssue({
        code: "custom",
        path: ["discount"],
        message: "Discount can't exceed the line amount",
      });
    }
  });

const schema = z.object({
  customer: z
    .object({
      id: z.string(),
      name: z.string(),
      detail: z.string().nullable().optional(),
    })
    .nullable()
    .refine((v): boolean => v !== null, "Choose who this invoice is for"),
  due_date: z
    .string()
    .refine((v) => !v || v >= todayISO(), "The due date can't be in the past"),
  notes: z.string().max(2000, "Keep notes under 2,000 characters"),
  lines: z.array(lineSchema).min(1, "Add at least one line"),
});

type FormValues = z.infer<typeof schema>;

const EMPTY_LINE = {
  description: "",
  quantity: "1",
  unit_price: "",
  discount: "0.00",
};

export function InvoiceNewPage() {
  return (
    <RequirePermission permission="billing.write" area="invoice creation">
      <InvoiceForm />
    </RequirePermission>
  );
}

function InvoiceForm() {
  const router = useRouter();
  const [serverError, setServerError] = useState<string | null>(null);
  const [created, setCreated] = useState(false);
  const settings = useScopedQuery(
    ["settings", "business"],
    () => adminService.businessSettings(),
    {
      staleTime: 60_000,
    },
  );

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      customer: null,
      due_date: "",
      notes: "",
      lines: [{ ...EMPTY_LINE }],
    },
    mode: "onTouched",
  });
  const { control, register, handleSubmit, formState } = form;
  const { errors, isDirty } = formState;
  const lines = useFieldArray({ control, name: "lines" });

  const create = useScopedMutation(billingService.createInvoice, {
    invalidate: [["invoices"], ["billing"]],
    success: (invoice) => `Draft ${invoice.number} created`,
    onSuccess: (invoice) => {
      setCreated(true);
      router.push(`/billing/invoices/${invoice.id}`);
    },
  });
  useUnsavedChangesWarning(isDirty && !created);

  const onSubmit = handleSubmit((values) => {
    if (!values.customer) return;
    setServerError(null);
    create.mutate(
      {
        customer_id: values.customer.id,
        due_date: values.due_date || null,
        notes: values.notes.trim(),
        lines: values.lines.map((l) => ({
          description: l.description.trim(),
          quantity: l.quantity.trim(),
          unit_price: l.unit_price.trim(),
          discount: l.discount.trim() || "0.00",
        })),
      },
      {
        onError: (e) =>
          setServerError(errorMessage(e, "The invoice couldn't be created.")),
      },
    );
  });

  const saving = create.isPending || created;

  return (
    <PageShell width="default">
      <PageHeader
        eyebrow={
          <Link href="/billing/invoices" className="hover:text-foreground">
            Invoices
          </Link>
        }
        title="New invoice"
        description="Bill a customer for goods or services that aren't tied to an order."
      />
      <Notice
        tone="info"
        icon={Info}
        title="This creates a draft"
        className="mb-5"
      >
        Nothing is sent and no balance is owed until you issue it. Review the
        draft, then choose <span className="font-medium">Issue invoice</span>{" "}
        when it&apos;s ready.
      </Notice>

      <form onSubmit={onSubmit} noValidate>
        {serverError && (
          <div className="mb-4">
            <InlineError message={serverError} />
          </div>
        )}
        <div className="rounded-xl border border-border bg-surface p-4 shadow-sm sm:p-6">
          <FormSection
            title="Bill to"
            description="Invoices are issued to an existing, active customer."
          >
            <FormField
              label="Customer"
              htmlFor="invoice-customer"
              required
              error={errors.customer?.message}
            >
              <Controller
                control={control}
                name="customer"
                render={({ field, fieldState }) => (
                  <CustomerPicker
                    id="invoice-customer"
                    value={field.value ?? null}
                    onChange={(c) => field.onChange(c)}
                    invalid={Boolean(fieldState.error)}
                    disabled={saving}
                  />
                )}
              />
            </FormField>
          </FormSection>

          <FormSection
            title="Line items"
            description="Quantities allow up to 3 decimals; amounts up to 2."
          >
            <div className="hidden grid-cols-[minmax(0,1fr)_80px_112px_112px_112px_32px] gap-2 px-0.5 text-xs font-medium text-muted-foreground sm:grid">
              <span>Description</span>
              <span>Qty</span>
              <span>Unit price</span>
              <span>Discount</span>
              <span className="text-right">Amount</span>
              <span className="sr-only">Remove</span>
            </div>
            <ul className="space-y-3 sm:space-y-2">
              {lines.fields.map((field, index) => {
                const lineErrors = errors.lines?.[index];
                return (
                  <li
                    key={field.id}
                    className="grid grid-cols-3 gap-2 rounded-lg border border-border p-3 sm:grid-cols-[minmax(0,1fr)_80px_112px_112px_112px_32px] sm:items-start sm:border-0 sm:p-0"
                  >
                    <div className="col-span-3 sm:col-span-1">
                      <label
                        htmlFor={`line-${index}-description`}
                        className="mb-1 block text-xs font-medium sm:sr-only"
                      >
                        Description
                      </label>
                      <Input
                        id={`line-${index}-description`}
                        placeholder="e.g. Consulting — March"
                        aria-invalid={
                          Boolean(lineErrors?.description) || undefined
                        }
                        disabled={saving}
                        {...register(`lines.${index}.description`)}
                      />
                      <LineError message={lineErrors?.description?.message} />
                    </div>
                    <div>
                      <label
                        htmlFor={`line-${index}-quantity`}
                        className="mb-1 block text-xs font-medium sm:sr-only"
                      >
                        Quantity
                      </label>
                      <Input
                        id={`line-${index}-quantity`}
                        inputMode="decimal"
                        className="tabular"
                        aria-invalid={
                          Boolean(lineErrors?.quantity) || undefined
                        }
                        disabled={saving}
                        {...register(`lines.${index}.quantity`)}
                      />
                      <LineError message={lineErrors?.quantity?.message} />
                    </div>
                    <div>
                      <label
                        htmlFor={`line-${index}-price`}
                        className="mb-1 block text-xs font-medium sm:sr-only"
                      >
                        Unit price
                      </label>
                      <Input
                        id={`line-${index}-price`}
                        inputMode="decimal"
                        placeholder="0.00"
                        className="tabular"
                        aria-invalid={
                          Boolean(lineErrors?.unit_price) || undefined
                        }
                        disabled={saving}
                        {...register(`lines.${index}.unit_price`)}
                      />
                      <LineError message={lineErrors?.unit_price?.message} />
                    </div>
                    <div>
                      <label
                        htmlFor={`line-${index}-discount`}
                        className="mb-1 block text-xs font-medium sm:sr-only"
                      >
                        Discount
                      </label>
                      <Input
                        id={`line-${index}-discount`}
                        inputMode="decimal"
                        className="tabular"
                        aria-invalid={
                          Boolean(lineErrors?.discount) || undefined
                        }
                        disabled={saving}
                        {...register(`lines.${index}.discount`)}
                      />
                      <LineError message={lineErrors?.discount?.message} />
                    </div>
                    <LineAmount
                      control={control}
                      index={index}
                      currency={settings.data?.default_currency}
                    />
                    <div className="flex items-end justify-end sm:h-9 sm:items-center">
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon-sm"
                        onClick={() => lines.remove(index)}
                        disabled={saving || lines.fields.length === 1}
                        aria-label={`Remove line ${index + 1}`}
                      >
                        <Trash2 />
                      </Button>
                    </div>
                  </li>
                );
              })}
            </ul>
            {errors.lines?.root?.message && (
              <LineError message={errors.lines.root.message} />
            )}
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={() => lines.append({ ...EMPTY_LINE })}
              disabled={saving || lines.fields.length >= 100}
            >
              <Plus /> Add line
            </Button>

            <TotalsPreview
              control={control}
              loading={settings.isPending}
              currency={settings.data?.default_currency}
              taxRate={settings.data?.tax_rate}
            />
          </FormSection>

          <FormSection
            title="Terms"
            description="Optional details printed on the invoice."
          >
            <FormField
              label="Due date"
              htmlFor="invoice-due"
              optional
              error={errors.due_date?.message}
              help={
                settings.data
                  ? `Leave empty to use your standard terms (${settings.data.invoice_due_days} days from the issue date).`
                  : "Leave empty to use your standard payment terms from the issue date."
              }
            >
              <Input
                id="invoice-due"
                type="date"
                min={todayISO()}
                className="sm:w-52"
                aria-invalid={Boolean(errors.due_date) || undefined}
                disabled={saving}
                {...register("due_date")}
              />
            </FormField>
            <FormField
              label="Notes"
              htmlFor="invoice-notes"
              optional
              error={errors.notes?.message}
            >
              <Textarea
                id="invoice-notes"
                rows={3}
                placeholder="Payment instructions, PO number or a thank-you note"
                disabled={saving}
                {...register("notes")}
              />
            </FormField>
          </FormSection>
        </div>

        <FormActions
          dirty={isDirty}
          saving={saving}
          onCancel={() => router.push("/billing/invoices")}
          submitLabel="Create draft"
        />
      </form>
    </PageShell>
  );
}

function LineError({ message }: { message?: string }) {
  if (!message) return null;
  return (
    <p role="alert" className="mt-1 text-xs font-medium text-danger">
      {message}
    </p>
  );
}

function lineNetCents(
  line:
    { quantity?: string; unit_price?: string; discount?: string } | undefined,
) {
  if (!line) return BigInt(0);
  const quantity = (line.quantity ?? "").trim();
  const price = (line.unit_price ?? "").trim();
  const discount = (line.discount ?? "").trim();
  if (!QUANTITY_PATTERN.test(quantity) || !MONEY_PATTERN.test(price))
    return BigInt(0);
  const gross = lineGrossCents(price, quantity);
  const off = MONEY_PATTERN.test(discount) ? scaled(discount, 2) : BigInt(0);
  return gross - off;
}

function LineAmount({
  control,
  index,
  currency,
}: {
  control: Control<FormValues>;
  index: number;
  currency?: string;
}) {
  const line = useWatch({ control, name: `lines.${index}` });
  const net = lineNetCents(line);
  return (
    <div className="flex flex-col justify-end sm:h-9 sm:justify-center">
      <span className="mb-1 block text-xs font-medium sm:hidden">Amount</span>
      <span
        className={cn(
          "tabular h-9 truncate text-right text-sm leading-9 font-medium sm:h-auto sm:leading-normal",
          net < BigInt(0) && "text-danger",
        )}
      >
        {formatMoney(centsToString(net), currency ?? "USD")}
      </span>
    </div>
  );
}

function TotalsPreview({
  control,
  loading,
  currency = "USD",
  taxRate,
}: {
  control: Control<FormValues>;
  loading: boolean;
  currency?: string;
  taxRate?: string;
}) {
  const lines = useWatch({ control, name: "lines" }) ?? [];
  let subtotal = BigInt(0);
  let discounts = BigInt(0);
  for (const line of lines) {
    const quantity = (line?.quantity ?? "").trim();
    const price = (line?.unit_price ?? "").trim();
    if (!QUANTITY_PATTERN.test(quantity) || !MONEY_PATTERN.test(price))
      continue;
    subtotal += lineGrossCents(price, quantity);
    const discount = (line?.discount ?? "").trim();
    if (MONEY_PATTERN.test(discount)) discounts += scaled(discount, 2);
  }
  const taxable = subtotal - discounts;
  const tax = taxRate ? taxCents(taxable, taxRate) : BigInt(0);
  const total = taxable + tax;
  const money = (cents: bigint) => formatMoney(centsToString(cents), currency);

  return (
    <div
      className="ml-auto w-full max-w-sm rounded-lg bg-surface-muted/70 p-3.5 text-[13px]"
      aria-live="polite"
    >
      {loading ? (
        <div className="space-y-2">
          <Skeleton className="h-4" />
          <Skeleton className="h-4" />
          <Skeleton className="h-5" />
        </div>
      ) : (
        <dl className="space-y-1.5">
          <div className="flex justify-between gap-4">
            <dt className="text-muted-foreground">Subtotal</dt>
            <dd className="tabular">{money(subtotal)}</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-muted-foreground">Discounts</dt>
            <dd className="tabular">
              {discounts > BigInt(0)
                ? `−${money(discounts)}`
                : money(BigInt(0))}
            </dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-muted-foreground">
              Tax{taxRate ? ` (${formatRate(taxRate)})` : ""}
            </dt>
            <dd className="tabular">
              {taxRate ? money(tax) : "Calculated on save"}
            </dd>
          </div>
          <div className="flex justify-between gap-4 border-t border-border pt-2 text-sm font-semibold">
            <dt>Total</dt>
            <dd className="tabular">{money(total)}</dd>
          </div>
        </dl>
      )}
      <p className="mt-2 text-xs text-muted-foreground">
        Preview only. Final totals are calculated by the server when the draft
        is saved.
      </p>
    </div>
  );
}
