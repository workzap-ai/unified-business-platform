"use client";

import { useState } from "react";
import Link from "next/link";
import { useQueries } from "@tanstack/react-query";
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  TouchSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import {
  ArrowRightLeft,
  GripVertical,
  Info,
  MoreHorizontal,
  Plus,
  SquareArrowOutUpRight,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { formatMoney, formatNumber, relativeTime } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Skeleton, Spinner } from "@/components/ui/display";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/overlays";
import {
  ModuleNav,
  PageHeader,
  PageShell,
  RequirePermission,
} from "@/components/app/page";
import { ErrorState } from "@/components/app/states";
import { StatusBadge } from "@/components/app/status-badge";
import { useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import type { Lead, LeadStage } from "@/features/business/types";
import { salesService } from "./service";
import {
  isStage,
  LeadSourceBadge,
  STAGE_DESCRIPTIONS,
  STAGE_LABELS,
  STAGES,
} from "./lib";
import { useMoveLead } from "./components/use-move-lead";

const COLUMN_LIMIT = 100;

export function PipelineBoardPage() {
  return (
    <RequirePermission permission="sales.read" area="the sales pipeline">
      <PipelineBoard />
    </RequirePermission>
  );
}

function PipelineBoard() {
  const { can, scopeKey, status } = useSession();
  const canWrite = can("sales.write");
  const pipeline = useScopedQuery(["pipeline"], () => salesService.pipeline());
  const columns = useQueries({
    queries: STAGES.map((stage) => ({
      queryKey: [
        ...scopeKey,
        "leads",
        "list",
        { stage, page: 1, pageSize: COLUMN_LIMIT },
      ],
      queryFn: () =>
        salesService.leads({ stage, page: 1, pageSize: COLUMN_LIMIT }),
      enabled: status === "ready",
    })),
  });

  const [active, setActive] = useState<Lead | null>(null);
  const { move, dialog, isPending, variables } = useMoveLead();
  const movingId = isPending ? variables?.lead.id : undefined;

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(TouchSensor, {
      activationConstraint: { delay: 200, tolerance: 6 },
    }),
  );

  const leadsById = new Map<string, Lead>();
  columns.forEach((c) => c.data?.items.forEach((l) => leadsById.set(l.id, l)));
  const currency =
    columns.find((c) => c.data?.items[0])?.data?.items[0]?.currency ?? "USD";
  const allowedTargets = new Set(active?.next_stages ?? []);

  function onDragStart(event: DragStartEvent) {
    setActive(leadsById.get(String(event.active.id)) ?? null);
  }

  function onDragEnd(event: DragEndEvent) {
    const lead = leadsById.get(String(event.active.id));
    const target = event.over ? String(event.over.id) : null;
    setActive(null);
    if (!lead || !target || !isStage(target) || target === lead.stage) return;
    if (!lead.next_stages.includes(target)) return;
    move(lead, target);
  }

  const failed = columns.find((c) => c.isError);

  return (
    <PageShell width="full">
      <PageHeader
        title="Pipeline"
        description="Drag a lead to its next stage, or use a card's menu to move it. Only valid next stages accept a drop."
        actions={
          canWrite && (
            <Button asChild>
              <Link href="/sales/leads?new=1">
                <Plus /> New lead
              </Link>
            </Button>
          )
        }
      />
      <ModuleNav moduleKey="sales" />

      {failed ? (
        <div className="rounded-xl border border-border bg-surface">
          <ErrorState
            error={failed.error}
            onRetry={() => columns.forEach((c) => void c.refetch())}
          />
        </div>
      ) : (
        <DndContext
          sensors={sensors}
          onDragStart={onDragStart}
          onDragEnd={onDragEnd}
          onDragCancel={() => setActive(null)}
        >
          <div className="scrollbar-thin -mx-4 overflow-x-auto px-4 pb-3 sm:-mx-6 sm:px-6 lg:-mx-8 lg:px-8">
            <div className="flex min-w-max gap-3 lg:min-w-0">
              {STAGES.map((stage, index) => {
                const query = columns[index];
                const summary = pipeline.data?.find((s) => s.stage === stage);
                const dragging = active !== null;
                const allowed = dragging && allowedTargets.has(stage);
                const origin = active?.stage === stage;
                return (
                  <BoardColumn
                    key={stage}
                    stage={stage}
                    count={summary?.count ?? query?.data?.total}
                    value={
                      summary
                        ? formatMoney(summary.value, currency, {
                            compact: true,
                          })
                        : undefined
                    }
                    leads={query?.data?.items}
                    total={query?.data?.total ?? 0}
                    loading={!query || query.isPending}
                    state={
                      !dragging
                        ? "idle"
                        : allowed
                          ? "allowed"
                          : origin
                            ? "origin"
                            : "blocked"
                    }
                  >
                    {query?.data?.items.map((lead) => (
                      <DraggableLead
                        key={lead.id}
                        lead={lead}
                        canWrite={canWrite}
                        moving={movingId === lead.id}
                        hidden={active?.id === lead.id}
                        onMove={move}
                      />
                    ))}
                  </BoardColumn>
                );
              })}
            </div>
          </div>
          <DragOverlay dropAnimation={null}>
            {active ? <LeadCard lead={active} overlay /> : null}
          </DragOverlay>
        </DndContext>
      )}
      <p className="mt-2 flex items-center gap-1.5 text-xs text-muted-foreground">
        <Info className="size-3.5" aria-hidden="true" />
        Keyboard: open a card&apos;s menu (Tab to its button, then Enter) and
        choose &ldquo;Move to…&rdquo;. Won is final and asks for confirmation.
      </p>
      {dialog}
    </PageShell>
  );
}

function BoardColumn({
  stage,
  count,
  value,
  leads,
  total,
  loading,
  state,
  children,
}: {
  stage: LeadStage;
  count: number | undefined;
  value: string | undefined;
  leads: Lead[] | undefined;
  total: number;
  loading: boolean;
  state: "idle" | "allowed" | "origin" | "blocked";
  children: React.ReactNode;
}) {
  const { setNodeRef, isOver } = useDroppable({
    id: stage,
    disabled: state === "blocked" || state === "origin",
  });
  return (
    <section
      ref={setNodeRef}
      aria-label={`${STAGE_LABELS[stage]} stage`}
      className={cn(
        "flex w-[272px] shrink-0 flex-col rounded-xl border bg-surface-muted/60 transition-[opacity,border-color,background-color] lg:w-auto lg:min-w-0 lg:flex-1",
        state === "blocked" ? "border-border opacity-40" : "border-border",
        state === "allowed" &&
          "border-dashed border-primary/50 bg-primary-soft/30",
        state === "allowed" &&
          isOver &&
          "border-solid border-primary bg-primary-soft/60",
      )}
    >
      <header className="flex items-start justify-between gap-2 px-3 pt-3 pb-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <StatusBadge status={stage} />
            <span className="tabular text-xs font-semibold text-muted-foreground">
              {count === undefined ? "–" : formatNumber(count)}
            </span>
          </div>
          <p className="mt-1 truncate text-[11.5px] text-muted-foreground">
            {STAGE_DESCRIPTIONS[stage]}
          </p>
        </div>
        <span className="tabular shrink-0 text-[13px] font-semibold">
          {value ?? ""}
        </span>
      </header>
      <div className="flex min-h-24 flex-1 flex-col gap-2 px-2 pb-2">
        {loading ? (
          Array.from({ length: 3 }, (_, i) => (
            <Skeleton key={i} className="h-[84px] rounded-lg" />
          ))
        ) : leads && leads.length === 0 ? (
          <p className="rounded-lg border border-dashed border-border px-3 py-6 text-center text-xs text-muted-foreground">
            {state === "allowed" ? "Drop here" : "No leads"}
          </p>
        ) : (
          children
        )}
        {total > (leads?.length ?? 0) && (
          <Link
            href={`/sales/leads?stage=${stage}`}
            className="px-1 py-1 text-center text-xs font-medium text-primary hover:underline"
          >
            Showing {leads?.length} of {formatNumber(total)} · view all
          </Link>
        )}
      </div>
    </section>
  );
}

function DraggableLead({
  lead,
  canWrite,
  moving,
  hidden,
  onMove,
}: {
  lead: Lead;
  canWrite: boolean;
  moving: boolean;
  hidden: boolean;
  onMove: (lead: Lead, stage: LeadStage) => void;
}) {
  const draggable = canWrite && lead.next_stages.length > 0 && !moving;
  const { setNodeRef, listeners, attributes } = useDraggable({
    id: lead.id,
    disabled: !draggable,
  });
  // Keyboard users move cards via the menu; keep the card itself out of the drag keyboard path.
  const { tabIndex: _tabIndex, role: _role, ...dragAttributes } = attributes;
  return (
    <div
      ref={setNodeRef}
      {...listeners}
      {...dragAttributes}
      className={cn(
        draggable && "cursor-grab touch-manipulation",
        hidden && "opacity-30",
      )}
    >
      <LeadCard
        lead={lead}
        canWrite={canWrite}
        moving={moving}
        draggable={draggable}
        onMove={onMove}
      />
    </div>
  );
}

function LeadCard({
  lead,
  canWrite = false,
  moving = false,
  draggable = false,
  overlay = false,
  onMove,
}: {
  lead: Lead;
  canWrite?: boolean;
  moving?: boolean;
  draggable?: boolean;
  overlay?: boolean;
  onMove?: (lead: Lead, stage: LeadStage) => void;
}) {
  const targets = lead.next_stages.filter(isStage);
  return (
    <article
      className={cn(
        "group relative rounded-lg border border-border bg-surface p-3 shadow-sm transition-shadow hover:border-border-strong",
        overlay && "rotate-1 cursor-grabbing shadow-lg",
        moving && "opacity-60",
      )}
    >
      <div className="flex items-start gap-1.5">
        {draggable && (
          <GripVertical
            className="mt-0.5 -ml-1 size-3.5 shrink-0 text-border-strong"
            aria-hidden="true"
          />
        )}
        <div className="min-w-0 flex-1">
          <Link
            href={`/sales/leads/${lead.id}`}
            className="line-clamp-2 text-[13px] leading-snug font-medium hover:underline"
            draggable={false}
          >
            {lead.title}
          </Link>
          <p className="mt-0.5 truncate text-xs text-muted-foreground">
            {lead.customer_name ?? "No customer linked"}
          </p>
        </div>
        {!overlay && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                onPointerDown={(e) => e.stopPropagation()}
                className="-mt-1 -mr-1 shrink-0 rounded-md p-1 text-muted-foreground hover:bg-surface-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring"
                aria-label={`Actions for ${lead.title}`}
              >
                {moving ? (
                  <Spinner label="Moving lead" />
                ) : (
                  <MoreHorizontal className="size-4" />
                )}
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent className="w-52">
              {canWrite && (
                <>
                  <DropdownMenuLabel>Move to…</DropdownMenuLabel>
                  {targets.length === 0 ? (
                    <DropdownMenuItem disabled>
                      No further stages
                    </DropdownMenuItem>
                  ) : (
                    targets.map((stage) => (
                      <DropdownMenuItem
                        key={stage}
                        disabled={moving}
                        onSelect={() => onMove?.(lead, stage)}
                      >
                        <ArrowRightLeft /> {STAGE_LABELS[stage]}
                      </DropdownMenuItem>
                    ))
                  )}
                  <DropdownMenuSeparator />
                </>
              )}
              <DropdownMenuItem asChild>
                <Link href={`/sales/leads/${lead.id}`}>
                  <SquareArrowOutUpRight /> Open lead
                </Link>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </div>
      <div className="mt-2.5 flex items-center justify-between gap-2">
        <span className="flex min-w-0 items-center gap-1.5">
          <span className="tabular text-[13px] font-semibold">
            {lead.estimated_value ? (
              formatMoney(lead.estimated_value, lead.currency, {
                compact: true,
              })
            ) : (
              <span className="font-normal text-muted-foreground">
                No value
              </span>
            )}
          </span>
          {lead.source === "pi" && <LeadSourceBadge source="pi" compact />}
        </span>
        <time
          dateTime={lead.updated_at}
          className="shrink-0 text-[11.5px] text-muted-foreground"
        >
          {relativeTime(lead.updated_at)}
        </time>
      </div>
    </article>
  );
}
