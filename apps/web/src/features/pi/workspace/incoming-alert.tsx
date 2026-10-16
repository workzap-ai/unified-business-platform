"use client";

import { usePathname } from "next/navigation";
import { Volume2, VolumeX } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tooltip } from "@/components/ui/overlays";
import { useSession } from "@/features/auth/session-provider";
import { useNavItemAvailable } from "@/features/navigation/hooks";
import { useScopedQuery } from "@/hooks/use-scoped";
import {
  playIncomingTone,
  useIncomingSoundSetting,
  useIncomingTone,
  useUnreadTitleBadge,
} from "@/hooks/use-incoming-sound";
import { piService } from "../service";

/**
 * App-wide watcher for new customer messages: polls the newest conversations (every
 * 5 s on the inbox, 20 s elsewhere, 30 s while the tab is hidden), plays the incoming
 * tone once per new batch and badges the tab title while hidden. Renders nothing.
 */
export function IncomingMessageAlert() {
  const { can, scopeKey } = useSession();
  const pathname = usePathname();
  const available = useNavItemAvailable("pi");
  const onInbox = pathname.startsWith("/pi/inbox");
  const newest = useScopedQuery(
    ["pi", "conversations", "incoming"],
    () => piService.conversations({ page: 1, page_size: 25 }),
    {
      enabled: available === true && can("pi.read"),
      refetchInterval: () =>
        document.hidden ? 30_000 : onInbox ? 5_000 : 20_000,
      refetchIntervalInBackground: true,
      retry: false,
    },
  );
  const rows = newest.data?.items;
  useIncomingTone(rows, scopeKey.join(":"));
  useUnreadTitleBadge(rows?.filter((c) => c.unread_count > 0).length ?? 0);
  return null;
}

/** Sound on/off for new customer messages (remembered in this browser). */
export function IncomingSoundToggle() {
  const [on, setOn] = useIncomingSoundSetting();
  const label = on
    ? "Message sound on: click to mute"
    : "Message sound off: click to turn on";
  return (
    <Tooltip content={label}>
      <Button
        variant="ghost"
        size="icon-sm"
        aria-label={label}
        aria-pressed={on}
        onClick={() => {
          setOn(!on);
          if (!on) playIncomingTone(true);
        }}
      >
        {on ? <Volume2 /> : <VolumeX />}
      </Button>
    </Tooltip>
  );
}
