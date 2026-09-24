"use client";

import { useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from "recharts";
import { BarChart3, Table2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Card, CardHeader, Skeleton } from "@/components/ui/display";
import { Tooltip } from "@/components/ui/overlays";

/**
 * Chart primitives. Series colors come from the validated categorical order
 * (--chart-1..5) and are assigned by series position in a fixed order, never by rank.
 * Text uses text tokens; grids are hairline and recessive. Every chart card offers a
 * table view so values never depend on color or hover.
 */
export const SERIES = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)", "var(--chart-5)"];

export type Series = { key: string; label: string };
type Datum = Record<string, string | number | null>;

const axis = { fontSize: 11, fill: "var(--muted-foreground)" };

function ChartTooltip({
  active,
  payload,
  label,
  series,
  format,
}: {
  active?: boolean;
  payload?: { dataKey?: string | number; value?: number | string; color?: string }[];
  label?: string | number;
  series: Series[];
  format: (v: number) => string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="min-w-36 rounded-lg border border-border bg-surface px-3 py-2 text-xs shadow-md">
      <p className="mb-1.5 font-semibold text-foreground">{label}</p>
      <ul className="space-y-1">
        {payload.map((p) => {
          const s = series.find((x) => x.key === p.dataKey);
          return (
            <li key={String(p.dataKey)} className="flex items-center gap-2">
              <span className="h-0.5 w-3 rounded-full" style={{ background: p.color }} aria-hidden="true" />
              <span className="flex-1 text-muted-foreground">{s?.label ?? p.dataKey}</span>
              <span className="tabular font-semibold text-foreground">{format(Number(p.value ?? 0))}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function Legend({ series }: { series: Series[] }) {
  if (series.length < 2) return null;
  return (
    <ul className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
      {series.map((s, i) => (
        <li key={s.key} className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-[3px]" style={{ background: SERIES[i % SERIES.length] }} aria-hidden="true" />
          {s.label}
        </li>
      ))}
    </ul>
  );
}

function DataTableView({
  data,
  xKey,
  series,
  format,
  xLabel,
}: {
  data: Datum[];
  xKey: string;
  series: Series[];
  format: (v: number) => string;
  xLabel: string;
}) {
  return (
    <div className="scrollbar-thin max-h-72 overflow-auto rounded-md border border-border">
      <table className="w-full text-xs">
        <thead className="sticky top-0 bg-surface-muted">
          <tr>
            <th scope="col" className="px-3 py-1.5 text-left font-medium text-muted-foreground">{xLabel}</th>
            {series.map((s) => (
              <th key={s.key} scope="col" className="px-3 py-1.5 text-right font-medium text-muted-foreground">{s.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, i) => (
            <tr key={i} className="border-t border-border">
              <td className="px-3 py-1.5">{String(row[xKey])}</td>
              {series.map((s) => (
                <td key={s.key} className="tabular px-3 py-1.5 text-right">{format(Number(row[s.key] ?? 0))}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ChartCard({
  title,
  description,
  data,
  xKey,
  xLabel = "Period",
  series,
  kind = "area",
  format = (v) => v.toLocaleString(),
  height = 240,
  loading = false,
  actions,
  stacked = false,
  className,
  emptyMessage = "No data for this period yet.",
  headline,
}: {
  title: string;
  description?: string;
  data: Datum[] | undefined;
  xKey: string;
  xLabel?: string;
  series: Series[];
  kind?: "area" | "line" | "bar";
  format?: (v: number) => string;
  height?: number;
  loading?: boolean;
  actions?: React.ReactNode;
  stacked?: boolean;
  className?: string;
  emptyMessage?: string;
  headline?: React.ReactNode;
}) {
  const [view, setView] = useState<"chart" | "table">("chart");
  const empty =
    !loading && data !== undefined && (data.length === 0 || data.every((d) => series.every((s) => !Number(d[s.key]))));
  return (
    <Card className={cn("flex flex-col", className)}>
      <CardHeader
        title={title}
        description={description}
        actions={
          <>
            {actions}
            <Tooltip content={view === "chart" ? "Show as table" : "Show as chart"}>
              <button
                type="button"
                onClick={() => setView((v) => (v === "chart" ? "table" : "chart"))}
                className="rounded-md p-1.5 text-muted-foreground hover:bg-surface-muted hover:text-foreground"
                aria-label={view === "chart" ? `Show ${title} as table` : `Show ${title} as chart`}
                disabled={!data?.length}
              >
                {view === "chart" ? <Table2 className="size-4" /> : <BarChart3 className="size-4" />}
              </button>
            </Tooltip>
          </>
        }
      />
      <div className="flex flex-1 flex-col gap-3 px-4 pb-4">
        {headline}
        {loading || !data ? (
          <Skeleton style={{ height }} />
        ) : empty ? (
          <div className="flex items-center justify-center rounded-md border border-dashed border-border text-[13px] text-muted-foreground" style={{ height }}>
            {emptyMessage}
          </div>
        ) : view === "table" ? (
          <DataTableView data={data} xKey={xKey} series={series} format={format} xLabel={xLabel} />
        ) : (
          <>
            <Legend series={series} />
            <div style={{ height }} role="img" aria-label={`${title} chart. Use the table view for exact values.`}>
              <ResponsiveContainer width="100%" height="100%">
                {kind === "bar" ? (
                  <BarChart data={data} margin={{ top: 4, right: 4, left: -8, bottom: 0 }} barCategoryGap="28%">
                    <CartesianGrid vertical={false} stroke="var(--chart-grid)" strokeWidth={1} />
                    <XAxis dataKey={xKey} tick={axis} tickLine={false} axisLine={false} interval="preserveStartEnd" minTickGap={12} />
                    <YAxis tick={axis} tickLine={false} axisLine={false} width={72} tickFormatter={(v: number) => format(v)} />
                    <RechartsTooltip cursor={{ fill: "var(--surface-muted)" }} content={<ChartTooltip series={series} format={format} />} />
                    {series.map((s, i) => (
                      <Bar
                        key={s.key}
                        dataKey={s.key}
                        stackId={stacked ? "stack" : undefined}
                        fill={SERIES[i % SERIES.length]}
                        maxBarSize={24}
                        radius={stacked ? (i === series.length - 1 ? [4, 4, 0, 0] : [0, 0, 0, 0]) : [4, 4, 0, 0]}
                        stroke="var(--surface)"
                        strokeWidth={stacked ? 2 : 0}
                      />
                    ))}
                  </BarChart>
                ) : kind === "line" ? (
                  <LineChart data={data} margin={{ top: 6, right: 8, left: -8, bottom: 0 }}>
                    <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
                    <XAxis dataKey={xKey} tick={axis} tickLine={false} axisLine={false} interval="preserveStartEnd" minTickGap={16} />
                    <YAxis tick={axis} tickLine={false} axisLine={false} width={72} tickFormatter={(v: number) => format(v)} />
                    <RechartsTooltip cursor={{ stroke: "var(--border-strong)" }} content={<ChartTooltip series={series} format={format} />} />
                    {series.map((s, i) => (
                      <Line
                        key={s.key}
                        type="monotone"
                        dataKey={s.key}
                        stroke={SERIES[i % SERIES.length]}
                        strokeWidth={2}
                        dot={false}
                        activeDot={{ r: 4.5, strokeWidth: 2, stroke: "var(--surface)" }}
                      />
                    ))}
                  </LineChart>
                ) : (
                  <AreaChart data={data} margin={{ top: 6, right: 8, left: -8, bottom: 0 }}>
                    <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
                    <XAxis dataKey={xKey} tick={axis} tickLine={false} axisLine={false} interval="preserveStartEnd" minTickGap={16} />
                    <YAxis tick={axis} tickLine={false} axisLine={false} width={72} tickFormatter={(v: number) => format(v)} />
                    <RechartsTooltip cursor={{ stroke: "var(--border-strong)" }} content={<ChartTooltip series={series} format={format} />} />
                    {series.map((s, i) => (
                      <Area
                        key={s.key}
                        type="monotone"
                        dataKey={s.key}
                        stroke={SERIES[i % SERIES.length]}
                        strokeWidth={2}
                        fill={SERIES[i % SERIES.length]}
                        fillOpacity={0.1}
                        stackId={stacked ? "stack" : undefined}
                        activeDot={{ r: 4.5, strokeWidth: 2, stroke: "var(--surface)" }}
                      />
                    ))}
                  </AreaChart>
                )}
              </ResponsiveContainer>
            </div>
          </>
        )}
      </div>
    </Card>
  );
}

/** Part-to-whole as a single segmented bar with a labeled legend (instead of a donut). */
export function DistributionBar({
  segments,
  format = (v) => v.toLocaleString(),
  className,
}: {
  segments: { key: string; label: string; value: number; color?: string }[];
  format?: (v: number) => string;
  className?: string;
}) {
  const total = segments.reduce((sum, s) => sum + s.value, 0);
  return (
    <div className={className}>
      <div className="flex h-2.5 w-full gap-0.5 overflow-hidden rounded-full bg-surface-sunken" role="img" aria-label={segments.map((s) => `${s.label} ${format(s.value)}`).join(", ")}>
        {total > 0 &&
          segments
            .filter((s) => s.value > 0)
            .map((s) => (
              <span
                key={s.key}
                style={{ width: `${(s.value / total) * 100}%`, background: s.color ?? SERIES[segments.indexOf(s) % SERIES.length] }}
                className="h-full first:rounded-l-full last:rounded-r-full"
              />
            ))}
      </div>
      <ul className="mt-2.5 grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
        {segments.map((s, i) => (
          <li key={s.key} className="flex items-center gap-1.5">
            <span className="size-2.5 shrink-0 rounded-[3px]" style={{ background: s.color ?? SERIES[i % SERIES.length] }} aria-hidden="true" />
            <span className="min-w-0 flex-1 truncate text-muted-foreground">{s.label}</span>
            <span className="tabular font-medium">{format(s.value)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function Sparkline({ values, className, color = "var(--chart-1)" }: { values: number[]; className?: string; color?: string }) {
  if (values.length < 2) return null;
  const max = Math.max(...values);
  const min = Math.min(...values);
  const range = max - min || 1;
  const points = values.map((v, i) => `${(i / (values.length - 1)) * 100},${28 - ((v - min) / range) * 24}`).join(" ");
  return (
    <svg viewBox="0 0 100 30" preserveAspectRatio="none" className={cn("h-7 w-full", className)} aria-hidden="true">
      <polyline points={points} fill="none" stroke={color} strokeWidth={2} vectorEffect="non-scaling-stroke" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}
