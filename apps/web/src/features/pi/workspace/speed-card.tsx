"use client";

import { useState } from "react";
import { Timer } from "lucide-react";
import { Card, CardBody } from "@/components/ui/display";
import { NativeSelect } from "@/components/ui/input";
import { ErrorState } from "@/components/app/states";
import { useScopedQuery } from "@/hooks/use-scoped";
import { piSpeedService, type Spread } from "../speed-service";

const STAGES: [string, string, string][] = [
  [
    "waiting_for_more_messages",
    "Waiting for the customer to finish",
    "From their message being saved until pi starts. Includes the pause that lets a burst of messages count as one.",
  ],
  ["thinking", "pi thinking", "Reading the chat and writing the reply."],
  [
    "queue_to_sender",
    "Reply waiting for a worker",
    "From the reply being ready until a worker picks it up to send.",
  ],
  [
    "send_checks",
    "Checks before sending",
    "Plan, permissions and the chat's state, just before the WhatsApp call.",
  ],
  ["whatsapp_call", "The WhatsApp call", "The call to WhatsApp itself."],
  [
    "delivered_after_sent",
    "WhatsApp delivering",
    "From sent until WhatsApp says it reached the phone.",
  ],
];

function secs(value: number | undefined): string {
  if (value === undefined) return "-";
  return value < 10 ? `${value.toFixed(1)} s` : `${Math.round(value)} s`;
}

function ms(value: number | undefined): string {
  if (value === undefined) return "-";
  return value < 1000
    ? `${Math.round(value)} ms`
    : `${(value / 1000).toFixed(1)} s`;
}

export function SpeedCard() {
  const [hours, setHours] = useState(24);
  const query = useScopedQuery(
    ["pi", "speed", hours],
    () => piSpeedService.get(hours),
    { refetchInterval: 60_000 },
  );
  const data = query.data;
  const stage = (id: string): Spread | null =>
    data?.replies.stages_s[id] ?? null;
  return (
    <Card>
      <CardBody className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="flex items-center gap-2 text-[15px] font-semibold">
            <Timer className="size-4" aria-hidden="true" /> Speed
          </h2>
          <label className="flex items-center gap-2 text-[13px] text-muted-foreground">
            Last
            <NativeSelect
              aria-label="Period"
              value={hours}
              onChange={(e) => setHours(Number(e.target.value))}
            >
              <option value={1}>1 hour</option>
              <option value={24}>24 hours</option>
              <option value={168}>7 days</option>
            </NativeSelect>
          </label>
        </div>
        {query.isError && !data ? (
          <ErrorState
            error={query.error}
            onRetry={() => void query.refetch()}
          />
        ) : !data ? (
          <div className="h-32 animate-pulse rounded-xl bg-surface-sunken" />
        ) : (
          <>
            <div>
              <p className="text-[13px] font-medium">
                From the customer&apos;s message to pi&apos;s reply leaving
              </p>
              {data.replies.total_s ? (
                <p className="mt-1 text-2xl font-semibold">
                  {secs(data.replies.total_s.p50)}{" "}
                  <span className="text-[13px] font-normal text-muted-foreground">
                    typical · {secs(data.replies.total_s.p90)} for the slowest 1
                    in 10 · {data.replies.with_send_timing} replies
                  </span>
                </p>
              ) : (
                <p className="mt-1 text-[13px] text-muted-foreground">
                  {data.replies.replies
                    ? "Replies in this period were sent before sending was timed. New ones will appear here."
                    : "No replies in this period yet."}
                </p>
              )}
            </div>
            <ul className="divide-y divide-border rounded-xl border border-border">
              {STAGES.map(([id, label, help]) => (
                <li
                  key={id}
                  className="flex flex-wrap items-center justify-between gap-2 px-3 py-2"
                >
                  <div className="min-w-0">
                    <p className="text-[13px] font-medium">{label}</p>
                    <p className="text-xs text-muted-foreground">{help}</p>
                  </div>
                  <p className="text-[13px] tabular-nums">
                    {secs(stage(id)?.p50)}{" "}
                    <span className="text-muted-foreground">
                      · slowest 1 in 10: {secs(stage(id)?.p90)}
                    </span>
                  </p>
                </li>
              ))}
            </ul>
            <div>
              <p className="text-[13px] font-medium">
                Live updates on your screen
              </p>
              {!data.live.enabled ? (
                <p className="mt-1 text-[13px] text-muted-foreground">
                  Off. The inbox checks for new messages every few seconds.
                </p>
              ) : !data.live.publishing ? (
                <p className="mt-1 text-[13px] text-muted-foreground">
                  On, but the worker is not sending signals yet, so the inbox
                  still checks every few seconds.
                </p>
              ) : data.live.samples === 0 ? (
                <p className="mt-1 text-[13px] text-muted-foreground">
                  On and working. Numbers appear after the first new message
                  arrives while the inbox is open.
                </p>
              ) : (
                <p className="mt-1 text-[13px]">
                  A new message shows on screen in{" "}
                  <strong>{ms(data.live.total_ms?.p50)}</strong> typically (
                  {ms(data.live.total_ms?.p90)} for the slowest 1 in 10), from{" "}
                  {data.live.samples} samples:{" "}
                  {ms(data.live.server_lag_ms?.p50)} on the server,{" "}
                  {ms(data.live.screen_ms?.p50)} on the screen.
                  {data.live.slowest_part
                    ? ` The slowest thing to reload is usually "${data.live.slowest_part}" (${ms(data.live.slowest_ms?.p50)}).`
                    : ""}
                </p>
              )}
            </div>
          </>
        )}
      </CardBody>
    </Card>
  );
}
