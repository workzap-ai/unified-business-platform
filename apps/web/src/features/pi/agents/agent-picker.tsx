"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Check, Plus, Search, SearchX, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/display";
import { Dialog, DialogContent, DialogHeader } from "@/components/ui/overlays";
import { ErrorState } from "@/components/app/states";
import { AgentAvatar } from "./agent-avatar";
import type { Agent } from "./meeting-agents-service";
import { useAgents } from "./use-agents";

function matches(a: Agent, term: string) {
  const t = term.trim().toLowerCase();
  if (!t) return true;
  return (
    a.name.toLowerCase().includes(t) ||
    a.tagline.toLowerCase().includes(t) ||
    a.focus.some((f) => f.toLowerCase().includes(t))
  );
}

/**
 * A searchable list of agents. Arrow keys move, Enter chooses, Esc closes. pi (the default) is
 * pinned first; built-in agents come next and the team's own last.
 */
export function AgentPicker({
  open,
  onOpenChange,
  value,
  onSelect,
  onCreate,
  title = "Choose an agent",
  description = "An agent changes what pi listens for. pi still says it is an AI first.",
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  value: string | null | undefined;
  onSelect: (agent: Agent) => void;
  onCreate?: () => void;
  title?: string;
  description?: string;
}) {
  const query = useAgents(open);
  const [term, setTerm] = useState("");
  const [active, setActive] = useState(0);
  const listId = useId();
  const listRef = useRef<HTMLUListElement>(null);

  const sections = useMemo(() => {
    const all = (query.data ?? []).filter((a) => matches(a, term));
    return [
      { label: "", items: all.filter((a) => a.is_default) },
      {
        label: "Built-in",
        items: all.filter((a) => !a.is_default && a.kind === "builtin"),
      },
      { label: "Yours", items: all.filter((a) => a.kind === "custom") },
    ].filter((s) => s.items.length > 0);
  }, [query.data, term]);
  const flat = useMemo(() => sections.flatMap((s) => s.items), [sections]);
  const current = Math.min(active, Math.max(flat.length - 1, 0));
  const activeId = flat[current] ? `${listId}-${flat[current].key}` : undefined;

  useEffect(() => {
    if (!activeId) return;
    document.getElementById(activeId)?.scrollIntoView({ block: "nearest" });
  }, [activeId]);

  function choose(a: Agent | undefined) {
    if (!a) return;
    onSelect(a);
    onOpenChange(false);
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive(flat.length ? (current + 1) % flat.length : 0);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive(flat.length ? (current - 1 + flat.length) % flat.length : 0);
    } else if (e.key === "Home") {
      e.preventDefault();
      setActive(0);
    } else if (e.key === "End") {
      e.preventDefault();
      setActive(Math.max(flat.length - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      choose(flat[current]);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) {
          setTerm("");
          setActive(0);
        }
        onOpenChange(o);
      }}
    >
      <DialogContent size="sm" className="max-h-[min(36rem,calc(100dvh-2rem))]">
        <DialogHeader title={title} description={description} />
        <div className="border-b border-border px-4 py-3">
          <div className="relative">
            <Search
              className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
              aria-hidden="true"
            />
            <input
              autoFocus
              role="combobox"
              aria-expanded="true"
              aria-controls={listId}
              aria-activedescendant={activeId}
              aria-autocomplete="list"
              aria-label="Search agents"
              placeholder="Search agents"
              value={term}
              maxLength={60}
              onChange={(e) => {
                setTerm(e.target.value);
                setActive(0);
              }}
              onKeyDown={onKeyDown}
              className="h-11 w-full rounded-lg border border-border bg-surface-muted pr-10 pl-9 text-sm text-foreground transition-colors placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/15 focus-visible:outline-none"
            />
            {term && (
              <button
                type="button"
                aria-label="Clear search"
                onClick={() => {
                  setTerm("");
                  setActive(0);
                }}
                className="absolute top-1/2 right-1.5 grid size-8 -translate-y-1/2 place-items-center rounded-md text-muted-foreground hover:bg-surface-sunken hover:text-foreground"
              >
                <X className="size-4" aria-hidden="true" />
              </button>
            )}
          </div>
        </div>

        <div className="scrollbar-thin min-h-0 flex-1 overflow-y-auto p-2">
          {query.isError ? (
            <ErrorState
              compact
              error={query.error}
              onRetry={() => void query.refetch()}
            />
          ) : query.isPending ? (
            <div
              className="space-y-1"
              aria-label="Loading agents"
              role="status"
            >
              {[0, 1, 2, 3].map((i) => (
                <div key={i} className="flex items-center gap-3 p-2.5">
                  <Skeleton className="size-10 rounded-xl" />
                  <div className="flex-1 space-y-1.5">
                    <Skeleton className="h-3.5 w-28" />
                    <Skeleton className="h-3 w-44" />
                  </div>
                </div>
              ))}
            </div>
          ) : flat.length === 0 ? (
            <div className="flex flex-col items-center px-6 py-10 text-center">
              <span className="grid size-10 place-items-center rounded-xl bg-surface-muted text-muted-foreground">
                <SearchX className="size-5" aria-hidden="true" />
              </span>
              <p className="mt-3 text-sm font-semibold">No agent matches</p>
              <p className="mt-1 text-[13px] text-muted-foreground">
                Try a different word, or create your own agent below.
              </p>
            </div>
          ) : (
            <ul
              id={listId}
              ref={listRef}
              role="listbox"
              aria-label="Agents"
              className="space-y-1"
            >
              {sections.map((s) => (
                <li key={s.label || "pinned"} role="presentation">
                  {s.label && (
                    <p
                      aria-hidden="true"
                      className="px-2.5 pt-2 pb-1 text-2xs font-semibold tracking-wide text-muted-foreground uppercase"
                    >
                      {s.label}
                    </p>
                  )}
                  <ul role="group" aria-label={s.label || "pi"}>
                    {s.items.map((a) => {
                      const selected = (value || "pi") === a.key;
                      const isActive = flat[current]?.key === a.key;
                      return (
                        <li
                          key={a.key}
                          id={`${listId}-${a.key}`}
                          role="option"
                          aria-selected={selected}
                          onMouseMove={() => setActive(flat.indexOf(a))}
                          onClick={() => choose(a)}
                          className={cn(
                            "flex min-h-14 cursor-pointer items-center gap-3 rounded-xl px-2.5 py-2 transition-colors",
                            isActive &&
                              "bg-surface-muted ring-1 ring-ring/40 ring-inset",
                            selected && "bg-primary-soft/60",
                          )}
                        >
                          <AgentAvatar agent={a} size="md" />
                          <span className="min-w-0 flex-1">
                            <span className="flex items-center gap-2">
                              <span className="truncate text-[14px] font-semibold">
                                {a.name}
                              </span>
                              <span
                                className={cn(
                                  "shrink-0 rounded-full px-1.5 py-px text-[10.5px] font-medium",
                                  a.kind === "custom"
                                    ? "bg-pi-soft text-pi-soft-foreground"
                                    : "bg-surface-sunken text-foreground-secondary",
                                )}
                              >
                                {a.kind === "custom" ? "Yours" : "Built-in"}
                              </span>
                            </span>
                            {a.tagline && (
                              <span className="block truncate text-xs text-muted-foreground">
                                {a.tagline}
                              </span>
                            )}
                          </span>
                          {selected && (
                            <Check
                              className="size-4 shrink-0 text-primary"
                              aria-hidden="true"
                            />
                          )}
                        </li>
                      );
                    })}
                  </ul>
                </li>
              ))}
            </ul>
          )}
        </div>

        {onCreate && (
          <div className="border-t border-border bg-surface-muted/60 px-4 py-2.5">
            <Button
              variant="link"
              className="min-h-11 w-full justify-start sm:min-h-9"
              onClick={onCreate}
            >
              <Plus /> Create your own agent
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
