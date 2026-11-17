"use client";

import { Bot, Check, CircleAlert, LogOut } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/display";
import { Notice } from "@/components/app/states";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { ApiError } from "@/services/api-client";
import {
  BOT_STATUS_LABELS,
  BOT_STEPS,
  meetingIntelService,
  type MeetingDetail as Detail,
} from "../meeting-intel-service";

/**
 * Where pi is in a Zoom, Meet or Teams call. pi joins as "pi (AI) - Workzap notetaker", so everyone
 * in the call can see an AI is there; the host can also remove it from the call. This card shows the
 * steps (sent, joining, waiting to be let in, listening, finished) and lets a person take pi out at
 * once. It asks the server for the state every few seconds only while pi is still in or on its way
 * to the call. pi listens and writes the transcript; it does not speak in a call yet.
 */
const REFUSED: Record<string, string> = {
  MEETING_BOT_NOT_ACTIVE: "pi is not in this call any more.",
  BOT_PROVIDER_UNREACHABLE:
    "The meeting bot service could not be reached. Try again in a moment.",
};

export function MeetingBotCard({ meeting }: { meeting: Detail }) {
  const key = ["pi", "meeting-intel", meeting.id, "bot"];
  const query = useScopedQuery(key, () => meetingIntelService.bot(meeting.id), {
    refetchInterval: (q) => (q.state.data?.bot?.active ? 5_000 : false),
  });
  const leave = useScopedMutation(
    () => meetingIntelService.leaveBot(meeting.id),
    {
      invalidate: [key, ["pi", "meeting-intel", meeting.id]],
      toastErrors: false,
    },
  );
  const bot = query.data?.bot;
  if (!bot) return null;
  const step = BOT_STEPS.indexOf(
    (bot.status === "in_call"
      ? "recording"
      : bot.status === "ended"
        ? "done"
        : bot.status) as (typeof BOT_STEPS)[number],
  );
  const stopped = bot.status === "failed" || bot.status === "denied";
  const failure =
    leave.error instanceof ApiError
      ? (REFUSED[leave.error.code ?? ""] ?? "Could not do that. Try again.")
      : leave.error
        ? "Could not do that. Try again."
        : "";
  return (
    <Card>
      <CardBody className="space-y-3">
        <h2 className="flex items-center gap-2 text-sm font-semibold">
          <Bot className="size-4" aria-hidden /> pi in this call
        </h2>
        <p
          role="status"
          aria-live="polite"
          className="flex items-center gap-2 text-sm font-medium"
        >
          {stopped ? (
            <CircleAlert className="size-4 text-danger" aria-hidden />
          ) : bot.active ? (
            <span
              className={`size-2 rounded-full bg-primary ${bot.status === "recording" ? "animate-pulse" : ""}`}
              aria-hidden
            />
          ) : (
            <Check className="size-4 text-success" aria-hidden />
          )}
          {BOT_STATUS_LABELS[bot.status] ?? bot.status}
        </p>
        {!stopped && (
          <ol
            className="grid grid-cols-5 gap-1"
            aria-label="Progress of pi joining the call"
          >
            {BOT_STEPS.map((s, i) => (
              <li
                key={s}
                aria-current={i === step ? "step" : undefined}
                className={`h-1.5 rounded-full ${i <= step ? "bg-primary" : "bg-surface-sunken"}`}
              />
            ))}
          </ol>
        )}
        {bot.status === "waiting" && (
          <Notice tone="info">
            Ask the host to admit &ldquo;{bot.bot_name}&rdquo; from the waiting
            room.
          </Notice>
        )}
        {bot.status === "failed" && (
          <Notice tone="danger">
            pi could not stay in the call
            {bot.sub_code ? ` (${bot.sub_code.replace(/_/g, " ")})` : ""}. Check
            the link and send pi again.
          </Notice>
        )}
        <p className="text-xs text-muted-foreground">
          pi joins as an AI notetaker that everyone in the call can see, and
          only listens. The host can remove it at any time. What it hears is
          turned into a transcript; nothing goes to the customer&apos;s record
          until you approve it.
        </p>
        {failure && <Notice tone="warning">{failure}</Notice>}
        {bot.active && (
          <Button
            variant="secondary"
            loading={leave.isPending}
            disabled={leave.isPending}
            onClick={() => leave.mutate(undefined)}
          >
            <LogOut /> Take pi out of the call
          </Button>
        )}
      </CardBody>
    </Card>
  );
}
