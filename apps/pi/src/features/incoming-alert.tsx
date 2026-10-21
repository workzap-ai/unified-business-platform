"use client";

/**
 * New customer message alert for the team app: polls the newest conversations (every
 * 5 s on the inbox, 20 s elsewhere, 30 s while the tab is hidden), plays the incoming
 * tone once per new batch and badges the tab title while hidden. Not used by the
 * customer portal.
 */
import { useQuery } from "@tanstack/react-query";
import { Volume2, VolumeX } from "lucide-react";
import { usePathname } from "next/navigation";

import { cn } from "@/components/ui";
import { get } from "@/lib/api";
import {
  playIncomingTone,
  useIncomingSoundSetting,
  useIncomingTone,
  useUnreadTitleBadge,
} from "@/lib/incoming-sound";
import { useBusinessKey, useCan, useSession } from "@/lib/session";
import type { Conversation, Page } from "@/lib/types";

export function IncomingMessageAlert() {
  const session = useSession();
  const can = useCan();
  const key = useBusinessKey();
  const pathname = usePathname();
  const onInbox = pathname.startsWith("/inbox");
  const business = session.data?.business;
  const newest = useQuery({
    queryKey: key(["conversations", "incoming"]),
    queryFn: () =>
      get<Page<Conversation>>("/pi/conversations", { page: 1, page_size: 25 }),
    enabled: Boolean(business) && can("pi.read"),
    refetchInterval: () =>
      document.hidden ? 30_000 : onInbox ? 5_000 : 20_000,
    refetchIntervalInBackground: true,
    retry: false,
  });
  const rows = newest.data?.items;
  useIncomingTone(
    rows,
    business ? `${business.id}:${business.environment}` : "none",
  );
  useUnreadTitleBadge(rows?.filter((c) => c.unread_count > 0).length ?? 0);
  return null;
}

/** Sound on/off for new customer messages (remembered in this browser). */
export function IncomingSoundToggle({ className }: { className?: string }) {
  const [on, setOn] = useIncomingSoundSetting();
  const label = on
    ? "Message sound on. Tap to mute"
    : "Message sound off. Tap to turn on";
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      aria-pressed={on}
      onClick={() => {
        setOn(!on);
        if (!on) playIncomingTone(true);
      }}
      className={cn(
        "inline-flex size-9 shrink-0 items-center justify-center rounded-full border border-border text-foreground-secondary hover:bg-surface-muted hover:text-foreground",
        className,
      )}
    >
      {on ? (
        <Volume2 className="size-4" aria-hidden />
      ) : (
        <VolumeX className="size-4" aria-hidden />
      )}
    </button>
  );
}
