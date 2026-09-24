"use client";

import { ChevronDown, Download } from "lucide-react";
import { centsToString, toCents } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { SegmentedList, SegmentedTrigger, Tabs } from "@/components/ui/display";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/overlays";
import { ModuleNav, PageHeader, PageShell, RequirePermission } from "@/components/app/page";
import { csvFilename, downloadCsv, type CsvValue } from "./csv";

/**
 * Shared report page frame: reports.read + the report's data permission, header,
 * report tabs from the navigation registry.
 */
export function ReportShell({
  title,
  description,
  permission,
  area,
  actions,
  children,
}: {
  title: string;
  description: string;
  permission?: string;
  area: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
}) {
  const page = (
    <PageShell>
      <PageHeader title={title} description={description} actions={actions} />
      <ModuleNav moduleKey="reports" />
      {children}
    </PageShell>
  );
  return (
    <RequirePermission permission="reports.read" area="reports">
      {permission ? (
        <RequirePermission permission={permission} area={area}>
          {page}
        </RequirePermission>
      ) : (
        page
      )}
    </RequirePermission>
  );
}

export type CsvExport = {
  label: string;
  filename: string;
  headers: string[];
  rows: () => CsvValue[][];
};

/** "Export CSV" as a single button, or a menu when a report offers several tables. */
export function ExportMenu({ exports, disabled }: { exports: CsvExport[]; disabled?: boolean }) {
  const run = (e: CsvExport) => downloadCsv(csvFilename(e.filename), e.headers, e.rows());
  if (exports.length === 1) {
    const only = exports[0]!;
    return (
      <Button variant="secondary" size="sm" onClick={() => run(only)} disabled={disabled}>
        <Download /> Export CSV
      </Button>
    );
  }
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="secondary" size="sm" disabled={disabled}>
          <Download /> Export CSV <ChevronDown className="opacity-60" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent className="w-56">
        <DropdownMenuLabel>Download as CSV</DropdownMenuLabel>
        {exports.map((e) => (
          <DropdownMenuItem key={e.filename} onSelect={() => run(e)}>
            {e.label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** Period switcher (SegmentedList) bound to a string value. */
export function RangeTabs({
  value,
  options,
  onChange,
  label,
}: {
  value: string;
  options: { value: string; label: string }[];
  onChange: (value: string) => void;
  label: string;
}) {
  return (
    <Tabs value={value} onValueChange={onChange}>
      <SegmentedList aria-label={label}>
        {options.map((o) => (
          <SegmentedTrigger key={o.value} value={o.value}>
            {o.label}
          </SegmentedTrigger>
        ))}
      </SegmentedList>
    </Tabs>
  );
}

/** "2026-09" → "Sep 2026" (or "Sep" when short). Parsed as a local date, never UTC. */
export function monthLabel(month: string, short = false) {
  const [y, m] = month.split("-").map(Number);
  if (!y || !m) return month;
  return new Date(y, m - 1, 1).toLocaleDateString("en-US", short ? { month: "short" } : { month: "short", year: "numeric" });
}

/** "2026-09-14" → "Sep 14". */
export function dayLabel(day: string) {
  const [y, m, d] = day.slice(0, 10).split("-").map(Number);
  if (!y || !m || !d) return day;
  return new Date(y, m - 1, d).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

/** Sum decimal strings exactly (integer cents). */
export function sumMoney(values: (string | null | undefined)[]) {
  return centsToString(values.reduce((sum, v) => sum + toCents(v), BigInt(0)));
}

export function ratio(part: string | number, whole: string | number): number | null {
  const w = Number(whole);
  if (!w) return null;
  return Number(part) / w;
}
