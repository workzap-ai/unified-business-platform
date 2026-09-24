"use client";

import { useId } from "react";
import { Lock, PenLine, Receipt, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatMoney } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tooltip } from "@/components/ui/overlays";
import { EmptyState } from "@/components/app/states";
import { lineTotal, MONEY_PATTERN, newKey } from "./lib";
import { ProductSelector, StockHint, type PickedVariant } from "./product-selector";
import type { DraftLine, LinesMode } from "./schema";

type LineErrors = unknown;

function fieldMessage(errors: LineErrors, index: number, field: keyof DraftLine): string | undefined {
  const row = (errors as Record<number, Record<string, { message?: string } | undefined> | undefined> | undefined)?.[index];
  return row?.[field]?.message;
}

function arrayMessage(errors: LineErrors): string | undefined {
  const e = errors as { message?: string; root?: { message?: string } } | undefined;
  return e?.message ?? e?.root?.message;
}

export function lineFromPick({ product, variant }: PickedVariant): DraftLine {
  return {
    key: newKey(),
    variant_id: variant.id,
    sku: variant.sku,
    description: variant.name && variant.name !== product.name ? `${product.name} — ${variant.name}` : product.name,
    unit_price: variant.price,
    quantity: "1",
    discount: "0",
    track_inventory: variant.track_inventory,
  };
}

/**
 * Editable document lines. Catalog lines keep the catalog price (read-only); quotes can also
 * carry custom service lines with their own description and price.
 */
export function LinesEditor({
  mode,
  lines,
  onChange,
  currency,
  errors,
  disabled = false,
}: {
  mode: LinesMode;
  lines: DraftLine[];
  onChange: (lines: DraftLine[]) => void;
  currency: string;
  errors?: LineErrors;
  disabled?: boolean;
}) {
  const baseId = useId();
  const update = (key: string, patch: Partial<DraftLine>) =>
    onChange(lines.map((line) => (line.key === key ? { ...line, ...patch } : line)));
  const remove = (key: string) => onChange(lines.filter((line) => line.key !== key));
  const addPick = (pick: PickedVariant) => onChange([...lines, lineFromPick(pick)]);
  const addCustom = () =>
    onChange([
      ...lines,
      { key: newKey(), variant_id: null, sku: null, description: "", unit_price: "", quantity: "1", discount: "0", track_inventory: false },
    ]);
  const listError = arrayMessage(errors);
  const usedVariants = lines.flatMap((line) => (line.variant_id ? [line.variant_id] : []));

  const actions = (
    <div className="flex flex-wrap items-center gap-2">
      <ProductSelector onPick={addPick} showStock={mode === "order"} excludeVariantIds={usedVariants} />
      {mode === "quote" && (
        <Button type="button" variant="ghost" size="sm" onClick={addCustom} disabled={disabled}>
          <PenLine /> Add custom line
        </Button>
      )}
    </div>
  );

  if (lines.length === 0) {
    return (
      <div className={cn("rounded-xl border border-dashed", listError ? "border-danger/50" : "border-border-strong")}>
        <EmptyState
          compact
          icon={Receipt}
          title="No items yet"
          description={
            mode === "quote"
              ? "Add products from your catalog at their current price, or a custom line for services."
              : "Add products from your catalog. Prices come from the catalog and are re-verified on confirmation."
          }
          action={actions}
        />
        {listError && (
          <p role="alert" className="pb-4 text-center text-xs font-medium text-danger">
            {listError}
          </p>
        )}
      </div>
    );
  }

  return (
    <div>
      <div className="overflow-hidden rounded-xl border border-border bg-surface">
        <div
          aria-hidden="true"
          className="hidden grid-cols-[minmax(0,1fr)_84px_112px_112px_112px_36px] gap-3 border-b border-border bg-surface-muted/70 px-3 py-2 text-xs font-medium text-muted-foreground md:grid"
        >
          <span>Item</span>
          <span className="text-right">Qty</span>
          <span className="text-right">Unit price</span>
          <span className="text-right">Discount</span>
          <span className="text-right">Line total</span>
          <span />
        </div>
        <ul className="divide-y divide-border">
          {lines.map((line, index) => {
            const id = `${baseId}-${index}`;
            const custom = line.variant_id === null;
            const priceValid = MONEY_PATTERN.test(line.unit_price.trim());
            const qtyNumber = Number(line.quantity);
            const descError = fieldMessage(errors, index, "description");
            const qtyError = fieldMessage(errors, index, "quantity");
            const priceError = fieldMessage(errors, index, "unit_price");
            const discountError = fieldMessage(errors, index, "discount");
            return (
              <li
                key={line.key}
                className="grid grid-cols-2 gap-x-3 gap-y-2 px-3 py-3 md:grid-cols-[minmax(0,1fr)_84px_112px_112px_112px_36px] md:items-start"
              >
                <div className="col-span-2 min-w-0 md:col-span-1">
                  {custom ? (
                    <>
                      <label htmlFor={`${id}-desc`} className="text-2xs font-medium text-muted-foreground md:sr-only">
                        Service description
                      </label>
                      <Input
                        id={`${id}-desc`}
                        value={line.description}
                        onChange={(e) => update(line.key, { description: e.target.value })}
                        placeholder="e.g. Installation and setup"
                        aria-invalid={Boolean(descError) || undefined}
                        maxLength={300}
                        disabled={disabled}
                        className="h-8 text-[13px]"
                      />
                      <p className="mt-1 text-2xs text-muted-foreground">Custom line</p>
                    </>
                  ) : (
                    <div className="pt-1">
                      <p className="truncate text-[13px] font-medium">{line.description}</p>
                      <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5">
                        {line.sku && <span className="font-mono text-xs text-muted-foreground">{line.sku}</span>}
                        {mode === "order" && (
                          <StockHint
                            sku={line.sku}
                            variantId={line.variant_id}
                            trackInventory={line.track_inventory}
                            quantity={Number.isFinite(qtyNumber) ? qtyNumber : undefined}
                          />
                        )}
                      </div>
                    </div>
                  )}
                  {descError && (
                    <p role="alert" className="mt-1 text-xs font-medium text-danger">
                      {descError}
                    </p>
                  )}
                </div>

                <div className="min-w-0">
                  <label htmlFor={`${id}-qty`} className="text-2xs font-medium text-muted-foreground md:sr-only">
                    Quantity
                  </label>
                  <Input
                    id={`${id}-qty`}
                    inputMode={mode === "order" ? "numeric" : "decimal"}
                    value={line.quantity}
                    onChange={(e) => update(line.key, { quantity: e.target.value })}
                    aria-invalid={Boolean(qtyError) || undefined}
                    disabled={disabled}
                    className="tabular h-8 text-right text-[13px]"
                  />
                  {qtyError && (
                    <p role="alert" className="mt-1 text-xs font-medium text-danger">
                      {qtyError}
                    </p>
                  )}
                </div>

                <div className="min-w-0">
                  <label htmlFor={`${id}-price`} className="text-2xs font-medium text-muted-foreground md:sr-only">
                    Unit price
                  </label>
                  {custom ? (
                    <Input
                      id={`${id}-price`}
                      inputMode="decimal"
                      value={line.unit_price}
                      onChange={(e) => update(line.key, { unit_price: e.target.value })}
                      placeholder="0.00"
                      aria-invalid={Boolean(priceError) || undefined}
                      disabled={disabled}
                      className="tabular h-8 text-right text-[13px]"
                    />
                  ) : (
                    <Tooltip content="Catalog price — change it in the catalog">
                      <div
                        id={`${id}-price`}
                        tabIndex={0}
                        className="tabular flex h-8 items-center justify-end gap-1.5 rounded-md bg-surface-muted px-2.5 text-[13px]"
                      >
                        <Lock className="size-3 text-muted-foreground" aria-hidden="true" />
                        {formatMoney(line.unit_price, currency)}
                      </div>
                    </Tooltip>
                  )}
                  {priceError && (
                    <p role="alert" className="mt-1 text-xs font-medium text-danger">
                      {priceError}
                    </p>
                  )}
                </div>

                <div className="min-w-0">
                  <label htmlFor={`${id}-discount`} className="text-2xs font-medium text-muted-foreground md:sr-only">
                    Discount amount
                  </label>
                  <Input
                    id={`${id}-discount`}
                    inputMode="decimal"
                    value={line.discount}
                    onChange={(e) => update(line.key, { discount: e.target.value })}
                    onFocus={(e) => {
                      if (e.target.value === "0") e.target.select();
                    }}
                    aria-invalid={Boolean(discountError) || undefined}
                    disabled={disabled}
                    className="tabular h-8 text-right text-[13px]"
                  />
                  {discountError && (
                    <p role="alert" className="mt-1 text-xs font-medium text-danger">
                      {discountError}
                    </p>
                  )}
                </div>

                <div className="flex min-w-0 flex-col justify-center md:h-8 md:items-end">
                  <span className="text-2xs font-medium text-muted-foreground md:sr-only">Line total</span>
                  <span className="tabular text-[13px] font-semibold md:text-right">
                    {priceValid ? formatMoney(lineTotal(line), currency) : "—"}
                  </span>
                </div>

                <div className="flex items-end justify-end md:h-8 md:items-center">
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => remove(line.key)}
                    disabled={disabled}
                    aria-label={`Remove ${line.description || "line"}`}
                  >
                    <Trash2 />
                  </Button>
                </div>
              </li>
            );
          })}
        </ul>
      </div>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
        {actions}
        {listError && (
          <p role="alert" className="text-xs font-medium text-danger">
            {listError}
          </p>
        )}
      </div>
    </div>
  );
}
