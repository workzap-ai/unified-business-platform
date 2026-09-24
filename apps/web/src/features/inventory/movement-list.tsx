"use client";

import Link from "next/link";
import { formatDateTime, formatNumber, relativeTime } from "@/lib/format";
import { Badge, Skeleton } from "@/components/ui/display";
import type { Location, Movement } from "@/features/business/types";
import { MOVEMENT_KINDS, shortId, type VariantInfo } from "./lib";
import { Quantity } from "./stock-display";

/** Compact movement feed for overviews and record tabs. The full ledger lives on /inventory/movements. */
export function MovementList({
  movements,
  loading,
  variants,
  locations,
  showProduct = true,
  empty = "No stock movements yet.",
}: {
  movements: Movement[] | undefined;
  loading?: boolean;
  variants?: Map<string, VariantInfo>;
  locations?: Location[];
  showProduct?: boolean;
  empty?: string;
}) {
  if (loading || !movements) {
    return (
      <ul className="space-y-2.5" aria-busy="true">
        {Array.from({ length: 5 }, (_, i) => (
          <li key={i}>
            <Skeleton className="h-10" />
          </li>
        ))}
      </ul>
    );
  }
  if (!movements.length)
    return (
      <p className="py-6 text-center text-[13px] text-muted-foreground">
        {empty}
      </p>
    );
  return (
    <ul className="divide-y divide-border">
      {movements.map((m) => {
        const info = variants?.get(m.variant_id);
        const location = locations?.find((l) => l.id === m.location_id);
        const kind = MOVEMENT_KINDS[m.kind];
        return (
          <li key={m.id} className="flex items-center gap-3 py-2.5">
            <Quantity
              value={m.quantity}
              className="w-14 shrink-0 text-right text-[13px]"
            />
            <div className="min-w-0 flex-1">
              <p className="truncate text-[13px] font-medium">
                {showProduct ? (
                  info ? (
                    <Link
                      href={`/catalog/products/${info.product_id}`}
                      className="hover:underline"
                    >
                      {info.product_name}
                      <span className="font-normal text-muted-foreground">
                        {" "}
                        · {info.sku}
                      </span>
                    </Link>
                  ) : (
                    <span className="font-mono text-xs text-muted-foreground">
                      Variant {shortId(m.variant_id)}
                    </span>
                  )
                ) : (
                  m.reason || kind.label
                )}
              </p>
              <p className="truncate text-xs text-muted-foreground">
                {showProduct && m.reason ? `${m.reason} · ` : ""}
                {location ? `${location.name} · ` : ""}
                {m.actor_label} ·{" "}
                <time
                  dateTime={m.created_at}
                  title={formatDateTime(m.created_at)}
                >
                  {relativeTime(m.created_at)}
                </time>
              </p>
            </div>
            <div className="flex shrink-0 flex-col items-end gap-1">
              <Badge tone={kind.tone}>{kind.label}</Badge>
              <span className="tabular text-2xs text-muted-foreground">
                Balance {formatNumber(m.balance_after)}
              </span>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
