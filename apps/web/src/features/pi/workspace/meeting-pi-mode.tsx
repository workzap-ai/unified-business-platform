"use client";

import { Bot } from "lucide-react";
import { Card, CardBody } from "@/components/ui/display";
import { NativeSelect } from "@/components/ui/input";
import { Label } from "@/components/ui/controls";
import { Notice } from "@/components/app/states";
import { useScopedMutation } from "@/hooks/use-scoped";
import { ApiError } from "@/services/api-client";
import {
  meetingIntelService,
  type MeetingDetail as Detail,
  type PiMode,
} from "../meeting-intel-service";

/**
 * What pi does in this meeting. "Suggest to me" is the "pi suggests" card (only you see it). "Talk
 * with the person on the link" lets pi speak, as an AI, with whoever opens the meeting link: it
 * asks one question at a time and listens. Choosing anything else mutes pi at once.
 */
const LABELS: Record<PiMode, string> = {
  off: "Off",
  listen: "Suggest to me (pi says nothing to the customer)",
  speak: "Talk with the person on the link (as an AI)",
};

export function MeetingPiMode({ meeting }: { meeting: Detail }) {
  const set = useScopedMutation(
    (mode: PiMode) => meetingIntelService.setPiMode(meeting.id, mode),
    {
      invalidate: [["pi", "meeting-intel", meeting.id]],
      toastErrors: false,
    },
  );
  const refused =
    set.error instanceof ApiError && set.error.code === "MEETING_VOICE_OFF"
      ? "pi talking in meetings is not switched on for this workspace yet."
      : set.error
        ? "Could not change this. Try again."
        : "";
  return (
    <Card>
      <CardBody className="space-y-2">
        <h2 className="flex items-center gap-2 text-sm font-semibold">
          <Bot className="size-4" aria-hidden /> What pi does in this meeting
        </h2>
        <div className="max-w-md">
          <Label htmlFor="pi-mode">pi</Label>
          <NativeSelect
            id="pi-mode"
            value={meeting.pi_mode}
            disabled={set.isPending}
            onChange={(e) => set.mutate(e.target.value as PiMode)}
          >
            {(Object.keys(LABELS) as PiMode[]).map((m) => (
              <option key={m} value={m}>
                {LABELS[m]}
              </option>
            ))}
          </NativeSelect>
        </div>
        {meeting.pi_mode === "speak" && (
          <p className="text-xs text-muted-foreground">
            pi will talk with the person who opens the meeting link. It says it
            is an AI first, asks one question at a time, never quotes a price,
            and stops the moment you choose another option. One person at a
            time: create the link for one guest.
          </p>
        )}
        {refused && <Notice tone="warning">{refused}</Notice>}
      </CardBody>
    </Card>
  );
}
