"use client";

import Link from "next/link";
import { cn } from "@/lib/utils";
import { formatMoney, formatNumber, toCents } from "@/lib/format";
import { useSession } from "@/features/auth/session-provider";
import { lineTotal } from "./lib";
import { TotalsPanel } from "./totals-panel";

export type DocumentLine = {
  id: string;
  description: string;
  sku?: string | null;
  quantity: string | number;
  unit_price: string;
  discount: string;
  line_total?: string;
  custom?: boolean;
};

/**
 * A paper-like rendering of a quote or order: issuer and number, dates, bill-to, lines and
 * totals. Used for the builder's review step and on record pages.
 */
export function DocumentView({
  kind,
  number,
  status,
  dates,
  billTo,
  lines,
  totals,
  taxRate,
  currency,
  notes,
  preview = false,
  className,
}: {
  kind: "Quote" | "Order";
  number?: string | null;
  status?: React.ReactNode;
  dates: { label: string; value: React.ReactNode }[];
  billTo: {
    name: string;
    href?: string;
    lines?: (string | null | undefined)[];
  } | null;
  lines: DocumentLine[];
  totals?: {
    subtotal: string;
    discount_total: string;
    tax_total: string;
    total: string;
  };
  taxRate: string | null | undefined;
  currency: string;
  notes?: string;
  preview?: boolean;
  className?: string;
}) {
  const { session } = useSession();
  const issuer = session?.tenant?.name ?? "Your business";
  const anyDiscount = lines.some((line) => toCents(line.discount) > BigInt(0));

  return (
    <article
      aria-label={`${kind} ${number ?? "preview"}`}
      className={cn(
        "rounded-xl border border-border bg-surface shadow-sm",
        className,
      )}
    >
      <header className="flex flex-col gap-4 border-b border-border px-5 py-5 sm:flex-row sm:items-start sm:justify-between sm:px-7 sm:py-6">
        <div className="min-w-0">
          <p className="text-2xs font-semibold tracking-wide text-muted-foreground uppercase">
            {kind}
          </p>
          <p className="mt-1 font-mono text-lg font-semibold tracking-tight">
            {number ?? (
              <span className="font-sans text-muted-foreground">
                Number assigned on save
              </span>
            )}
          </p>
          {status && <div className="mt-2">{status}</div>}
        </div>
        <div className="sm:text-right">
          <p className="text-[15px] font-semibold">{issuer}</p>
          <dl className="mt-2 grid grid-cols-[auto_auto] justify-start gap-x-4 gap-y-1 text-[13px] sm:justify-end">
            {dates.map((d) => (
              <div key={d.label} className="contents">
                <dt className="text-muted-foreground">{d.label}</dt>
                <dd className="tabular font-medium sm:text-right">{d.value}</dd>
              </div>
            ))}
          </dl>
        </div>
      </header>

      <section className="border-b border-border px-5 py-4 sm:px-7">
        <p className="text-2xs font-semibold tracking-wide text-muted-foreground uppercase">
          Bill to
        </p>
        {billTo ? (
          <div className="mt-1 text-[13px]">
            {billTo.href ? (
              <Link
                href={billTo.href}
                className="text-sm font-semibold hover:underline"
              >
                {billTo.name}
              </Link>
            ) : (
              <p className="text-sm font-semibold">{billTo.name}</p>
            )}
            {billTo.lines?.filter(Boolean).map((line) => (
              <p key={line} className="text-muted-foreground">
                {line}
              </p>
            ))}
          </div>
        ) : (
          <p className="mt-1 text-[13px] text-muted-foreground">
            No customer selected
          </p>
        )}
      </section>

      <div className="scrollbar-thin overflow-x-auto">
        <table className="w-full min-w-[520px] border-collapse text-[13px]">
          <caption className="sr-only">{kind} lines</caption>
          <thead>
            <tr className="border-b border-border text-xs text-muted-foreground">
              <th
                scope="col"
                className="px-5 py-2 text-left font-medium sm:pl-7"
              >
                Description
              </th>
              <th scope="col" className="px-3 py-2 text-right font-medium">
                Qty
              </th>
              <th scope="col" className="px-3 py-2 text-right font-medium">
                Unit price
              </th>
              {anyDiscount && (
                <th scope="col" className="px-3 py-2 text-right font-medium">
                  Discount
                </th>
              )}
              <th
                scope="col"
                className="px-5 py-2 text-right font-medium sm:pr-7"
              >
                Amount
              </th>
            </tr>
          </thead>
          <tbody>
            {lines.length === 0 ? (
              <tr>
                <td
                  colSpan={anyDiscount ? 5 : 4}
                  className="px-7 py-8 text-center text-muted-foreground"
                >
                  No lines on this {kind.toLowerCase()}.
                </td>
              </tr>
            ) : (
              lines.map((line) => (
                <tr
                  key={line.id}
                  className="border-b border-border last:border-0"
                >
                  <td className="px-5 py-2.5 align-top sm:pl-7">
                    <p className="font-medium">
                      {line.description || "Untitled line"}
                    </p>
                    {line.sku ? (
                      <p className="font-mono text-xs text-muted-foreground">
                        {line.sku}
                      </p>
                    ) : line.custom ? (
                      <p className="text-xs text-muted-foreground">Service</p>
                    ) : null}
                  </td>
                  <td className="tabular px-3 py-2.5 text-right align-top">
                    {formatNumber(line.quantity)}
                  </td>
                  <td className="tabular px-3 py-2.5 text-right align-top">
                    {formatMoney(line.unit_price, currency)}
                  </td>
                  {anyDiscount && (
                    <td className="tabular px-3 py-2.5 text-right align-top text-muted-foreground">
                      {toCents(line.discount) > BigInt(0)
                        ? `−${formatMoney(line.discount, currency)}`
                        : "—"}
                    </td>
                  )}
                  <td className="tabular px-5 py-2.5 text-right align-top font-medium sm:pr-7">
                    {formatMoney(line.line_total ?? lineTotal(line), currency)}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <footer className="grid gap-5 border-t border-border px-5 py-5 sm:grid-cols-[1fr_minmax(240px,300px)] sm:px-7">
        <div className="min-w-0 text-[13px]">
          {notes ? (
            <>
              <p className="text-2xs font-semibold tracking-wide text-muted-foreground uppercase">
                Notes
              </p>
              <p className="mt-1 whitespace-pre-line text-foreground-secondary">
                {notes}
              </p>
            </>
          ) : null}
        </div>
        <TotalsPanel
          lines={totals ? undefined : lines}
          totals={totals}
          taxRate={taxRate}
          currency={currency}
          preview={preview}
        />
      </footer>
    </article>
  );
}
