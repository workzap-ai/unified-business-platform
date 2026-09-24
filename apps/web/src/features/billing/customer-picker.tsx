"use client";

import { useEffect, useId, useState } from "react";
import { Check, ChevronsUpDown, Search } from "lucide-react";
import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/input";
import { Avatar, Skeleton } from "@/components/ui/display";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/overlays";
import { useScopedQuery } from "@/hooks/use-scoped";
import { customersService } from "@/features/customers/service";
import { errorMessage } from "@/services/api-client";

export type PickedCustomer = { id: string; name: string; detail?: string | null };

function useDebounced<T>(value: T, delay = 250) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

/** Searchable single-select combobox over active customers. */
export function CustomerPicker({
  id,
  value,
  onChange,
  invalid,
  disabled,
}: {
  id?: string;
  value: PickedCustomer | null;
  onChange: (customer: PickedCustomer) => void;
  invalid?: boolean;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [active, setActive] = useState(0);
  const debounced = useDebounced(search.trim());
  const listId = useId();
  const query = useScopedQuery(
    ["customers", { search: debounced, status: "active", pageSize: 8 }],
    () => customersService.list({ search: debounced || undefined, status: "active", pageSize: 8 }),
    { enabled: open, placeholderData: (previous) => previous },
  );
  const items = query.data?.items ?? [];
  const activeIndex = Math.min(active, Math.max(0, items.length - 1));

  function choose(index: number) {
    const customer = items[index];
    if (!customer) return;
    onChange({ id: customer.id, name: customer.name, detail: customer.company ?? customer.email ?? customer.phone });
    setOpen(false);
    setSearch("");
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          id={id}
          type="button"
          disabled={disabled}
          aria-invalid={invalid || undefined}
          aria-haspopup="listbox"
          aria-expanded={open}
          className={cn(
            "flex h-10 w-full items-center gap-2.5 rounded-md border border-border bg-surface px-3 text-left text-sm shadow-sm transition-colors hover:border-border-strong focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/15 focus-visible:outline-none disabled:opacity-60",
            invalid && "border-danger",
          )}
        >
          {value ? (
            <>
              <Avatar name={value.name} size="sm" />
              <span className="min-w-0 flex-1 truncate">
                <span className="font-medium">{value.name}</span>
                {value.detail && <span className="ml-2 text-muted-foreground">{value.detail}</span>}
              </span>
            </>
          ) : (
            <span className="flex-1 text-muted-foreground/80">Choose a customer…</span>
          )}
          <ChevronsUpDown className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-[min(28rem,calc(100vw-2rem))] p-0">
        <div className="relative border-b border-border p-2">
          <Search
            className="pointer-events-none absolute top-1/2 left-4.5 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            autoFocus
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setActive(0);
            }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setActive(Math.min(activeIndex + 1, items.length - 1));
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setActive(Math.max(activeIndex - 1, 0));
              } else if (e.key === "Enter") {
                e.preventDefault();
                choose(activeIndex);
              }
            }}
            placeholder="Search name, company, email or phone"
            aria-label="Search customers"
            role="combobox"
            aria-expanded="true"
            aria-controls={listId}
            aria-activedescendant={items[activeIndex] ? `${listId}-${items[activeIndex].id}` : undefined}
            className="h-8 pl-8 text-[13px]"
          />
        </div>
        <div className="scrollbar-thin max-h-72 overflow-y-auto p-1">
          {query.isPending ? (
            <div className="space-y-1 p-1">
              {Array.from({ length: 4 }, (_, i) => (
                <Skeleton key={i} className="h-9" />
              ))}
            </div>
          ) : query.isError ? (
            <p className="px-3 py-4 text-[13px] text-danger">
              {errorMessage(query.error, "Customers couldn't be loaded.")}
            </p>
          ) : items.length === 0 ? (
            <p className="px-3 py-4 text-center text-[13px] text-muted-foreground">
              {debounced ? `No active customers match "${debounced}".` : "No active customers yet."}
            </p>
          ) : (
            <ul id={listId} role="listbox" aria-label="Customers">
              {items.map((customer, index) => {
                const selected = value?.id === customer.id;
                return (
                  <li
                    key={customer.id}
                    id={`${listId}-${customer.id}`}
                    role="option"
                    aria-selected={selected}
                    onMouseEnter={() => setActive(index)}
                    onClick={() => choose(index)}
                    className={cn(
                      "flex cursor-pointer items-center gap-2.5 rounded-md px-2 py-1.5 text-[13px]",
                      index === activeIndex && "bg-surface-muted",
                    )}
                  >
                    <Avatar name={customer.name} size="sm" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-medium">{customer.name}</span>
                      {(customer.company || customer.email || customer.phone) && (
                        <span className="block truncate text-xs text-muted-foreground">
                          {[customer.company, customer.email ?? customer.phone].filter(Boolean).join(" · ")}
                        </span>
                      )}
                    </span>
                    {selected && <Check className="size-4 shrink-0 text-primary" aria-hidden="true" />}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
