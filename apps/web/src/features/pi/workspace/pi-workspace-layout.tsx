"use client";

import { usePathname } from "next/navigation";
import { Bot } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge, Skeleton } from "@/components/ui/display";
import { Tooltip } from "@/components/ui/overlays";
import { ModuleNav, RequirePermission } from "@/components/app/page";
import { useScopedQuery } from "@/hooks/use-scoped";
import { piService } from "../service";
import type { PiOverview } from "../types";
import { piKeys } from "./lib";

/**
 * PI product workspace frame shared by every /pi route: identity band, live status and
 * the registry-driven PI sub-navigation. The inbox gets a full-height, full-width canvas.
 */
export function PiWorkspaceLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const fullBleed =
    pathname === "/pi/inbox" || pathname.startsWith("/pi/inbox/");
  return (
    <RequirePermission permission="pi.read" area="PI">
      <div
        className={cn(
          fullBleed && "flex h-[calc(100dvh-52px)] flex-col overflow-hidden",
        )}
      >
        <PiBand fullBleed={fullBleed} />
        {fullBleed ? (
          <div className="min-h-0 flex-1">{children}</div>
        ) : (
          children
        )}
      </div>
    </RequirePermission>
  );
}

function PiBand({ fullBleed }: { fullBleed: boolean }) {
  return (
    <div
      className={cn(
        "mx-auto w-full shrink-0 px-4 pt-4 sm:px-6 lg:px-8",
        fullBleed ? "max-w-none bg-surface" : "max-w-[1400px]",
      )}
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-pi-soft text-pi">
            <Bot className="size-5" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <p className="text-[15px] leading-tight font-semibold tracking-tight">
              PI
            </p>
            <p className="truncate text-xs text-muted-foreground">
              AI WhatsApp assistant
            </p>
          </div>
        </div>
        <div className="ml-auto">
          <PiStatusChip />
        </div>
      </div>
      <ModuleNav moduleKey="pi" className="mt-3 mb-0" />
    </div>
  );
}

const WHATSAPP: Record<
  string,
  {
    label: string;
    tone: "success" | "warning" | "danger" | "neutral";
    hint: string;
  }
> = {
  active: {
    label: "WhatsApp connected",
    tone: "success",
    hint: "Messages to your WhatsApp number reach PI.",
  },
  pending: {
    label: "WhatsApp pending",
    tone: "warning",
    hint: "The number is saved but not active yet. Finish setup in WhatsApp.",
  },
  disabled: {
    label: "WhatsApp paused",
    tone: "neutral",
    hint: "The number is disabled. Incoming messages are not processed.",
  },
  error: {
    label: "WhatsApp error",
    tone: "danger",
    hint: "The connection reported an error. Check WhatsApp settings.",
  },
  none: {
    label: "WhatsApp not connected",
    tone: "neutral",
    hint: "Connect a WhatsApp Business number to receive conversations.",
  },
};

function PiStatusChip() {
  const overview = useScopedQuery<PiOverview>(
    piKeys.overview,
    () => piService.overview(),
    {
      refetchInterval: 60_000,
      retry: false,
    },
  );
  if (overview.isPending) return <Skeleton className="h-6 w-52 rounded-full" />;
  if (overview.isError || !overview.data) {
    return (
      <Badge tone="neutral" dot>
        Status unavailable
      </Badge>
    );
  }
  const { auto_reply_enabled: autoReply, whatsapp } = overview.data;
  const wa = WHATSAPP[whatsapp?.status ?? "none"] ?? WHATSAPP.none!;
  return (
    <div
      className="flex flex-wrap items-center justify-end gap-1.5"
      aria-label="PI status"
    >
      <Tooltip
        content={
          autoReply
            ? "PI replies to customers automatically."
            : "Automatic replies are paused. PI isn't answering customers."
        }
      >
        <span
          tabIndex={0}
          className="rounded-full focus-visible:outline-2 focus-visible:outline-ring"
        >
          <Badge tone={autoReply ? "pi" : "warning"} dot>
            {autoReply ? "Auto-reply on" : "Auto-reply paused"}
          </Badge>
        </span>
      </Tooltip>
      <Tooltip
        content={
          whatsapp?.display_phone_number
            ? `${whatsapp.display_phone_number} · ${wa.hint}`
            : wa.hint
        }
      >
        <span
          tabIndex={0}
          className="rounded-full focus-visible:outline-2 focus-visible:outline-ring"
        >
          <Badge tone={wa.tone} dot>
            {wa.label}
          </Badge>
        </span>
      </Tooltip>
    </div>
  );
}
