"use client";

import { useEffect, useId, useState } from "react";
import { Command } from "cmdk";
import { Check, ChevronsUpDown, Search, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { Avatar, Spinner } from "@/components/ui/display";
import { fieldBase } from "@/components/ui/input";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/overlays";
import { useScopedQuery } from "@/hooks/use-scoped";
import { customersService } from "@/features/customers/service";

export type CustomerOption = { id: string; name: string };

/** Searchable customer picker backed by the customers service (server-side search). */
export function CustomerCombobox({
  id,
  value,
  onChange,
  invalid,
  describedBy,
  disabled,
}: {
  id?: string;
  value: CustomerOption | null;
  onChange: (value: CustomerOption | null) => void;
  invalid?: boolean;
  describedBy?: string;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const listId = useId();
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(search.trim()), 200);
    return () => clearTimeout(timer);
  }, [search]);

  const results = useScopedQuery(
    ["customers", "picker", debounced],
    () =>
      customersService.list({
        search: debounced || undefined,
        status: "active",
        pageSize: 8,
      }),
    { enabled: open, placeholderData: (previous) => previous },
  );

  function pick(option: CustomerOption | null) {
    onChange(option);
    setOpen(false);
    setSearch("");
  }

  return (
    <div className="relative">
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <button
            id={id}
            type="button"
            role="combobox"
            aria-expanded={open}
            aria-controls={listId}
            aria-haspopup="listbox"
            aria-invalid={invalid || undefined}
            aria-describedby={describedBy}
            disabled={disabled}
            className={cn(
              fieldBase,
              "flex h-9 items-center gap-2 pr-8 text-left",
            )}
          >
            {value ? (
              <>
                <Avatar name={value.name} size="xs" />
                <span className="truncate">{value.name}</span>
              </>
            ) : (
              <span className="text-muted-foreground/80">
                Search customers…
              </span>
            )}
            <ChevronsUpDown
              className="absolute top-1/2 right-2.5 size-4 -translate-y-1/2 text-muted-foreground"
              aria-hidden="true"
            />
          </button>
        </PopoverTrigger>
        <PopoverContent className="w-[var(--radix-popover-trigger-width)] min-w-64 p-0">
          <Command shouldFilter={false} loop label="Choose a customer">
            <div className="flex items-center gap-2 border-b border-border px-3">
              <Search
                className="size-4 shrink-0 text-muted-foreground"
                aria-hidden="true"
              />
              <Command.Input
                value={search}
                onValueChange={setSearch}
                placeholder="Name, phone or email"
                className="h-10 w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
                autoFocus
              />
              {results.isFetching && <Spinner label="Searching customers" />}
            </div>
            <Command.List
              id={listId}
              className="scrollbar-thin max-h-64 overflow-y-auto p-1"
            >
              {results.isError ? (
                <p className="px-3 py-6 text-center text-[13px] text-danger">
                  Customers couldn&apos;t be loaded.
                </p>
              ) : (
                <>
                  {!results.isPending && (
                    <Command.Empty className="px-3 py-6 text-center text-[13px] text-muted-foreground">
                      No active customers match “{debounced}”.
                    </Command.Empty>
                  )}
                  {results.data?.items.map((c) => (
                    <Command.Item
                      key={c.id}
                      value={c.id}
                      onSelect={() => pick({ id: c.id, name: c.name })}
                      className="flex cursor-pointer items-center gap-2.5 rounded-md px-2 py-1.5 text-[13px] data-[selected=true]:bg-surface-muted"
                    >
                      <Avatar name={c.name} size="sm" />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate font-medium">
                          {c.name}
                        </span>
                        <span className="block truncate text-xs text-muted-foreground">
                          {c.phone ??
                            c.company ??
                            c.email ??
                            "No contact details"}
                        </span>
                      </span>
                      {value?.id === c.id && (
                        <Check
                          className="size-4 text-primary"
                          aria-hidden="true"
                        />
                      )}
                    </Command.Item>
                  ))}
                </>
              )}
            </Command.List>
          </Command>
        </PopoverContent>
      </Popover>
      {value && !disabled && (
        <button
          type="button"
          onClick={() => onChange(null)}
          className="absolute top-1/2 right-8 -translate-y-1/2 rounded p-1 text-muted-foreground hover:bg-surface-muted hover:text-foreground"
          aria-label="Clear customer"
        >
          <X className="size-3.5" />
        </button>
      )}
    </div>
  );
}
