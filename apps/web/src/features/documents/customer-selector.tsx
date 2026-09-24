"use client";

import { useEffect, useId, useState } from "react";
import { Command } from "cmdk";
import { Check, ChevronsUpDown, Search, UserRound } from "lucide-react";
import { cn } from "@/lib/utils";
import { Avatar, Spinner } from "@/components/ui/display";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/overlays";
import { useScopedQuery } from "@/hooks/use-scoped";
import { customersService } from "@/features/customers/service";
import type { Customer } from "@/features/business/types";

export type SelectedCustomer = Pick<Customer, "id" | "name"> &
  Partial<Pick<Customer, "email" | "phone" | "company">>;

export function useDebouncedValue<T>(value: T, delay = 250) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

export const commandItemClass =
  "flex cursor-pointer items-center gap-2.5 rounded-md px-2 py-2 text-[13px] text-foreground outline-none aria-selected:bg-surface-muted data-[disabled=true]:pointer-events-none data-[disabled=true]:opacity-50";

/** Searchable customer combobox backed by the customers service. */
export function CustomerSelector({
  id,
  value,
  onChange,
  invalid = false,
  disabled = false,
}: {
  id?: string;
  value: SelectedCustomer | null;
  onChange: (customer: SelectedCustomer | null) => void;
  invalid?: boolean;
  disabled?: boolean;
}) {
  const listId = useId();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const term = useDebouncedValue(query.trim());
  const results = useScopedQuery(
    ["customers", "selector", term],
    () =>
      customersService.list({
        search: term || undefined,
        pageSize: 8,
        status: "active",
      }),
    { enabled: open, staleTime: 30_000 },
  );

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          id={id}
          type="button"
          role="combobox"
          aria-expanded={open}
          aria-controls={listId}
          aria-invalid={invalid || undefined}
          disabled={disabled}
          className={cn(
            "flex h-10 w-full items-center gap-2.5 rounded-md border border-border bg-surface px-3 text-left text-sm shadow-sm transition-colors hover:border-border-strong focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/15 focus-visible:outline-none disabled:opacity-60",
            invalid && "border-danger",
          )}
        >
          {value ? (
            <>
              <Avatar name={value.name} size="sm" />
              <span className="min-w-0 flex-1 truncate font-medium">
                {value.name}
              </span>
              {value.company && (
                <span className="hidden truncate text-xs text-muted-foreground sm:inline">
                  {value.company}
                </span>
              )}
            </>
          ) : (
            <>
              <UserRound
                className="size-4 text-muted-foreground"
                aria-hidden="true"
              />
              <span className="flex-1 text-muted-foreground">
                Choose a customer…
              </span>
            </>
          )}
          <ChevronsUpDown
            className="size-4 shrink-0 text-muted-foreground"
            aria-hidden="true"
          />
        </button>
      </PopoverTrigger>
      <PopoverContent
        id={listId}
        className="w-[min(calc(100vw-2rem),420px)] p-0"
        align="start"
      >
        <Command label="Find a customer" shouldFilter={false} loop>
          <div className="flex items-center gap-2 border-b border-border px-3">
            <Search
              className="size-4 text-muted-foreground"
              aria-hidden="true"
            />
            <Command.Input
              value={query}
              onValueChange={setQuery}
              placeholder="Search by name, phone or email…"
              className="h-10 flex-1 bg-transparent text-[13.5px] outline-none placeholder:text-muted-foreground"
              autoFocus
            />
            {results.isFetching && <Spinner />}
          </div>
          <Command.List className="scrollbar-thin max-h-72 overflow-y-auto p-1">
            {results.isError ? (
              <p
                role="alert"
                className="px-3 py-6 text-center text-[13px] text-danger"
              >
                Couldn&apos;t load customers.{" "}
                <button
                  type="button"
                  className="font-medium underline"
                  onClick={() => void results.refetch()}
                >
                  Try again
                </button>
              </p>
            ) : results.data && results.data.items.length === 0 ? (
              <p className="px-3 py-6 text-center text-[13px] text-muted-foreground">
                {term
                  ? `No active customers match “${term}”.`
                  : "No active customers yet."}
              </p>
            ) : !results.data ? (
              <p className="px-3 py-6 text-center text-[13px] text-muted-foreground">
                Loading customers…
              </p>
            ) : (
              results.data.items.map((customer) => (
                <Command.Item
                  key={customer.id}
                  value={customer.id}
                  onSelect={() => {
                    onChange(customer);
                    setOpen(false);
                    setQuery("");
                  }}
                  className={commandItemClass}
                >
                  <Avatar name={customer.name} size="sm" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">
                      {customer.name}
                    </span>
                    <span className="block truncate text-xs text-muted-foreground">
                      {[customer.company, customer.phone ?? customer.email]
                        .filter(Boolean)
                        .join(" · ") || "No contact details"}
                    </span>
                  </span>
                  {value?.id === customer.id && (
                    <Check className="size-4 text-primary" aria-hidden="true" />
                  )}
                </Command.Item>
              ))
            )}
          </Command.List>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
