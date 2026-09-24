"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Controller, useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { ArrowLeft, ArrowRight, Info, Mail, Phone, Building2, Stamp, UserPlus, Warehouse } from "lucide-react";
import { formatDate } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import { Avatar, Card, CardBody, CardHeader } from "@/components/ui/display";
import { FormField, Stepper, useUnsavedChangesWarning } from "@/components/app/forms";
import { InlineError, Notice } from "@/components/app/states";
import { StatusBadge } from "@/components/app/status-badge";
import { useScopedMutation } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import { errorMessage } from "@/services/api-client";
import type { Quote } from "@/features/business/types";
import { documentsService } from "./service";
import { CustomerSelector, type SelectedCustomer } from "./customer-selector";
import { LinesEditor } from "./lines-editor";
import { TotalsPanel } from "./totals-panel";
import { DocumentView } from "./document-view";
import { useBusinessSettings } from "./hooks";
import { approvalReasons, computeTotals, dateFromToday } from "./lib";
import { linesSchema, toOrderLineInputs, toQuoteLineInputs, type DraftLine } from "./schema";

const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

function builderSchema(kind: "quote" | "order") {
  return z.object({
    customer: z.custom<SelectedCustomer | null>().refine((v): boolean => v !== null && v !== undefined, "Choose a customer"),
    lines: linesSchema(kind),
    valid_until: z
      .string()
      .refine((v) => v === "" || DATE_PATTERN.test(v), "Choose a valid date")
      .refine((v) => v === "" || v >= dateFromToday(0), "The validity date can't be in the past"),
    notes: z.string().max(4000, "Keep notes under 4,000 characters"),
  });
}

type BuilderValues = z.infer<ReturnType<typeof builderSchema>>;

export type BuilderInitial = {
  /** Present when editing an existing draft. */
  documentId?: string;
  number?: string;
  source?: Quote["source"];
  currency?: string;
  customer: SelectedCustomer | null;
  lines: DraftLine[];
  valid_until?: string;
  notes: string;
};

const STEPS = [
  { key: "customer", label: "Customer" },
  { key: "items", label: "Items" },
  { key: "review", label: "Review" },
];

/**
 * Guided builder for quotes and orders: customer → items → review. Catalog prices are
 * locked; totals are previewed in integer cents and priced authoritatively by the server.
 */
export function DocumentBuilder({ kind, initial }: { kind: "quote" | "order"; initial: BuilderInitial }) {
  const router = useRouter();
  const { can } = useSession();
  const editing = Boolean(initial.documentId);
  const settings = useBusinessSettings();
  const [step, setStep] = useState(editing ? 1 : initial.customer ? 1 : 0);
  const [done, setDone] = useState(false);

  const form = useForm<BuilderValues>({
    resolver: zodResolver(builderSchema(kind)),
    defaultValues: {
      customer: initial.customer,
      lines: initial.lines,
      valid_until: initial.valid_until ?? "",
      notes: initial.notes,
    },
    mode: "onTouched",
  });
  const { control, register, handleSubmit, trigger, setValue, getValues, formState } = form;
  const values = useWatch({ control }) as BuilderValues;
  useUnsavedChangesWarning(formState.isDirty && !done);

  // Default validity from business settings once they load (new quotes only).
  const validityDays = settings.data?.quote_validity_days;
  useEffect(() => {
    if (kind === "quote" && !editing && validityDays !== undefined && !getValues("valid_until")) {
      setValue("valid_until", dateFromToday(validityDays), { shouldDirty: false });
    }
  }, [kind, editing, validityDays, getValues, setValue]);

  const currency = initial.currency ?? settings.data?.default_currency ?? "USD";
  const taxRate = settings.data?.tax_rate ?? null;
  const lines = values.lines ?? [];
  const totals = computeTotals(lines, taxRate);
  const reasons =
    kind === "quote" ? approvalReasons({ ...totals, source: initial.source ?? "manual" }, settings.data, currency) : [];

  const save = useScopedMutation(
    async (v: BuilderValues) => {
      const notes = v.notes.trim();
      if (kind === "quote") {
        const input = { valid_until: v.valid_until || null, notes, lines: toQuoteLineInputs(v.lines) };
        const result = initial.documentId
          ? await documentsService.updateQuote(initial.documentId, input)
          : await documentsService.createQuote({ ...input, customer_id: v.customer!.id });
        return { id: result.id, href: `/quotes/${result.id}`, number: result.number };
      }
      const result = await documentsService.createOrder({
        customer_id: v.customer!.id,
        notes,
        lines: toOrderLineInputs(v.lines),
      });
      return { id: result.id, href: `/orders/${result.id}`, number: result.number };
    },
    {
      invalidate: [[kind === "quote" ? "quotes" : "orders"], ["customers"]],
      success: (r) =>
        editing
          ? `${r.number} updated`
          : kind === "quote"
            ? `${r.number} saved as draft — submit it when ready`
            : `${r.number} saved as draft — confirm it when ready`,
      onSuccess: (r) => {
        setDone(true);
        router.push(r.href);
      },
    },
  );

  async function next() {
    const fields: (keyof BuilderValues)[][] = [["customer"], ["lines"], ["valid_until", "notes"]];
    const ok = await trigger(fields[step]);
    if (ok) setStep((s) => Math.min(STEPS.length - 1, s + 1));
  }

  const onSubmit = handleSubmit((v) => save.mutate(v));
  const cancelHref = initial.documentId
    ? `/${kind === "quote" ? "quotes" : "orders"}/${initial.documentId}`
    : kind === "quote"
      ? "/quotes"
      : "/orders";
  const noun = kind === "quote" ? "quote" : "order";

  return (
    <form
      noValidate
      onSubmit={(event) => {
        if (step < STEPS.length - 1) {
          event.preventDefault();
          void next();
          return;
        }
        void onSubmit(event);
      }}
    >
      <Stepper steps={STEPS} current={step} onStep={(i) => setStep(i)} />

      {step === 0 && (
        <Card>
          <CardHeader
            title="Who is this for?"
            description={editing ? "The customer can't be changed on an existing draft." : `Pick the customer this ${noun} is addressed to.`}
          />
          <CardBody className="space-y-4">
            <Controller
              control={control}
              name="customer"
              render={({ field, fieldState }) => (
                <FormField label="Customer" htmlFor="builder-customer" required error={fieldState.error}>
                  <CustomerSelector
                    id="builder-customer"
                    value={field.value ?? null}
                    onChange={(c) => field.onChange(c)}
                    invalid={Boolean(fieldState.error)}
                    disabled={editing}
                  />
                </FormField>
              )}
            />
            {values.customer ? (
              <CustomerSummary customer={values.customer} />
            ) : (
              can("customers.write") && (
                <p className="text-[13px] text-muted-foreground">
                  New customer?{" "}
                  <Link href="/customers/new" className="inline-flex items-center gap-1 font-medium text-primary hover:underline">
                    <UserPlus className="size-3.5" aria-hidden="true" /> Add them first
                  </Link>
                </p>
              )
            )}
          </CardBody>
        </Card>
      )}

      {step === 1 && (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
          <Card>
            <CardHeader
              title="Items"
              description={
                kind === "quote"
                  ? "Catalog items use their current catalog price. Use a custom line for services."
                  : "Catalog items only. Quantities are whole units; stock is deducted on confirmation."
              }
            />
            <CardBody>
              <Controller
                control={control}
                name="lines"
                render={({ field, fieldState }) => (
                  <LinesEditor
                    mode={kind}
                    lines={field.value}
                    onChange={(next) => {
                      field.onChange(next);
                      if (formState.isSubmitted || fieldState.error) void trigger("lines");
                    }}
                    currency={currency}
                    errors={formState.errors.lines}
                  />
                )}
              />
            </CardBody>
          </Card>
          <Card className="h-fit lg:sticky lg:top-4">
            <CardHeader title="Summary" description={`${lines.length} ${lines.length === 1 ? "line" : "lines"}`} />
            <CardBody>
              <TotalsPanel lines={lines} taxRate={taxRate} currency={currency} loading={settings.isPending} preview />
              {kind === "quote" && reasons.length > 0 && (
                <p className="mt-3 flex items-start gap-1.5 text-xs text-warning">
                  <Stamp className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" /> Will need approval before sending
                </p>
              )}
            </CardBody>
          </Card>
        </div>
      )}

      {step === 2 && (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_300px]">
          <DocumentView
            kind={kind === "quote" ? "Quote" : "Order"}
            number={initial.number ?? null}
            status={<StatusBadge status="draft" />}
            dates={[
              { label: "Date", value: formatDate(new Date()) },
              ...(kind === "quote" ? [{ label: "Valid until", value: values.valid_until ? formatDate(values.valid_until) : "Default" }] : []),
            ]}
            billTo={
              values.customer
                ? {
                    name: values.customer.name,
                    lines: [values.customer.company, values.customer.email, values.customer.phone],
                  }
                : null
            }
            lines={lines.map((l) => ({ ...l, id: l.key, custom: l.variant_id === null }))}
            taxRate={taxRate}
            currency={currency}
            notes={values.notes?.trim()}
            preview
          />
          <div className="space-y-4">
            <Card>
              <CardHeader title="Details" />
              <CardBody className="space-y-4">
                {kind === "quote" && (
                  <FormField
                    label="Valid until"
                    htmlFor="builder-valid-until"
                    error={formState.errors.valid_until}
                    help={
                      settings.data
                        ? `Defaults to ${settings.data.quote_validity_days} days from today.`
                        : "Leave empty to use the workspace default."
                    }
                  >
                    <Input
                      id="builder-valid-until"
                      type="date"
                      min={dateFromToday(0)}
                      aria-invalid={Boolean(formState.errors.valid_until) || undefined}
                      {...register("valid_until")}
                    />
                  </FormField>
                )}
                <FormField label="Notes" htmlFor="builder-notes" optional error={formState.errors.notes} help="Shown on the document.">
                  <Textarea
                    id="builder-notes"
                    rows={4}
                    placeholder={kind === "quote" ? "Delivery terms, payment terms, scope…" : "Delivery instructions, references…"}
                    aria-invalid={Boolean(formState.errors.notes) || undefined}
                    {...register("notes")}
                  />
                </FormField>
              </CardBody>
            </Card>
            {kind === "quote" && reasons.length > 0 && (
              <Notice tone="warning" icon={Stamp} title="Approval will be needed">
                <ul className="list-disc space-y-0.5 pl-4">
                  {reasons.map((r) => (
                    <li key={r}>{r}</li>
                  ))}
                </ul>
                <p className="mt-1">After you submit, a reviewer approves it before it can be sent.</p>
              </Notice>
            )}
            {kind === "order" && (
              <Notice tone="info" icon={Warehouse} title="Nothing is deducted yet">
                The order is saved as a draft. Stock is checked and deducted, and prices re-verified, when you confirm it.
              </Notice>
            )}
            <Notice tone="neutral" icon={Info}>
              {editing
                ? "Changes are saved to this draft. It stays a draft until you submit it."
                : kind === "quote"
                  ? "Saved as a draft. Submit it when ready — nothing is sent to the customer yet."
                  : "Saved as a draft. You can review it and confirm from the order page."}
            </Notice>
          </div>
        </div>
      )}

      {save.isError && (
        <div className="mt-4">
          <InlineError message={errorMessage(save.error, `The ${noun} couldn't be saved. Please try again.`)} />
        </div>
      )}

      <div className="sticky bottom-0 z-10 -mx-4 mt-6 flex flex-wrap items-center gap-2 border-t border-border bg-surface/95 px-4 py-3 backdrop-blur sm:-mx-6 sm:px-6 lg:-mx-8 lg:px-8">
        <Button type="button" variant="ghost" asChild>
          <Link href={cancelHref}>Cancel</Link>
        </Button>
        <div className="ml-auto flex items-center gap-2">
          {step > 0 && (
            <Button type="button" variant="secondary" onClick={() => setStep((s) => s - 1)} disabled={save.isPending}>
              <ArrowLeft /> Back
            </Button>
          )}
          {step < STEPS.length - 1 ? (
            <Button type="submit">
              Continue <ArrowRight />
            </Button>
          ) : (
            <Button type="submit" loading={save.isPending} disabled={save.isPending}>
              {editing ? "Save changes" : kind === "quote" ? "Create draft quote" : "Create draft order"}
            </Button>
          )}
        </div>
      </div>
    </form>
  );
}

function CustomerSummary({ customer }: { customer: SelectedCustomer }) {
  const details = [
    { icon: Building2, value: customer.company },
    { icon: Mail, value: customer.email },
    { icon: Phone, value: customer.phone },
  ].filter((d) => d.value);
  return (
    <div className="flex items-start gap-3 rounded-lg border border-border bg-surface-muted/50 p-3">
      <Avatar name={customer.name} size="lg" />
      <div className="min-w-0 text-[13px]">
        <p className="font-semibold">{customer.name}</p>
        {details.length ? (
          <ul className="mt-1 space-y-0.5 text-muted-foreground">
            {details.map((d) => (
              <li key={d.value} className="flex items-center gap-1.5 truncate">
                <d.icon className="size-3.5 shrink-0" aria-hidden="true" /> {d.value}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-0.5 text-muted-foreground">No contact details on file.</p>
        )}
      </div>
    </div>
  );
}
