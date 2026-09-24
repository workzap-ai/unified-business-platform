"use client";

import { useEffect } from "react";
import { Controller, useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { History } from "lucide-react";
import { formatMoney } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label, Switch } from "@/components/ui/controls";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/overlays";
import { FormField } from "@/components/app/forms";
import { InlineError, Notice } from "@/components/app/states";
import { useScopedMutation } from "@/hooks/use-scoped";
import { ApiError, errorMessage } from "@/services/api-client";
import type { Variant, VariantInput } from "@/features/business/types";
import { catalogService } from "./service";
import { CATALOG_CHANGED } from "./hooks";
import { CURRENCY_PATTERN, PRICE_PATTERN, SKU_PATTERN } from "./lib";

const threshold = z
  .string()
  .trim()
  .regex(
    /^\d{0,7}$/,
    "Enter a whole number, or leave empty to use the workspace default",
  );

const addSchema = z.object({
  sku: z
    .string()
    .trim()
    .min(1, "Enter a SKU")
    .regex(
      SKU_PATTERN,
      "Letters, numbers, dots, dashes or underscores; start with a letter or number",
    ),
  name: z
    .string()
    .trim()
    .min(1, "Enter a name")
    .max(200, "Keep the name under 200 characters"),
  price: z.string().trim().regex(PRICE_PATTERN, "Enter a price like 12.50"),
  currency: z
    .string()
    .trim()
    .toUpperCase()
    .regex(CURRENCY_PATTERN, "Use a 3-letter currency code"),
  track_inventory: z.boolean(),
  low_stock_threshold: threshold,
});
type AddValues = z.infer<typeof addSchema>;

export function AddVariantDialog({
  productId,
  existingSkus,
  currency,
  open,
  onOpenChange,
}: {
  productId: string;
  existingSkus: string[];
  currency: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { register, handleSubmit, reset, control, setError, formState } =
    useForm<AddValues>({
      resolver: zodResolver(addSchema),
      defaultValues: {
        sku: "",
        name: "",
        price: "",
        currency,
        track_inventory: true,
        low_stock_threshold: "",
      },
    });
  useEffect(() => {
    if (open)
      reset({
        sku: "",
        name: "",
        price: "",
        currency,
        track_inventory: true,
        low_stock_threshold: "",
      });
  }, [open, currency, reset]);
  const tracked = useWatch({ control, name: "track_inventory" });

  const mutation = useScopedMutation(
    (input: VariantInput) => catalogService.addVariant(productId, input),
    {
      invalidate: CATALOG_CHANGED,
      success: (v) => `Variant ${v.sku} added`,
      error: "Couldn't add this variant.",
      onSuccess: () => onOpenChange(false),
    },
  );

  const submit = handleSubmit((v) => {
    if (
      existingSkus.some((s) => s.toLowerCase() === v.sku.trim().toLowerCase())
    ) {
      setError("sku", {
        message: "This product already has a variant with this SKU",
      });
      return;
    }
    mutation.mutate(
      {
        sku: v.sku.trim(),
        name: v.name.trim(),
        price: v.price.trim(),
        currency: v.currency,
        track_inventory: v.track_inventory,
        low_stock_threshold:
          v.track_inventory && v.low_stock_threshold
            ? Number(v.low_stock_threshold)
            : null,
      },
      {
        onError: (e) => {
          if (e instanceof ApiError && e.status === 409)
            setError("sku", { message: errorMessage(e) });
        },
      },
    );
  });

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => !mutation.isPending && onOpenChange(next)}
    >
      <DialogContent size="md">
        <DialogHeader
          title="Add variant"
          description="A size, color or package of this product with its own SKU and price."
        />
        <form
          onSubmit={submit}
          noValidate
          className="flex min-h-0 flex-1 flex-col"
        >
          <DialogBody className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField
                label="SKU"
                htmlFor="variant-sku"
                required
                error={formState.errors.sku}
              >
                <Input
                  id="variant-sku"
                  autoFocus
                  className="font-mono"
                  aria-invalid={Boolean(formState.errors.sku)}
                  {...register("sku")}
                />
              </FormField>
              <FormField
                label="Variant name"
                htmlFor="variant-name"
                required
                error={formState.errors.name}
              >
                <Input
                  id="variant-name"
                  placeholder="e.g. Large, Blue"
                  aria-invalid={Boolean(formState.errors.name)}
                  {...register("name")}
                />
              </FormField>
              <FormField
                label="Price"
                htmlFor="variant-price"
                required
                error={formState.errors.price}
              >
                <Input
                  id="variant-price"
                  inputMode="decimal"
                  className="tabular"
                  placeholder="0.00"
                  aria-invalid={Boolean(formState.errors.price)}
                  {...register("price")}
                />
              </FormField>
              <FormField
                label="Currency"
                htmlFor="variant-currency"
                required
                error={formState.errors.currency}
              >
                <Input
                  id="variant-currency"
                  maxLength={3}
                  className="uppercase"
                  aria-invalid={Boolean(formState.errors.currency)}
                  {...register("currency")}
                />
              </FormField>
            </div>
            <TrackingFields
              idPrefix="variant"
              tracked={tracked}
              error={formState.errors.low_stock_threshold?.message}
              trackSwitch={
                <Controller
                  control={control}
                  name="track_inventory"
                  render={({ field }) => (
                    <Switch
                      id="variant-track"
                      checked={field.value}
                      onCheckedChange={field.onChange}
                    />
                  )}
                />
              }
              thresholdInput={
                <Input
                  id="variant-threshold"
                  inputMode="numeric"
                  className="tabular w-32"
                  aria-invalid={Boolean(formState.errors.low_stock_threshold)}
                  {...register("low_stock_threshold")}
                />
              }
            />
            {mutation.isError &&
              !(
                mutation.error instanceof ApiError &&
                mutation.error.status === 409
              ) && <InlineError message={errorMessage(mutation.error)} />}
          </DialogBody>
          <DialogFooter>
            <Button
              type="button"
              variant="secondary"
              onClick={() => onOpenChange(false)}
              disabled={mutation.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" loading={mutation.isPending}>
              Add variant
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function TrackingFields({
  trackSwitch,
  thresholdInput,
  tracked,
  error,
  idPrefix,
}: {
  trackSwitch: React.ReactNode;
  thresholdInput: React.ReactNode;
  tracked: boolean;
  error?: string;
  idPrefix: string;
}) {
  return (
    <div className="rounded-lg border border-border p-3.5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <Label htmlFor={`${idPrefix}-track`}>Track inventory</Label>
          <p className="text-xs text-muted-foreground">
            Count stock for this SKU and warn when it runs low.
          </p>
        </div>
        {trackSwitch}
      </div>
      {tracked && (
        <FormField
          label="Low-stock threshold"
          htmlFor={`${idPrefix}-threshold`}
          optional
          className="mt-3"
          error={error}
          help="Leave empty to use the workspace default."
        >
          {thresholdInput}
        </FormField>
      )}
    </div>
  );
}

const editSchema = z.object({
  name: z
    .string()
    .trim()
    .min(1, "Enter a name")
    .max(200, "Keep the name under 200 characters"),
  price: z.string().trim().regex(PRICE_PATTERN, "Enter a price like 12.50"),
  track_inventory: z.boolean(),
  low_stock_threshold: threshold,
});
type EditValues = z.infer<typeof editSchema>;

/** Edit a variant. `priceOnly` narrows it to the price (pricing page). */
export function EditVariantDialog({
  variant,
  open,
  onOpenChange,
  priceOnly = false,
  productName,
}: {
  variant: Variant | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  priceOnly?: boolean;
  productName?: string;
}) {
  const values = (v: Variant | null): EditValues => ({
    name: v?.name ?? "",
    price: v?.price ?? "",
    track_inventory: v?.track_inventory ?? true,
    low_stock_threshold:
      v?.low_stock_threshold === null || v?.low_stock_threshold === undefined
        ? ""
        : String(v.low_stock_threshold),
  });
  const { register, handleSubmit, reset, control, formState } =
    useForm<EditValues>({
      resolver: zodResolver(editSchema),
      defaultValues: values(variant),
    });
  useEffect(() => {
    if (open) reset(values(variant));
  }, [open, variant, reset]);
  const tracked = useWatch({ control, name: "track_inventory" });
  const price = useWatch({ control, name: "price" });
  const priceChanged = Boolean(
    variant &&
    price.trim() &&
    PRICE_PATTERN.test(price.trim()) &&
    Number(price) !== Number(variant.price),
  );

  const mutation = useScopedMutation(
    (input: Parameters<typeof catalogService.updateVariant>[1]) =>
      catalogService.updateVariant(variant!.id, input),
    {
      invalidate: CATALOG_CHANGED,
      success: (v) => `${v.sku} updated`,
      error: "Couldn't save this variant.",
      onSuccess: () => onOpenChange(false),
    },
  );

  const submit = handleSubmit((v) => {
    if (!variant) return;
    const input: Parameters<typeof catalogService.updateVariant>[1] = {};
    if (
      v.price.trim() !== variant.price &&
      Number(v.price) !== Number(variant.price)
    )
      input.price = v.price.trim();
    if (!priceOnly) {
      if (v.name.trim() !== variant.name) input.name = v.name.trim();
      if (v.track_inventory !== variant.track_inventory)
        input.track_inventory = v.track_inventory;
      const nextThreshold = v.low_stock_threshold
        ? Number(v.low_stock_threshold)
        : null;
      if (nextThreshold !== variant.low_stock_threshold)
        input.low_stock_threshold = nextThreshold;
    }
    if (Object.keys(input).length === 0) {
      onOpenChange(false);
      return;
    }
    mutation.mutate(input);
  });

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => !mutation.isPending && onOpenChange(next)}
    >
      <DialogContent size={priceOnly ? "sm" : "md"}>
        <DialogHeader
          title={priceOnly ? "Change price" : "Edit variant"}
          description={
            variant ? (
              <>
                {productName ? `${productName} · ` : ""}
                <span className="font-mono">{variant.sku}</span>
              </>
            ) : undefined
          }
        />
        <form
          onSubmit={submit}
          noValidate
          className="flex min-h-0 flex-1 flex-col"
        >
          <DialogBody className="space-y-4">
            {!priceOnly && (
              <FormField
                label="Variant name"
                htmlFor="edit-variant-name"
                required
                error={formState.errors.name}
              >
                <Input
                  id="edit-variant-name"
                  aria-invalid={Boolean(formState.errors.name)}
                  {...register("name")}
                />
              </FormField>
            )}
            <FormField
              label={`Price (${variant?.currency ?? ""})`}
              htmlFor="edit-variant-price"
              required
              error={formState.errors.price}
              help={
                variant
                  ? `Current price ${formatMoney(variant.price, variant.currency)}`
                  : undefined
              }
            >
              <Input
                id="edit-variant-price"
                inputMode="decimal"
                autoFocus={priceOnly}
                className="tabular"
                aria-invalid={Boolean(formState.errors.price)}
                {...register("price")}
              />
            </FormField>
            {priceChanged && (
              <Notice tone="info" icon={History}>
                Price changes are audited and apply to new drafts only. Existing
                quotes, orders and invoices keep their price.
              </Notice>
            )}
            {!priceOnly && (
              <TrackingFields
                idPrefix="edit-variant"
                tracked={tracked}
                error={formState.errors.low_stock_threshold?.message}
                trackSwitch={
                  <Controller
                    control={control}
                    name="track_inventory"
                    render={({ field }) => (
                      <Switch
                        id="edit-variant-track"
                        checked={field.value}
                        onCheckedChange={field.onChange}
                      />
                    )}
                  />
                }
                thresholdInput={
                  <Input
                    id="edit-variant-threshold"
                    inputMode="numeric"
                    className="tabular w-32"
                    aria-invalid={Boolean(formState.errors.low_stock_threshold)}
                    {...register("low_stock_threshold")}
                  />
                }
              />
            )}
            {mutation.isError && (
              <InlineError message={errorMessage(mutation.error)} />
            )}
          </DialogBody>
          <DialogFooter>
            <Button
              type="button"
              variant="secondary"
              onClick={() => onOpenChange(false)}
              disabled={mutation.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" loading={mutation.isPending}>
              {priceOnly ? "Save price" : "Save changes"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
