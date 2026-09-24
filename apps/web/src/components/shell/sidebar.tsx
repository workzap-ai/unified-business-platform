"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import {
  restrictToParentElement,
  restrictToVerticalAxis,
} from "@dnd-kit/modifiers";
import { CSS } from "@dnd-kit/utilities";
import {
  ArrowDown,
  ArrowUp,
  ChevronDown,
  GripVertical,
  PanelLeftClose,
  PanelLeftOpen,
  RotateCcw,
  Search,
  SlidersHorizontal,
} from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { Kbd } from "@/components/ui/controls";
import { Skeleton } from "@/components/ui/display";
import { Tooltip } from "@/components/ui/overlays";
import {
  findActive,
  useNavOrderMutation,
  useNavigation,
} from "@/features/navigation/hooks";
import { NavIcon } from "@/features/navigation/icons";
import type { NavItem, NavSection } from "@/features/navigation/types";
import { errorMessage } from "@/services/api-client";
import { useCommandMenu } from "./command-menu";
import { WorkspaceSwitcher } from "./workspace-switcher";

export function Sidebar({
  collapsed = false,
  onToggleCollapsed,
  onNavigate,
  variant = "desktop",
}: {
  collapsed?: boolean;
  onToggleCollapsed?: () => void;
  onNavigate?: () => void;
  variant?: "desktop" | "mobile";
}) {
  const pathname = usePathname();
  const navigation = useNavigation();
  const active = findActive(navigation.data, pathname);
  const { open: openCommand } = useCommandMenu();
  const [adminOpen, setAdminOpen] = useState(true);
  const main = navigation.data?.sections.find((s) => s.key === "main");
  const admin = navigation.data?.sections.find((s) => s.key === "admin");
  const compact = collapsed && variant === "desktop";

  return (
    <div className="flex h-full min-h-0 flex-col bg-sidebar text-sidebar-foreground">
      <div className={cn("shrink-0 px-3 pt-3", compact && "px-2")}>
        <WorkspaceSwitcher compact={compact} />
        <Tooltip
          content="Search and commands (Ctrl K)"
          side="right"
          disabled={!compact}
        >
          <button
            type="button"
            onClick={() => {
              onNavigate?.();
              openCommand();
            }}
            className={cn(
              "mt-3 flex h-8 w-full items-center gap-2 rounded-md border border-sidebar-border bg-sidebar-elevated px-2.5 text-[13px] text-sidebar-muted transition-colors hover:border-sidebar-muted/40 hover:text-sidebar-foreground",
              compact && "justify-center px-0",
            )}
            aria-label="Search and commands"
          >
            <Search className="size-3.5 shrink-0" aria-hidden="true" />
            {!compact && (
              <>
                <span className="flex-1 text-left">Search…</span>
                <Kbd className="border-sidebar-border bg-sidebar text-sidebar-muted">
                  Ctrl K
                </Kbd>
              </>
            )}
          </button>
        </Tooltip>
      </div>

      <div className="sidebar-scroll mt-3 min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        {navigation.isPending ? (
          <NavSkeleton compact={compact} />
        ) : navigation.isError ? (
          <div className="px-2 py-3 text-xs text-sidebar-muted">
            Navigation could not be loaded.{" "}
            <button
              className="underline"
              onClick={() => void navigation.refetch()}
            >
              Retry
            </button>
          </div>
        ) : (
          <>
            {main && (
              <MainSection
                section={main}
                activeKey={active?.item.key}
                compact={compact}
                onNavigate={onNavigate}
              />
            )}
            {admin && admin.items.length > 0 && (
              <nav aria-label="Administration" className="mt-5">
                {!compact ? (
                  <button
                    type="button"
                    onClick={() => setAdminOpen((v) => !v)}
                    aria-expanded={adminOpen}
                    className="mb-1 flex w-full items-center gap-1 px-2 text-2xs font-semibold tracking-wider text-sidebar-muted uppercase hover:text-sidebar-foreground"
                  >
                    Admin
                    <ChevronDown
                      className={cn(
                        "size-3 transition-transform",
                        !adminOpen && "-rotate-90",
                      )}
                      aria-hidden="true"
                    />
                  </button>
                ) : (
                  <div className="mx-2 mb-2 h-px bg-sidebar-border" />
                )}
                {(adminOpen || compact) && (
                  <ul className="space-y-px">
                    {admin.items.map((item) => (
                      <li key={item.key}>
                        <NavLink
                          item={item}
                          active={active?.item.key === item.key}
                          compact={compact}
                          onNavigate={onNavigate}
                        />
                      </li>
                    ))}
                  </ul>
                )}
              </nav>
            )}
          </>
        )}
      </div>

      {variant === "desktop" && onToggleCollapsed && (
        <div className="shrink-0 border-t border-sidebar-border p-2">
          <Tooltip
            content={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            side="right"
          >
            <button
              type="button"
              onClick={onToggleCollapsed}
              className={cn(
                "flex h-8 w-full items-center gap-2 rounded-md px-2 text-[13px] text-sidebar-muted hover:bg-sidebar-hover hover:text-sidebar-foreground",
                compact && "justify-center",
              )}
              aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            >
              {collapsed ? (
                <PanelLeftOpen className="size-4" aria-hidden="true" />
              ) : (
                <>
                  <PanelLeftClose className="size-4" aria-hidden="true" />
                  Collapse
                </>
              )}
            </button>
          </Tooltip>
        </div>
      )}
    </div>
  );
}

function NavSkeleton({ compact }: { compact: boolean }) {
  return (
    <div className="space-y-1.5 px-1" aria-label="Loading navigation">
      {Array.from({ length: 12 }, (_, i) => (
        <div key={i} className="flex h-8 items-center gap-2.5 px-1.5">
          <Skeleton className="size-4 bg-sidebar-hover" />
          {!compact && (
            <Skeleton
              className="h-3 flex-1 bg-sidebar-hover"
              style={{ maxWidth: 80 + ((i * 37) % 60) }}
            />
          )}
        </div>
      ))}
    </div>
  );
}

function MainSection({
  section,
  activeKey,
  compact,
  onNavigate,
}: {
  section: NavSection;
  activeKey?: string;
  compact: boolean;
  onNavigate?: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const mutation = useNavOrderMutation();
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  );
  const keys = section.items.map((i) => i.key);

  function save(order: string[]) {
    mutation.mutate(
      { section: "main", order },
      {
        onSuccess: () => toast.success("Sidebar order saved"),
        onError: (error) =>
          toast.error(errorMessage(error, "Sidebar order could not be saved.")),
      },
    );
  }

  function move(key: string, delta: -1 | 1) {
    const index = keys.indexOf(key);
    const target = index + delta;
    if (index < 0 || target < 0 || target >= keys.length) return;
    save(arrayMove(keys, index, target));
  }

  function onDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    save(
      arrayMove(
        keys,
        keys.indexOf(String(active.id)),
        keys.indexOf(String(over.id)),
      ),
    );
  }

  return (
    <nav aria-label="Primary">
      {!compact && (
        <div className="group/section mb-1 flex h-6 items-center justify-between px-2">
          <span className="text-2xs font-semibold tracking-wider text-sidebar-muted uppercase">
            {editing ? "Drag to reorder" : "Workspace"}
          </span>
          {editing ? (
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() =>
                  mutation.mutate(
                    { section: "main", order: null },
                    {
                      onSuccess: () =>
                        toast.success("Sidebar reset to the default order"),
                    },
                  )
                }
                disabled={!section.customized || mutation.isPending}
                className="flex items-center gap-1 rounded px-1.5 py-0.5 text-2xs font-medium text-sidebar-muted hover:bg-sidebar-hover hover:text-sidebar-foreground disabled:opacity-40"
              >
                <RotateCcw className="size-3" aria-hidden="true" />
                Reset
              </button>
              <button
                type="button"
                onClick={() => setEditing(false)}
                className="rounded bg-sidebar-active px-2 py-0.5 text-2xs font-semibold text-sidebar-active-foreground"
              >
                Done
              </button>
            </div>
          ) : (
            <Tooltip content="Customize order" side="right">
              <button
                type="button"
                onClick={() => setEditing(true)}
                className="rounded p-1 text-sidebar-muted opacity-70 transition-opacity group-hover/section:opacity-100 hover:bg-sidebar-hover hover:text-sidebar-foreground focus-visible:opacity-100"
                aria-label="Customize sidebar order"
              >
                <SlidersHorizontal className="size-3.5" aria-hidden="true" />
              </button>
            </Tooltip>
          )}
        </div>
      )}
      {editing && !compact ? (
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          modifiers={[restrictToVerticalAxis, restrictToParentElement]}
          onDragEnd={onDragEnd}
          accessibility={{
            screenReaderInstructions: {
              draggable:
                "Press space or enter to pick up a navigation item. Use the arrow keys to move it, then press space or enter to drop it, or escape to cancel.",
            },
          }}
        >
          <SortableContext items={keys} strategy={verticalListSortingStrategy}>
            <ul className="space-y-px" aria-label="Reorder navigation items">
              {section.items.map((item, index) => (
                <SortableNavItem
                  key={item.key}
                  item={item}
                  first={index === 0}
                  last={index === section.items.length - 1}
                  onMove={(delta) => move(item.key, delta)}
                />
              ))}
            </ul>
          </SortableContext>
        </DndContext>
      ) : (
        <ul className="space-y-px">
          {section.items.map((item) => (
            <li key={item.key}>
              <NavLink
                item={item}
                active={activeKey === item.key}
                compact={compact}
                onNavigate={onNavigate}
              />
            </li>
          ))}
        </ul>
      )}
    </nav>
  );
}

function NavLink({
  item,
  active,
  compact,
  onNavigate,
}: {
  item: NavItem;
  active: boolean;
  compact: boolean;
  onNavigate?: () => void;
}) {
  const product = item.type === "product";
  return (
    <Tooltip
      content={
        <span>
          {item.label}
          {item.badge ? ` · ${item.badge}` : ""}
        </span>
      }
      side="right"
      disabled={!compact}
    >
      <Link
        href={item.route}
        onClick={onNavigate}
        aria-current={active ? "page" : undefined}
        data-nav-key={item.key}
        className={cn(
          "group relative flex h-8 items-center gap-2.5 rounded-md px-2 text-[13.5px] font-medium transition-colors",
          active
            ? "bg-sidebar-active text-sidebar-active-foreground"
            : "text-sidebar-foreground/85 hover:bg-sidebar-hover hover:text-sidebar-foreground",
          compact && "justify-center px-0",
        )}
      >
        <span className="relative flex size-4 shrink-0 items-center justify-center">
          <NavIcon
            name={item.icon}
            className={cn(
              "size-4",
              product && !active && "text-pi",
              !product &&
                !active &&
                "text-sidebar-muted group-hover:text-sidebar-foreground",
            )}
          />
          {compact && item.badge ? (
            <span className="absolute -top-1 -right-1.5 size-2 rounded-full bg-pi ring-2 ring-sidebar" />
          ) : null}
        </span>
        {!compact && (
          <>
            <span className="min-w-0 flex-1 truncate">{item.label}</span>
            {product && (
              <span
                className={cn(
                  "rounded px-1 text-[9.5px] font-bold tracking-wide uppercase",
                  active
                    ? "bg-pi-soft text-pi-soft-foreground"
                    : "bg-pi/15 text-pi",
                )}
              >
                AI
              </span>
            )}
            {item.badge ? (
              <span
                className={cn(
                  "tabular min-w-5 rounded-full px-1.5 text-center text-[11px] leading-[18px] font-semibold",
                  active
                    ? "bg-sidebar-active-foreground/10"
                    : "bg-sidebar-hover text-sidebar-foreground",
                )}
              >
                {item.badge > 99 ? "99+" : item.badge}
              </span>
            ) : null}
          </>
        )}
      </Link>
    </Tooltip>
  );
}

function SortableNavItem({
  item,
  first,
  last,
  onMove,
}: {
  item: NavItem;
  first: boolean;
  last: boolean;
  onMove: (delta: -1 | 1) => void;
}) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({
    id: item.key,
  });
  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={cn(
        "relative flex h-8 items-center gap-1.5 rounded-md border border-dashed border-sidebar-border bg-sidebar-elevated pr-1 pl-1 text-[13.5px] font-medium",
        isDragging &&
          "z-10 border-solid border-sidebar-muted/60 bg-sidebar-hover shadow-lg",
      )}
      data-sortable-key={item.key}
    >
      <button
        type="button"
        className="flex size-6 cursor-grab items-center justify-center rounded text-sidebar-muted hover:bg-sidebar-hover hover:text-sidebar-foreground active:cursor-grabbing"
        aria-label={`Drag ${item.label}`}
        {...attributes}
        {...listeners}
      >
        <GripVertical className="size-3.5" aria-hidden="true" />
      </button>
      <NavIcon
        name={item.icon}
        className={cn(
          "size-4 shrink-0",
          item.type === "product" ? "text-pi" : "text-sidebar-muted",
        )}
      />
      <span className="min-w-0 flex-1 truncate">{item.label}</span>
      <button
        type="button"
        onClick={() => onMove(-1)}
        disabled={first}
        className="flex size-6 items-center justify-center rounded text-sidebar-muted hover:bg-sidebar-hover hover:text-sidebar-foreground disabled:opacity-30"
        aria-label={`Move ${item.label} up`}
      >
        <ArrowUp className="size-3.5" aria-hidden="true" />
      </button>
      <button
        type="button"
        onClick={() => onMove(1)}
        disabled={last}
        className="flex size-6 items-center justify-center rounded text-sidebar-muted hover:bg-sidebar-hover hover:text-sidebar-foreground disabled:opacity-30"
        aria-label={`Move ${item.label} down`}
      >
        <ArrowDown className="size-3.5" aria-hidden="true" />
      </button>
    </li>
  );
}
