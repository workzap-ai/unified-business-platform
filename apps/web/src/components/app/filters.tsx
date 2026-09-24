"use client";

import { useEffect, useRef, useState } from "react";
import { useLocalStorageState } from "@/hooks/use-local-storage";
import {
  Bookmark,
  BookmarkPlus,
  Check,
  ChevronDown,
  Search,
  Star,
  Trash2,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/overlays";

const NO_VIEWS: SavedView[] = [];

export function SearchInput({
  value,
  onChange,
  placeholder = "Search…",
  className,
  delay = 250,
  autoFocus,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  delay?: number;
  autoFocus?: boolean;
}) {
  const [draft, setDraft] = useState(value);
  const last = useRef(value);
  useEffect(() => {
    if (value !== last.current) {
      last.current = value;
      setDraft(value);
    }
  }, [value]);
  useEffect(() => {
    if (draft === last.current) return;
    const timer = setTimeout(() => {
      last.current = draft;
      onChange(draft);
    }, delay);
    return () => clearTimeout(timer);
  }, [draft, delay, onChange]);
  return (
    <div className={cn("relative min-w-0", className)}>
      <Search
        className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground"
        aria-hidden="true"
      />
      <Input
        type="search"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        placeholder={placeholder}
        aria-label={placeholder}
        className="h-8 pr-8 pl-8 text-[13px]"
        autoFocus={autoFocus}
      />
      {draft && (
        <button
          type="button"
          onClick={() => {
            setDraft("");
            last.current = "";
            onChange("");
          }}
          className="absolute top-1/2 right-1.5 -translate-y-1/2 rounded p-1 text-muted-foreground hover:bg-surface-muted"
          aria-label="Clear search"
        >
          <X className="size-3.5" />
        </button>
      )}
    </div>
  );
}

export type FilterOption = { value: string; label: string; count?: number };

/** A single-select filter rendered as a compact chip with a menu. */
export function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: FilterOption[];
  onChange: (value: string) => void;
}) {
  const current = options.find((o) => o.value === value);
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className={cn(
            "inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md border px-2.5 text-[13px] font-medium transition-colors",
            current
              ? "border-primary/40 bg-primary-soft text-primary-soft-foreground"
              : "border-dashed border-border-strong bg-surface text-foreground-secondary hover:bg-surface-muted",
          )}
        >
          {label}
          {current && (
            <>
              <span className="text-primary-soft-foreground/60">:</span>
              <span className="max-w-32 truncate">{current.label}</span>
            </>
          )}
          <ChevronDown className="size-3.5 opacity-60" aria-hidden="true" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-56">
        <DropdownMenuLabel>{label}</DropdownMenuLabel>
        {options.map((option) => (
          <DropdownMenuItem
            key={option.value}
            onSelect={() =>
              onChange(option.value === value ? "" : option.value)
            }
          >
            <span className="flex size-4 items-center justify-center">
              {option.value === value && <Check className="!text-primary" />}
            </span>
            <span className="flex-1">{option.label}</span>
            {option.count !== undefined && (
              <span className="tabular text-xs text-muted-foreground">
                {option.count}
              </span>
            )}
          </DropdownMenuItem>
        ))}
        {current && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => onChange("")}>
              <X /> Clear filter
            </DropdownMenuItem>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function FilterBar({
  children,
  actions,
  activeCount = 0,
  onClear,
  className,
}: {
  children: React.ReactNode;
  actions?: React.ReactNode;
  activeCount?: number;
  onClear?: () => void;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "mb-3 flex flex-col gap-2 md:flex-row md:items-center",
        className,
      )}
    >
      <div className="scrollbar-thin flex min-w-0 flex-1 items-center gap-2 overflow-x-auto pb-0.5">
        {children}
        {activeCount > 0 && onClear && (
          <Button
            variant="ghost"
            size="sm"
            onClick={onClear}
            className="shrink-0 text-muted-foreground"
          >
            Clear all
          </Button>
        )}
      </div>
      {actions && (
        <div className="flex shrink-0 items-center gap-2">{actions}</div>
      )}
    </div>
  );
}

export type SavedView = {
  id: string;
  name: string;
  params: Record<string, string>;
  builtIn?: boolean;
};

/**
 * Saved views: built-in views from the page plus views the member saves. Saved views are
 * stored per browser for now; the params shape is ready to become a server preference.
 */
export function SavedViews({
  tableId,
  views,
  current,
  onApply,
}: {
  tableId: string;
  views: SavedView[];
  current: Record<string, string>;
  onApply: (params: Record<string, string>) => void;
}) {
  const storageKey = `platform.views.${tableId}`;
  const [custom, persist] = useLocalStorageState<SavedView[]>(
    storageKey,
    NO_VIEWS,
  );
  const [name, setName] = useState("");
  const [open, setOpen] = useState(false);
  const relevant = (params: Record<string, string>) =>
    Object.entries(params).filter(([k, v]) => v && k !== "page");
  const same = (a: Record<string, string>, b: Record<string, string>) => {
    const ea = relevant(a);
    const eb = relevant(b);
    return ea.length === eb.length && ea.every(([k, v]) => b[k] === v);
  };
  const all = [...views, ...custom];
  const activeView = all.find((v) => same(v.params, current));

  return (
    <div className="scrollbar-thin mb-3 flex items-center gap-1 overflow-x-auto">
      {views.map((view) => (
        <button
          key={view.id}
          type="button"
          onClick={() => onApply(view.params)}
          aria-pressed={activeView?.id === view.id}
          className={cn(
            "h-7 shrink-0 rounded-md px-2.5 text-[13px] font-medium transition-colors",
            activeView?.id === view.id
              ? "bg-foreground text-background"
              : "text-foreground-secondary hover:bg-surface-muted",
          )}
        >
          {view.name}
        </button>
      ))}
      {custom.length > 0 && (
        <span className="mx-1 h-4 w-px shrink-0 bg-border" aria-hidden="true" />
      )}
      {custom.map((view) => (
        <span key={view.id} className="group flex shrink-0 items-center">
          <button
            type="button"
            onClick={() => onApply(view.params)}
            aria-pressed={activeView?.id === view.id}
            className={cn(
              "flex h-7 items-center gap-1 rounded-md px-2.5 text-[13px] font-medium",
              activeView?.id === view.id
                ? "bg-foreground text-background"
                : "text-foreground-secondary hover:bg-surface-muted",
            )}
          >
            <Star className="size-3" aria-hidden="true" /> {view.name}
          </button>
          <button
            type="button"
            onClick={() => persist(custom.filter((v) => v.id !== view.id))}
            className="ml-0.5 rounded p-1 text-muted-foreground opacity-0 group-hover:opacity-100 hover:bg-surface-muted focus-visible:opacity-100"
            aria-label={`Delete view ${view.name}`}
          >
            <Trash2 className="size-3" />
          </button>
        </span>
      ))}
      {!activeView && relevant(current).length > 0 && (
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger asChild>
            <Button variant="ghost" size="xs" className="shrink-0 text-primary">
              <BookmarkPlus /> Save view
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-64">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (!name.trim()) return;
                persist([
                  ...custom,
                  {
                    id: `view-${Date.now()}`,
                    name: name.trim().slice(0, 40),
                    params: current,
                  },
                ]);
                setName("");
                setOpen(false);
              }}
            >
              <label
                htmlFor={`${tableId}-view-name`}
                className="text-[13px] font-medium"
              >
                View name
              </label>
              <Input
                id={`${tableId}-view-name`}
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="mt-1.5 h-8"
                placeholder="e.g. Overdue, high value"
                autoFocus
              />
              <p className="mt-1.5 text-2xs text-muted-foreground">
                Saves the current filters and search on this device.
              </p>
              <Button
                type="submit"
                size="sm"
                className="mt-3 w-full"
                disabled={!name.trim()}
              >
                <Bookmark /> Save view
              </Button>
            </form>
          </PopoverContent>
        </Popover>
      )}
    </div>
  );
}
