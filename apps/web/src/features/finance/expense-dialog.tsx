"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toCents } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input, NativeSelect } from "@/components/ui/input";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/overlays";
import { FormField } from "@/components/app/forms";
import { InlineError } from "@/components/app/states";
import { useScopedMutation } from "@/hooks/use-scoped";
import { errorMessage } from "@/services/api-client";
import { EXPENSE_CATEGORIES } from "@/features/business/types";
import { MONEY_PATTERN, todayISO } from "@/features/billing/utils";
import { financeService } from "./service";
import { CATEGORY_OPTIONS } from "./utils";

const schema = z.object({
  category: z.enum(EXPENSE_CATEGORIES),
  description: z
    .string()
    .trim()
    .min(1, "Describe what the money was spent on")
    .max(500, "Keep it under 500 characters"),
  vendor: z.string().trim().max(200, "Keep it under 200 characters"),
  amount: z
    .string()
    .trim()
    .regex(MONEY_PATTERN, "Use an amount like 49.99")
    .refine(
      (v): boolean => toCents(v) > BigInt(0),
      "Enter an amount greater than zero",
    ),
  incurred_on: z
    .string()
    .min(1, "Choose the date of the expense")
    .refine(
      (v): boolean => v <= todayISO(),
      "Expenses can't be dated in the future",
    ),
});
type Values = z.infer<typeof schema>;

export function ExpenseDialog({
  open,
  onOpenChange,
  currency,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  currency?: string;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="md">
        {open && (
          <ExpenseForm onDone={() => onOpenChange(false)} currency={currency} />
        )}
      </DialogContent>
    </Dialog>
  );
}

function ExpenseForm({
  onDone,
  currency,
}: {
  onDone: () => void;
  currency?: string;
}) {
  const [serverError, setServerError] = useState<string | null>(null);
  const { register, handleSubmit, formState } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      category: "other",
      description: "",
      vendor: "",
      amount: "",
      incurred_on: todayISO(),
    },
  });
  const { errors } = formState;
  const create = useScopedMutation(financeService.createExpense, {
    invalidate: [["expenses"], ["finance"]],
    success: (e) => `Expense ${e.number} recorded`,
    onSuccess: onDone,
  });
  const saving = create.isPending;

  const onSubmit = handleSubmit((values) => {
    setServerError(null);
    create.mutate(
      {
        category: values.category,
        description: values.description.trim(),
        vendor: values.vendor.trim(),
        amount: values.amount.trim(),
        incurred_on: values.incurred_on,
      },
      {
        onError: (e) =>
          setServerError(errorMessage(e, "The expense couldn't be recorded.")),
      },
    );
  });

  return (
    <form onSubmit={onSubmit} noValidate className="flex min-h-0 flex-col">
      <DialogHeader
        title="Record expense"
        description="Money your business spent. It counts toward cash out on the date you choose."
      />
      <DialogBody className="space-y-4">
        {serverError && <InlineError message={serverError} />}
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField
            label="Category"
            htmlFor="expense-category"
            required
            error={errors.category?.message}
          >
            <NativeSelect
              id="expense-category"
              disabled={saving}
              {...register("category")}
            >
              {CATEGORY_OPTIONS.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.label}
                </option>
              ))}
            </NativeSelect>
          </FormField>
          <FormField
            label="Date"
            htmlFor="expense-date"
            required
            error={errors.incurred_on?.message}
          >
            <Input
              id="expense-date"
              type="date"
              max={todayISO()}
              aria-invalid={Boolean(errors.incurred_on) || undefined}
              disabled={saving}
              {...register("incurred_on")}
            />
          </FormField>
        </div>
        <FormField
          label="Description"
          htmlFor="expense-description"
          required
          error={errors.description?.message}
        >
          <Input
            id="expense-description"
            placeholder="e.g. September office rent"
            autoFocus
            aria-invalid={Boolean(errors.description) || undefined}
            disabled={saving}
            {...register("description")}
          />
        </FormField>
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField
            label="Vendor"
            htmlFor="expense-vendor"
            optional
            error={errors.vendor?.message}
          >
            <Input
              id="expense-vendor"
              placeholder="Who was paid"
              disabled={saving}
              {...register("vendor")}
            />
          </FormField>
          <FormField
            label={currency ? `Amount (${currency})` : "Amount"}
            htmlFor="expense-amount"
            required
            error={errors.amount?.message}
          >
            <Input
              id="expense-amount"
              inputMode="decimal"
              placeholder="0.00"
              className="tabular"
              aria-invalid={Boolean(errors.amount) || undefined}
              disabled={saving}
              {...register("amount")}
            />
          </FormField>
        </div>
      </DialogBody>
      <DialogFooter>
        <Button
          type="button"
          variant="secondary"
          onClick={onDone}
          disabled={saving}
        >
          Cancel
        </Button>
        <Button type="submit" loading={saving}>
          Record expense
        </Button>
      </DialogFooter>
    </form>
  );
}
