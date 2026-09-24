"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, Columns3, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatNumber } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/controls";
import { Skeleton } from "@/components/ui/display";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/overlays";
import { ErrorState } from "./states";

export type Column<T> = {
  key: string;
  header: React.ReactNode;
  cell: (row: T) => React.ReactNode;
  align?: "left" | "right" | "center";
  className?: string;
  headerClassName?: string;
  /** Responsive: hide below this breakpoint. */
  hideBelow?: "sm" | "md" | "lg" | "xl";
  sortable?: boolean;
  /** Can be hidden from the Columns menu. */
  optional?: boolean;
  defaultHidden?: boolean;
  width?: string;
};

type SortState = { key: string; direction: "asc" | "desc" } | null;

const HIDE = { sm: "hidden sm:table-cell", md: "hidden md:table-cell", lg: "hidden lg:table-cell", xl: "hidden xl:table-cell" };

export function useColumnVisibility<T>(tableId: string, columns: Column<T>[]) {
  const initial = columns.filter((c) => c.defaultHidden).map((c) => c.key);
  const [hidden, setHidden] = useState<string[]>(initial);
  useEffect(() => {
    try {
      const raw = localStorage.getItem(`platform.columns.${tableId}`);
      if (raw) setHidden(JSON.parse(raw) as string[]);
    } catch {
      /* ignore */
    }
  }, [tableId]);
  const toggle = (key: string) => {
    setHidden((current) => {
      const next = current.includes(key) ? current.filter((k) => k !== key) : [...current, key];
      try {
        localStorage.setItem(`platform.columns.${tableId}`, JSON.stringify(next));
      } catch {
        /* ignore */
      }
      return next;
    });
  };
  return { hidden, toggle };
}

export function ColumnsMenu<T>({
  columns,
  hidden,
  onToggle,
}: {
  columns: Column<T>[];
  hidden: string[];
  onToggle: (key: string) => void;
}) {
  const optional = columns.filter((c) => c.optional);
  if (!optional.length) return null;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="secondary" size="sm" aria-label="Choose columns">
          <Columns3 /> <span className="hidden sm:inline">Columns</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent className="w-52">
        <DropdownMenuLabel>Visible columns</DropdownMenuLabel>
        {optional.map((c) => (
          <DropdownMenuCheckboxItem
            key={c.key}
            checked={!hidden.includes(c.key)}
            onCheckedChange={() => onToggle(c.key)}
            onSelect={(e) => e.preventDefault()}
          >
            {c.header}
          </DropdownMenuCheckboxItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function DataTable<T>({
  columns,
  rows,
  getRowId,
  loading = false,
  error,
  onRetry,
  empty,
  rowHref,
  onRowClick,
  selectable = false,
  selected,
  onSelectedChange,
  sort,
  onSortChange,
  hiddenColumns = [],
  density = "compact",
  className,
  caption,
  loadingRows = 8,
  rowClassName,
}: {
  columns: Column<T>[];
  rows: T[] | undefined;
  getRowId: (row: T) => string;
  loading?: boolean;
  error?: unknown;
  onRetry?: () => void;
  empty?: React.ReactNode;
  rowHref?: (row: T) => string;
  onRowClick?: (row: T) => void;
  selectable?: boolean;
  selected?: Set<string>;
  onSelectedChange?: (next: Set<string>) => void;
  sort?: SortState;
  onSortChange?: (sort: SortState) => void;
  hiddenColumns?: string[];
  density?: "compact" | "comfortable";
  className?: string;
  caption?: string;
  loadingRows?: number;
  rowClassName?: (row: T) => string | undefined;
}) {
  const router = useRouter();
  const visible = columns.filter((c) => !hiddenColumns.includes(c.key));
  const ids = rows?.map(getRowId) ?? [];
  const allSelected = selectable && ids.length > 0 && ids.every((id) => selected?.has(id));
  const someSelected = selectable && ids.some((id) => selected?.has(id));
  const cellPad = density === "compact" ? "px-3 py-2" : "px-3.5 py-3";

  function toggleAll() {
    if (!onSelectedChange) return;
    const next = new Set(selected);
    if (allSelected) ids.forEach((id) => next.delete(id));
    else ids.forEach((id) => next.add(id));
    onSelectedChange(next);
  }

  function toggleOne(id: string) {
    if (!onSelectedChange) return;
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onSelectedChange(next);
  }

  function header(column: Column<T>) {
    const active = sort?.key === column.key;
    const content = column.header;
    if (!column.sortable || !onSortChange) return content;
    return (
      <button
        type="button"
        onClick={() =>
          onSortChange(
            !active ? { key: column.key, direction: "asc" } : sort?.direction === "asc" ? { key: column.key, direction: "desc" } : null,
          )
        }
        className={cn("inline-flex items-center gap-1 hover:text-foreground", active && "text-foreground")}
        aria-label={`Sort by ${typeof content === "string" ? content : column.key}`}
      >
        {content}
        {active && (sort?.direction === "asc" ? <ArrowUp className="size-3" /> : <ArrowDown className="size-3" />)}
      </button>
    );
  }

  if (error) {
    return (
      <div className={cn("rounded-xl border border-border bg-surface", className)}>
        <ErrorState error={error} onRetry={onRetry} compact />
      </div>
    );
  }

  const isEmpty = !loading && rows !== undefined && rows.length === 0;

  return (
    <div className={cn("overflow-hidden rounded-xl border border-border bg-surface shadow-sm", className)}>
      <div className="scrollbar-thin overflow-x-auto">
        <table className="w-full border-collapse text-[13px]">
          {caption && <caption className="sr-only">{caption}</caption>}
          <thead>
            <tr className="border-b border-border bg-surface-muted/70">
              {selectable && (
                <th scope="col" className="w-10 px-3 py-2">
                  <Checkbox
                    checked={allSelected ? true : someSelected ? "indeterminate" : false}
                    onCheckedChange={toggleAll}
                    aria-label="Select all rows on this page"
                  />
                </th>
              )}
              {visible.map((column) => (
                <th
                  key={column.key}
                  scope="col"
                  style={column.width ? { width: column.width } : undefined}
                  aria-sort={
                    sort?.key === column.key ? (sort.direction === "asc" ? "ascending" : "descending") : undefined
                  }
                  className={cn(
                    "px-3 py-2 text-left text-xs font-medium whitespace-nowrap text-muted-foreground",
                    column.align === "right" && "text-right",
                    column.align === "center" && "text-center",
                    column.hideBelow && HIDE[column.hideBelow],
                    column.headerClassName,
                  )}
                >
                  {header(column)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading || rows === undefined
              ? Array.from({ length: loadingRows }, (_, i) => (
                  <tr key={i} className="border-b border-border last:border-0">
                    {selectable && (
                      <td className={cellPad}>
                        <Skeleton className="size-4" />
                      </td>
                    )}
                    {visible.map((column, j) => (
                      <td key={column.key} className={cn(cellPad, column.hideBelow && HIDE[column.hideBelow])}>
                        <Skeleton className="h-3.5" style={{ width: `${40 + ((i * 13 + j * 29) % 50)}%` }} />
                      </td>
                    ))}
                  </tr>
                ))
              : rows.map((row) => {
                  const id = getRowId(row);
                  const href = rowHref?.(row);
                  const clickable = Boolean(href || onRowClick);
                  return (
                    <tr
                      key={id}
                      data-row-id={id}
                      onClick={(event) => {
                        if (!clickable) return;
                        const target = event.target as HTMLElement;
                        if (target.closest("a,button,input,[role=checkbox],[data-no-row-click]")) return;
                        if (onRowClick) onRowClick(row);
                        else if (href) router.push(href);
                      }}
                      className={cn(
                        "border-b border-border transition-colors last:border-0",
                        clickable && "cursor-pointer hover:bg-surface-muted/60",
                        selected?.has(id) && "bg-primary-soft/40",
                        rowClassName?.(row),
                      )}
                    >
                      {selectable && (
                        <td className={cellPad} data-no-row-click>
                          <Checkbox
                            checked={selected?.has(id) ?? false}
                            onCheckedChange={() => toggleOne(id)}
                            aria-label="Select row"
                          />
                        </td>
                      )}
                      {visible.map((column) => (
                        <td
                          key={column.key}
                          className={cn(
                            cellPad,
                            "align-middle",
                            column.align === "right" && "text-right",
                            column.align === "center" && "text-center",
                            column.hideBelow && HIDE[column.hideBelow],
                            column.className,
                          )}
                        >
                          {column.cell(row)}
                        </td>
                      ))}
                    </tr>
                  );
                })}
          </tbody>
        </table>
      </div>
      {isEmpty && empty}
    </div>
  );
}

export function Pagination({
  page,
  pageSize,
  total,
  onPage,
  className,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPage: (page: number) => void;
  className?: string;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (total === 0) return null;
  const from = (page - 1) * pageSize + 1;
  const to = Math.min(total, page * pageSize);
  return (
    <div className={cn("mt-3 flex items-center justify-between gap-3 text-[13px] text-muted-foreground", className)}>
      <p className="tabular">
        {formatNumber(from)}–{formatNumber(to)} of {formatNumber(total)}
      </p>
      <div className="flex items-center gap-1">
        <Button variant="secondary" size="icon-sm" onClick={() => onPage(page - 1)} disabled={page <= 1} aria-label="Previous page">
          <ChevronLeft />
        </Button>
        <span className="tabular px-2">
          Page {page} of {pages}
        </span>
        <Button variant="secondary" size="icon-sm" onClick={() => onPage(page + 1)} disabled={page >= pages} aria-label="Next page">
          <ChevronRight />
        </Button>
      </div>
    </div>
  );
}

export function BulkBar({
  count,
  onClear,
  children,
}: {
  count: number;
  onClear: () => void;
  children: React.ReactNode;
}) {
  if (count === 0) return null;
  return (
    <div
      role="region"
      aria-label="Bulk actions"
      className="sticky bottom-4 z-20 mx-auto mt-3 flex w-fit max-w-full animate-scale-in items-center gap-2 rounded-lg border border-border bg-foreground px-2 py-1.5 text-background shadow-lg"
    >
      <span className="tabular px-2 text-[13px] font-medium">{count} selected</span>
      <div className="flex items-center gap-1 [&_button]:text-background [&_button:hover]:bg-background/15">{children}</div>
      <button
        type="button"
        onClick={onClear}
        className="rounded-md p-1.5 hover:bg-background/15"
        aria-label="Clear selection"
      >
        <X className="size-4" />
      </button>
    </div>
  );
}
