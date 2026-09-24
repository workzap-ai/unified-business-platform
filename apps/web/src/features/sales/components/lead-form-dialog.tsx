"use client";

import { useEffect } from "react";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader } from "@/components/ui/overlays";
import { FormField } from "@/components/app/forms";
import { useScopedMutation } from "@/hooks/use-scoped";
import { ApiError } from "@/services/api-client";
import type { Lead } from "@/features/business/types";
import { salesService, type LeadInput } from "../service";
import { EDITABLE_SOURCES, LEAD_SOURCE_LABELS } from "../lib";
import { CustomerCombobox } from "./customer-combobox";

const leadFormSchema = z.object({
  title: z.string().trim().min(1, "Give the lead a short title").max(200, "Keep the title under 200 characters"),
  customer: z.object({ id: z.string(), name: z.string() }).nullable(),
  estimated_value: z
    .string()
    .trim()
    .refine((v) => !v || /^\d{1,12}(\.\d{1,2})?$/.test(v), "Enter an amount like 1500 or 1500.50"),
  source: z.enum(["manual", "website", "referral", "pi"]),
  notes: z.string().max(5000, "Keep notes under 5,000 characters"),
});
type LeadFormValues = z.infer<typeof leadFormSchema>;

function toForm(lead?: Lead, customer?: { id: string; name: string } | null): LeadFormValues {
  if (!lead) return { title: "", customer: customer ?? null, estimated_value: "", source: "manual", notes: "" };
  return {
    title: lead.title,
    customer: lead.customer_id ? { id: lead.customer_id, name: lead.customer_name ?? "Customer" } : null,
    estimated_value: lead.estimated_value ?? "",
    source: lead.source,
    notes: lead.notes,
  };
}

export function LeadFormDialog({
  open,
  onOpenChange,
  lead,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Present when editing. */
  lead?: Lead;
  onCreated?: (lead: Lead) => void;
}) {
  const editing = Boolean(lead);
  const form = useForm<LeadFormValues>({ resolver: zodResolver(leadFormSchema), defaultValues: toForm(lead) });
  const errors = form.formState.errors;

  useEffect(() => {
    if (open) form.reset(toForm(lead));
    // Reset only when the dialog opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const save = useScopedMutation(
    (values: LeadFormValues) => {
      const input: LeadInput = {
        title: values.title.trim(),
        customer_id: values.customer?.id ?? null,
        estimated_value: values.estimated_value.trim() || null,
        notes: values.notes,
        ...(values.source !== "pi" && { source: values.source }),
      };
      return lead ? salesService.update(lead.id, input) : salesService.create(input);
    },
    {
      invalidate: [["leads"], ["pipeline"]],
      success: editing ? "Lead updated" : (l) => `Lead “${l.title}” created`,
      error: "The lead couldn't be saved. Please try again.",
    },
  );

  const onSubmit = form.handleSubmit(async (values) => {
    try {
      const result = await save.mutateAsync(values);
      onOpenChange(false);
      if (!editing) onCreated?.(result);
    } catch (error) {
      if (error instanceof ApiError) {
        for (const [field, message] of Object.entries(error.fields)) {
          const key = field === "customer_id" ? "customer" : field;
          if (key in leadFormSchema.shape) form.setError(key as keyof LeadFormValues, { type: "server", message });
        }
      }
    }
  });

  const saving = save.isPending;
  const currency = lead?.currency;

  return (
    <Dialog open={open} onOpenChange={(next) => !saving && onOpenChange(next)}>
      <DialogContent size="md">
        <form onSubmit={onSubmit} noValidate className="flex min-h-0 flex-1 flex-col">
          <DialogHeader
            title={editing ? "Edit lead" : "New lead"}
            description={editing ? "Update the lead's details. Use the stage buttons to move it through the pipeline." : "Track a potential sale from first contact to won or lost."}
          />
          <DialogBody className="space-y-4">
            <FormField label="Title" htmlFor="lead-title" required error={errors.title}>
              <Input
                id="lead-title"
                placeholder="e.g. 40 office chairs for new branch"
                aria-invalid={!!errors.title || undefined}
                aria-describedby={errors.title ? "lead-title-error" : undefined}
                autoFocus
                {...form.register("title")}
              />
            </FormField>
            <FormField label="Customer" htmlFor="lead-customer" optional error={errors.customer?.message} help="Link an existing customer to create quotes from this lead.">
              <Controller
                control={form.control}
                name="customer"
                render={({ field }) => (
                  <CustomerCombobox
                    id="lead-customer"
                    value={field.value}
                    onChange={field.onChange}
                    invalid={!!errors.customer}
                    describedBy="lead-customer-help"
                  />
                )}
              />
            </FormField>
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField
                label={currency ? `Estimated value (${currency})` : "Estimated value"}
                htmlFor="lead-value"
                optional
                error={errors.estimated_value}
                help={currency ? undefined : "In your workspace currency."}
              >
                <Input
                  id="lead-value"
                  inputMode="decimal"
                  placeholder="0.00"
                  className="tabular"
                  aria-invalid={!!errors.estimated_value || undefined}
                  aria-describedby={errors.estimated_value ? "lead-value-error" : currency ? undefined : "lead-value-help"}
                  {...form.register("estimated_value")}
                />
              </FormField>
              <FormField label="Source" htmlFor="lead-source" error={errors.source} help={lead?.source === "pi" ? "Captured by PI; the source can't be changed." : undefined}>
                <NativeSelect id="lead-source" disabled={lead?.source === "pi"} {...form.register("source")}>
                  {lead?.source === "pi" && <option value="pi">{LEAD_SOURCE_LABELS.pi}</option>}
                  {EDITABLE_SOURCES.map((s) => (
                    <option key={s} value={s}>
                      {LEAD_SOURCE_LABELS[s]}
                    </option>
                  ))}
                </NativeSelect>
              </FormField>
            </div>
            <FormField label="Notes" htmlFor="lead-notes" optional error={errors.notes}>
              <Textarea id="lead-notes" rows={4} placeholder="Context, budget, timing, decision makers…" {...form.register("notes")} />
            </FormField>
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="secondary" onClick={() => onOpenChange(false)} disabled={saving}>
              Cancel
            </Button>
            <Button type="submit" loading={saving} disabled={saving || (editing && !form.formState.isDirty)}>
              {editing ? "Save changes" : "Create lead"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
