"use client";

import { useMemo } from "react";
import { Bell, CheckCheck } from "lucide-react";
import { formatDate, humanize } from "@/lib/format";
import { Button } from "@/components/ui/button";
import {
  Card,
  SegmentedList,
  SegmentedTrigger,
  Skeleton,
  Tabs,
} from "@/components/ui/display";
import {
  PageHeader,
  PageShell,
  RequirePermission,
} from "@/components/app/page";
import { Pagination } from "@/components/app/data-table";
import { FilterBar, FilterSelect } from "@/components/app/filters";
import { EmptyState, ErrorState } from "@/components/app/states";
import { NotificationRow } from "@/components/shell/notification-center";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useUrlState } from "@/hooks/use-url-state";
import { notificationsService, type Notification } from "./service";

const PAGE_SIZE = 25;

function localDay(iso: string) {
  const d = new Date(iso);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function dayHeading(day: string) {
  const today = localDay(new Date().toISOString());
  const y = new Date();
  y.setDate(y.getDate() - 1);
  if (day === today) return "Today";
  if (day === localDay(y.toISOString())) return "Yesterday";
  const [yy, mm, dd] = day.split("-").map(Number);
  const date = new Date(yy!, mm! - 1, dd!);
  return formatDate(
    date,
    date.getFullYear() === new Date().getFullYear()
      ? "EEEE, d MMMM"
      : "d MMMM yyyy",
  );
}

export function NotificationsPage() {
  return (
    <RequirePermission permission="notifications.read" area="notifications">
      <NotificationsContent />
    </RequirePermission>
  );
}

function NotificationsContent() {
  const [state, setState] = useUrlState({ view: "all", kind: "", page: "1" });
  const unreadOnly = state.view === "unread";
  const page = Math.max(1, Number(state.page) || 1);
  const list = useScopedQuery(
    ["notifications", "inbox", { page, unreadOnly }],
    () => notificationsService.list({ page, pageSize: PAGE_SIZE, unreadOnly }),
  );
  const unread = useScopedQuery(["notifications", "unread"], () =>
    notificationsService.unreadCount(),
  );
  const markAll = useScopedMutation(() => notificationsService.markRead(null), {
    invalidate: [["notifications"]],
    success: "All notifications marked as read",
  });
  const markOne = useScopedMutation(
    (id: string) => notificationsService.markRead([id]),
    { invalidate: [["notifications"]] },
  );

  const items = list.data?.items;
  const kindOptions = useMemo(() => {
    const counts = new Map<string, number>();
    for (const n of items ?? [])
      counts.set(n.kind, (counts.get(n.kind) ?? 0) + 1);
    if (state.kind && !counts.has(state.kind)) counts.set(state.kind, 0);
    return [...counts.entries()].sort().map(([kind, count]) => ({
      value: kind,
      label: kind === "pi" ? "PI" : humanize(kind),
      count,
    }));
  }, [items, state.kind]);
  const filtered = items?.filter((n) => !state.kind || n.kind === state.kind);
  const groups = useMemo(() => {
    const map = new Map<string, Notification[]>();
    for (const n of filtered ?? []) {
      const day = localDay(n.created_at);
      map.set(day, [...(map.get(day) ?? []), n]);
    }
    return [...map.entries()];
  }, [filtered]);
  const unreadCount = unread.data ?? 0;

  return (
    <PageShell width="default">
      <PageHeader
        title="Notifications"
        description="Handoffs, stock, billing and system alerts for this environment."
        actions={
          <Button
            variant="secondary"
            onClick={() => markAll.mutate(undefined)}
            disabled={unreadCount === 0}
            loading={markAll.isPending}
          >
            <CheckCheck /> Mark all read
          </Button>
        }
      />
      <FilterBar
        activeCount={state.kind ? 1 : 0}
        onClear={() => setState({ kind: "" })}
      >
        <Tabs
          value={unreadOnly ? "unread" : "all"}
          onValueChange={(v) => setState({ view: v })}
        >
          <SegmentedList aria-label="Show">
            <SegmentedTrigger value="all">All</SegmentedTrigger>
            <SegmentedTrigger value="unread">
              Unread
              {unreadCount > 0 && (
                <span className="tabular rounded-full bg-primary-soft px-1.5 text-[10.5px] font-semibold text-primary-soft-foreground">
                  {unreadCount}
                </span>
              )}
            </SegmentedTrigger>
          </SegmentedList>
        </Tabs>
        {kindOptions.length > 0 && (
          <FilterSelect
            label="Kind"
            value={state.kind}
            options={kindOptions}
            onChange={(v) => setState({ kind: v }, { resetPage: false })}
          />
        )}
      </FilterBar>

      {list.isPending ? (
        <Card className="space-y-1 p-2">
          {Array.from({ length: 6 }, (_, i) => (
            <div key={i} className="flex gap-3 px-2.5 py-2.5">
              <Skeleton className="size-7 rounded-full" />
              <div className="flex-1 space-y-1.5">
                <Skeleton className="h-3.5 w-2/3" />
                <Skeleton className="h-3 w-1/2" />
              </div>
            </div>
          ))}
        </Card>
      ) : list.isError ? (
        <Card>
          <ErrorState error={list.error} onRetry={() => void list.refetch()} />
        </Card>
      ) : groups.length === 0 ? (
        <Card>
          <EmptyState
            icon={Bell}
            title={
              state.kind
                ? "Nothing of this kind on this page"
                : unreadOnly
                  ? "You're all caught up"
                  : "No notifications yet"
            }
            description={
              state.kind
                ? "Clear the kind filter or look at another page."
                : unreadOnly
                  ? "Every notification has been read."
                  : "Handoffs, low stock and overdue invoices will show up here."
            }
            action={
              unreadOnly || state.kind ? (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setState({ view: "all", kind: "" })}
                >
                  Show all notifications
                </Button>
              ) : undefined
            }
          />
        </Card>
      ) : (
        <div className="space-y-4">
          {groups.map(([day, rows]) => (
            <section key={day} aria-labelledby={`day-${day}`}>
              <h2
                id={`day-${day}`}
                className="mb-1.5 px-1 text-2xs font-semibold tracking-wide text-muted-foreground uppercase"
              >
                {dayHeading(day)}
              </h2>
              <Card className="p-1.5">
                <ul>
                  {rows.map((n) => (
                    <li key={n.id}>
                      <NotificationRow
                        n={n}
                        onOpen={() => !n.read && markOne.mutate(n.id)}
                      />
                    </li>
                  ))}
                </ul>
              </Card>
            </section>
          ))}
        </div>
      )}
      {list.data && (
        <Pagination
          page={page}
          pageSize={PAGE_SIZE}
          total={list.data.total}
          onPage={(p) => setState({ page: String(p) }, { resetPage: false })}
        />
      )}
    </PageShell>
  );
}
