"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Bell, CheckCheck, CircleAlert, Info } from "lucide-react";
import { cn } from "@/lib/utils";
import { relativeTime } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/display";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/overlays";
import { useSession } from "@/features/auth/session-provider";
import { notificationsService, type Notification } from "@/features/notifications/service";

export const SEVERITY_ICON = {
  info: { icon: Info, className: "text-info bg-info-soft" },
  warning: { icon: AlertTriangle, className: "text-warning bg-warning-soft" },
  critical: { icon: CircleAlert, className: "text-danger bg-danger-soft" },
} as const;

export function NotificationRow({ n, onOpen }: { n: Notification; onOpen?: () => void }) {
  const tone = SEVERITY_ICON[n.severity];
  const body = (
    <div className={cn("flex gap-3 rounded-md px-2.5 py-2.5 hover:bg-surface-muted", !n.read && "bg-primary-soft/40")}>
      <span className={cn("mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full", tone.className)}>
        <tone.icon className="size-3.5" aria-hidden="true" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-start gap-2">
          <span className={cn("min-w-0 flex-1 text-[13px] leading-snug", !n.read ? "font-semibold" : "font-medium")}>
            {n.title}
          </span>
          {!n.read && <span className="mt-1.5 size-2 shrink-0 rounded-full bg-primary" aria-label="Unread" />}
        </span>
        {n.body && <span className="mt-0.5 line-clamp-2 block text-xs text-muted-foreground">{n.body}</span>}
        <span className="mt-1 block text-2xs text-muted-foreground">{relativeTime(n.created_at)}</span>
      </span>
    </div>
  );
  return n.link ? (
    <Link href={n.link} onClick={onOpen} className="block">
      {body}
    </Link>
  ) : (
    body
  );
}

export function NotificationCenter() {
  const { scopeKey, can } = useSession();
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const enabled = can("notifications.read");
  const unread = useQuery({
    queryKey: [...scopeKey, "notifications", "unread"],
    queryFn: () => notificationsService.unreadCount(),
    enabled,
    refetchInterval: 60_000,
  });
  const list = useQuery({
    queryKey: [...scopeKey, "notifications", "recent"],
    queryFn: () => notificationsService.list({ pageSize: 8 }),
    enabled: enabled && open,
  });
  const markAll = useMutation({
    mutationFn: () => notificationsService.markRead(null),
    onSuccess: () => client.invalidateQueries({ queryKey: [...scopeKey, "notifications"] }),
  });
  if (!enabled) return null;
  const count = unread.data ?? 0;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="relative flex size-8 items-center justify-center rounded-md text-foreground-secondary hover:bg-surface-muted hover:text-foreground"
          aria-label={count ? `Notifications, ${count} unread` : "Notifications"}
        >
          <Bell className="size-4" aria-hidden="true" />
          {count > 0 && (
            <span className="tabular absolute top-0.5 right-0.5 min-w-4 rounded-full bg-pi px-1 text-center text-[10px] leading-4 font-bold text-white">
              {count > 9 ? "9+" : count}
            </span>
          )}
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[min(380px,calc(100vw-1.5rem))] p-0">
        <div className="flex items-center justify-between border-b border-border px-3.5 py-2.5">
          <p className="text-sm font-semibold">Notifications</p>
          <Button
            variant="ghost"
            size="xs"
            onClick={() => markAll.mutate()}
            disabled={count === 0 || markAll.isPending}
          >
            <CheckCheck /> Mark all read
          </Button>
        </div>
        <div className="scrollbar-thin max-h-[420px] overflow-y-auto p-1.5">
          {list.isPending ? (
            Array.from({ length: 4 }, (_, i) => (
              <div key={i} className="flex gap-3 px-2.5 py-2.5">
                <Skeleton className="size-7 rounded-full" />
                <div className="flex-1 space-y-1.5">
                  <Skeleton className="h-3 w-3/4" />
                  <Skeleton className="h-3 w-1/2" />
                </div>
              </div>
            ))
          ) : list.isError ? (
            <p className="px-3 py-6 text-center text-sm text-muted-foreground">Notifications could not be loaded.</p>
          ) : list.data.items.length === 0 ? (
            <div className="px-3 py-10 text-center">
              <Bell className="mx-auto size-6 text-border-strong" aria-hidden="true" />
              <p className="mt-2 text-sm font-medium">You're all caught up</p>
              <p className="text-xs text-muted-foreground">Handoffs, stock and billing alerts appear here.</p>
            </div>
          ) : (
            list.data.items.map((n) => <NotificationRow key={n.id} n={n} onOpen={() => setOpen(false)} />)
          )}
        </div>
        <Link
          href="/notifications"
          onClick={() => setOpen(false)}
          className="block border-t border-border px-3.5 py-2.5 text-center text-[13px] font-medium text-primary hover:bg-surface-muted"
        >
          View all notifications
        </Link>
      </PopoverContent>
    </Popover>
  );
}
