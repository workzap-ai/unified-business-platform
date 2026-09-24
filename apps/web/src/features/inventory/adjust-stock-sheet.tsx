"use client";

import { useEffect, useMemo } from "react";
import { Controller, useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { AlertTriangle, ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatNumber } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import { Label, RadioGroup, RadioGroupItem } from "@/components/ui/controls";
import { Skeleton } from "@/components/ui/display";
import { Dialog, DialogBody, DialogFooter, DialogHeader, SheetContent } from "@/components/ui/overlays";
import { FormField } from "@/components/app/forms";
import { InlineError, Notice } from "@/components/app/states";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { errorMessage } from "@/services/api-client";
import type { AdjustmentInput } from "@/features/business/types";
import { inventoryService } from "./service";
import { STOCK_CHANGED, useLocations } from "./hooks";

export type AdjustTarget = {
  variant_id: string;
  product_name: string;
  variant_name: string;
  sku: string;
  location_id?: string | null;
};

const KINDS: { value: AdjustmentInput["kind"]; label: string; description: string }[] = [
  { value: "receipt", label: "Receipt", description: "Stock received from a supplier or production." },
  { value: "return", label: "Return", description: "Items a customer sent back into sellable stock." },
  { value: "adjustment", label: "Adjustment", description: "Count correction, damage or loss. Can be negative." },
];

const schema = z
  .object({
    kind: z.enum(["receipt", "adjustment", "return"]),
    quantity: z.string().trim().min(1, "Enter a quantity").regex(/^[-+]?\d+$/, "Enter a whole number"),
    location_id: z.string().min(1, "Choose a location"),
    reason: z.string().trim().min(3, "Give a reason of at least 3 characters").max(240, "Keep the reason under 240 characters"),
  })
  .superRefine((value, ctx) => {
    if (!/^[-+]?\d+$/.test(value.quantity.trim())) return;
    const quantity = Number(value.quantity);
    if (quantity === 0) ctx.addIssue({ code: "custom", path: ["quantity"], message: "Quantity can't be zero" });
    else if (Math.abs(quantity) > 1_000_000)
      ctx.addIssue({ code: "custom", path: ["quantity"], message: "Quantity is too large" });
    else if (value.kind !== "adjustment" && quantity < 0)
      ctx.addIssue({
        code: "custom",
        path: ["quantity"],
        message: "Receipts and returns add stock. Enter a positive number, or use Adjustment to remove stock.",
      });
  });

type Values = z.infer<typeof schema>;

export function AdjustStockSheet({
  target,
  open,
  onOpenChange,
}: {
  target: AdjustTarget | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const locations = useLocations(open);
  const active = useMemo(() => locations.sorted?.filter((l) => l.status === "active") ?? [], [locations.sorted]);
  const levels = useScopedQuery(
    ["inventory", "levels", "variant", target?.variant_id ?? "", target?.sku ?? ""],
    () => inventoryService.levels({ search: target?.sku, pageSize: 100 }),
    { enabled: open && Boolean(target) },
  );
  const variantLevels = useMemo(
    () => levels.data?.items.filter((l) => l.variant_id === target?.variant_id) ?? [],
    [levels.data, target?.variant_id],
  );

  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { kind: "receipt", quantity: "", location_id: "", reason: "" },
  });
  const { register, handleSubmit, control, reset, formState, setValue, getValues } = form;

  useEffect(() => {
    if (open) reset({ kind: "receipt", quantity: "", location_id: target?.location_id ?? "", reason: "" });
  }, [open, target, reset]);

  // Default to the target's location, else the default location, once locations arrive.
  useEffect(() => {
    if (!open || getValues("location_id") || !active.length) return;
    setValue("location_id", target?.location_id ?? active[0]!.id);
  }, [open, active, target, getValues, setValue]);

  const kind = useWatch({ control, name: "kind" });
  const quantityText = useWatch({ control, name: "quantity" });
  const locationId = useWatch({ control, name: "location_id" });

  const mutation = useScopedMutation((input: AdjustmentInput) => inventoryService.adjust(input), {
    invalidate: STOCK_CHANGED,
    success: "Stock updated",
    error: "Couldn't record this stock change.",
    onSuccess: () => onOpenChange(false),
  });

  const current = variantLevels.find((l) => l.location_id === locationId);
  const onHand = current?.on_hand ?? 0;
  const reserved = current?.reserved ?? 0;
  const quantity = /^[-+]?\d+$/.test(quantityText.trim()) ? Number(quantityText) : null;
  const effective = quantity === null ? null : kind === "adjustment" ? quantity : Math.abs(quantity);
  const next = effective === null ? null : onHand + effective;
  const belowReserved = next !== null && next < reserved;
  const negative = next !== null && next < 0;

  const onSubmit = handleSubmit((values) => {
    if (!target) return;
    mutation.mutate({
      variant_id: target.variant_id,
      location_id: values.location_id,
      quantity: Number(values.quantity),
      kind: values.kind,
      reason: values.reason.trim(),
    });
  });

  return (
    <Dialog open={open} onOpenChange={(next) => !mutation.isPending && onOpenChange(next)}>
      <SheetContent width="md" aria-describedby={undefined}>
        <DialogHeader
          title="Adjust stock"
          description={
            target ? (
              <>
                {target.product_name}
                {target.variant_name && target.variant_name !== target.product_name ? ` · ${target.variant_name}` : ""}{" "}
                <span className="font-mono text-xs">({target.sku})</span>
              </>
            ) : undefined
          }
        />
        <form onSubmit={onSubmit} className="flex min-h-0 flex-1 flex-col" noValidate>
          <DialogBody className="space-y-5">
            <fieldset className="space-y-2">
              <legend className="mb-2 text-[13px] font-medium">Type of change</legend>
              <Controller
                control={control}
                name="kind"
                render={({ field }) => (
                  <RadioGroup value={field.value} onValueChange={field.onChange} aria-label="Type of change">
                    {KINDS.map((k) => (
                      <Label
                        key={k.value}
                        htmlFor={`adjust-kind-${k.value}`}
                        className={cn(
                          "flex cursor-pointer items-start gap-3 rounded-lg border px-3 py-2.5 transition-colors",
                          field.value === k.value ? "border-primary/50 bg-primary-soft/40" : "border-border hover:bg-surface-muted",
                        )}
                      >
                        <RadioGroupItem id={`adjust-kind-${k.value}`} value={k.value} className="mt-0.5" />
                        <span>
                          <span className="block text-[13px] font-medium">{k.label}</span>
                          <span className="block text-xs font-normal text-muted-foreground">{k.description}</span>
                        </span>
                      </Label>
                    ))}
                  </RadioGroup>
                )}
              />
            </fieldset>

            <div className="grid gap-4 sm:grid-cols-2">
              <FormField
                label="Quantity"
                htmlFor="adjust-quantity"
                required
                error={formState.errors.quantity}
                help={kind === "adjustment" ? "Use a minus sign to remove stock, e.g. -3." : "Units added to stock."}
              >
                <Input
                  id="adjust-quantity"
                  inputMode="numeric"
                  autoComplete="off"
                  placeholder={kind === "adjustment" ? "-3 or 5" : "10"}
                  className="tabular"
                  aria-invalid={Boolean(formState.errors.quantity)}
                  aria-describedby={formState.errors.quantity ? "adjust-quantity-error" : "adjust-quantity-help"}
                  {...register("quantity")}
                />
              </FormField>
              <FormField label="Location" htmlFor="adjust-location" required error={formState.errors.location_id}>
                {locations.isPending ? (
                  <Skeleton className="h-9" />
                ) : (
                  <NativeSelect
                    id="adjust-location"
                    aria-invalid={Boolean(formState.errors.location_id)}
                    {...register("location_id")}
                  >
                    {!active.length && <option value="">No active locations</option>}
                    {active.map((l) => (
                      <option key={l.id} value={l.id}>
                        {l.name}
                        {l.is_default ? " (default)" : ""}
                      </option>
                    ))}
                  </NativeSelect>
                )}
              </FormField>
            </div>

            {locations.isSuccess && !active.length && (
              <Notice tone="warning" icon={AlertTriangle} title="No stock location yet">
                Create a location on the Locations page before recording stock.
              </Notice>
            )}

            <FormField label="Reason" htmlFor="adjust-reason" required error={formState.errors.reason} help="Recorded in the stock ledger and audit log.">
              <Textarea
                id="adjust-reason"
                rows={3}
                placeholder="e.g. Supplier delivery PO-1042, damaged in transit"
                aria-invalid={Boolean(formState.errors.reason)}
                {...register("reason")}
              />
            </FormField>

            <section aria-label="Resulting balance" className="rounded-lg border border-border bg-surface-muted/60 p-3.5">
              <p className="text-xs font-medium text-muted-foreground">Resulting balance at this location</p>
              {levels.isPending ? (
                <Skeleton className="mt-2 h-7 w-40" />
              ) : (
                <div className="mt-1.5 flex items-center gap-3">
                  <div>
                    <p className="text-2xs text-muted-foreground">On hand now</p>
                    <p className="tabular text-lg font-semibold">{formatNumber(onHand)}</p>
                  </div>
                  <ArrowRight className="size-4 text-muted-foreground" aria-hidden="true" />
                  <div>
                    <p className="text-2xs text-muted-foreground">After this change</p>
                    <p
                      className={cn(
                        "tabular text-lg font-semibold",
                        (belowReserved || negative) && "text-danger",
                        next !== null && next > onHand && !belowReserved && "text-success",
                      )}
                      aria-live="polite"
                    >
                      {next === null ? "—" : formatNumber(next)}
                    </p>
                  </div>
                  <div className="ml-auto text-right">
                    <p className="text-2xs text-muted-foreground">Reserved</p>
                    <p className="tabular text-sm font-medium">{formatNumber(reserved)}</p>
                  </div>
                </div>
              )}
              {(belowReserved || negative) && (
                <p className="mt-2 text-xs font-medium text-danger">
                  {negative
                    ? "Stock can't go below zero."
                    : `This would leave less than the ${formatNumber(reserved)} units reserved for open orders.`}
                </p>
              )}
            </section>

            {mutation.isError && <InlineError message={errorMessage(mutation.error, "Couldn't record this stock change.")} />}
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="secondary" onClick={() => onOpenChange(false)} disabled={mutation.isPending}>
              Cancel
            </Button>
            <Button type="submit" loading={mutation.isPending} disabled={mutation.isPending || !active.length}>
              Record change
            </Button>
          </DialogFooter>
        </form>
      </SheetContent>
    </Dialog>
  );
}
