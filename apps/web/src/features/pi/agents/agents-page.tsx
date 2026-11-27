"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Plus, Search, SearchX, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Skeleton,
  Tabs,
  SegmentedList,
  SegmentedTrigger,
} from "@/components/ui/display";
import { Input } from "@/components/ui/input";
import { PageShell, RequirePermission } from "@/components/app/page";
import { EmptyState, ErrorState } from "@/components/app/states";
import { useScopedMutation } from "@/hooks/use-scoped";
import { AgentCard } from "./agent-card";
import { AgentCluster } from "./agent-avatar";
import { AgentFormDialog } from "./agent-form-dialog";
import { ConfirmDialog } from "./confirm-dialog";
import { meetingAgentsService, type Agent } from "./meeting-agents-service";
import { AGENTS_KEY, useAgents } from "./use-agents";

type Filter = "all" | "builtin" | "custom";

export function MeetingAgentsPage() {
  return (
    <RequirePermission permission="pi.meetings.read" area="pi">
      <AgentsView />
    </RequirePermission>
  );
}

function AgentsView() {
  const query = useAgents();
  const [filter, setFilter] = useState<Filter>("all");
  const [term, setTerm] = useState("");
  const [editing, setEditing] = useState<Agent | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [archiving, setArchiving] = useState<Agent | null>(null);

  const archive = useScopedMutation(
    (a: Agent) => meetingAgentsService.archive(a.key),
    {
      invalidate: [AGENTS_KEY],
      success: "Agent archived",
      onSuccess: () => setArchiving(null),
    },
  );

  const agents = useMemo(() => query.data ?? [], [query.data]);
  const mine = agents.filter((a) => a.kind === "custom");
  const shown = useMemo(() => {
    const t = term.trim().toLowerCase();
    return agents
      .filter((a) => filter === "all" || a.kind === filter)
      .filter(
        (a) =>
          !t ||
          a.name.toLowerCase().includes(t) ||
          a.tagline.toLowerCase().includes(t) ||
          a.focus.some((f) => f.toLowerCase().includes(t)),
      )
      .sort((a, b) => Number(b.is_default) - Number(a.is_default));
  }, [agents, filter, term]);

  function openNew() {
    setEditing(null);
    setFormOpen(true);
  }

  return (
    <PageShell>
      <Link
        href="/pi/meeting-intel"
        className="mb-3 inline-flex min-h-8 items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-3.5" aria-hidden="true" /> All meetings
      </Link>

      <header className="relative mb-6 overflow-hidden rounded-2xl border border-border bg-gradient-to-br from-primary-soft via-surface to-pi-soft p-5 sm:p-7">
        <div className="relative flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <h1 className="text-xl font-semibold tracking-tight sm:text-2xl">
              Meeting agents
            </h1>
            <p className="mt-1.5 max-w-xl text-[14px] text-foreground-secondary">
              Choose how pi listens and what it looks for in each meeting.
            </p>
          </div>
          <Button size="lg" onClick={openNew} className="min-h-11 sm:min-h-10">
            <Plus /> New agent
          </Button>
        </div>
      </header>

      <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <Tabs value={filter} onValueChange={(v) => setFilter(v as Filter)}>
          <SegmentedList aria-label="Show agents" className="h-10 sm:h-8">
            <SegmentedTrigger
              value="all"
              className="h-8.5 flex-1 whitespace-nowrap sm:h-6.5"
            >
              All
            </SegmentedTrigger>
            <SegmentedTrigger
              value="builtin"
              className="h-8.5 flex-1 whitespace-nowrap sm:h-6.5"
            >
              Built-in
            </SegmentedTrigger>
            <SegmentedTrigger
              value="custom"
              className="h-8.5 flex-1 whitespace-nowrap sm:h-6.5"
            >
              Yours{mine.length > 0 ? ` (${mine.length})` : ""}
            </SegmentedTrigger>
          </SegmentedList>
        </Tabs>
        <div className="relative sm:w-72">
          <Search
            className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            aria-label="Search agents"
            placeholder="Search agents"
            value={term}
            maxLength={60}
            onChange={(e) => setTerm(e.target.value)}
            className="h-11 pr-10 pl-9 sm:h-9"
          />
          {term && (
            <button
              type="button"
              aria-label="Clear search"
              onClick={() => setTerm("")}
              className="absolute top-1/2 right-1 grid size-9 -translate-y-1/2 place-items-center rounded-md text-muted-foreground hover:text-foreground"
            >
              <X className="size-4" aria-hidden="true" />
            </button>
          )}
        </div>
      </div>

      {query.isError ? (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      ) : query.isPending ? (
        <ul
          className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3"
          role="status"
          aria-label="Loading agents"
        >
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <li
              key={i}
              className="rounded-xl border border-border bg-surface p-4"
            >
              <div className="flex gap-3">
                <Skeleton className="size-14 rounded-2xl" />
                <div className="flex-1 space-y-2 pt-1">
                  <Skeleton className="h-4 w-32" />
                  <Skeleton className="h-3 w-full" />
                </div>
              </div>
              <Skeleton className="mt-5 h-3 w-4/5" />
              <Skeleton className="mt-2 h-3 w-3/5" />
              <Skeleton className="mt-5 h-6 w-2/3 rounded-full" />
            </li>
          ))}
        </ul>
      ) : filter === "custom" && mine.length === 0 && !term ? (
        <div className="flex flex-col items-center rounded-2xl border border-dashed border-border bg-surface px-6 py-12 text-center">
          <AgentCluster />
          <h2 className="mt-5 text-[15px] font-semibold">
            No agents of your own yet
          </h2>
          <p className="mt-1 max-w-sm text-[13px] text-muted-foreground">
            Write a few lines and pi will listen the way you ask: for a sales
            call, a training session or a customer visit.
          </p>
          <Button onClick={openNew} className="mt-4 min-h-11 sm:min-h-9">
            <Plus /> Create your first agent
          </Button>
        </div>
      ) : shown.length === 0 ? (
        <EmptyState
          icon={SearchX}
          title="No agent matches"
          description="Try a different word, or show all agents."
        />
      ) : (
        <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {shown.map((a) => (
            <AgentCard
              key={a.key}
              agent={a}
              onEdit={(x) => {
                setEditing(x);
                setFormOpen(true);
              }}
              onArchive={setArchiving}
            />
          ))}
        </ul>
      )}

      <AgentFormDialog
        open={formOpen}
        onOpenChange={setFormOpen}
        agent={editing}
      />
      <ConfirmDialog
        open={archiving !== null}
        onOpenChange={(o) => !o && setArchiving(null)}
        title={`Archive ${archiving?.name ?? "this agent"}?`}
        description="It will no longer be offered for new meetings or chats. Old chats that used it keep working."
        confirmLabel="Archive"
        pending={archive.isPending}
        onConfirm={() => archiving && archive.mutate(archiving)}
      />
    </PageShell>
  );
}
