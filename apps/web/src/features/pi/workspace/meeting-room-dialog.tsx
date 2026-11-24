"use client";

import { useState } from "react";
import { Video } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox, Label } from "@/components/ui/controls";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/overlays";
import { Notice } from "@/components/app/states";
import { useScopedMutation } from "@/hooks/use-scoped";
import { ApiError } from "@/services/api-client";
import { meetingRoomService, ROOM_REFUSED } from "../meeting-room-service";

/**
 * Open a video room: a title, and a confirmation that everyone who joins will be told the call is
 * transcribed by pi (an AI). No video is recorded; the words are kept as text.
 */
export function StartRoomDialog({
  open,
  onClose,
  onOpened,
}: {
  open: boolean;
  onClose: () => void;
  onOpened: (meetingId: string) => void;
}) {
  const [title, setTitle] = useState("");
  const [agreed, setAgreed] = useState(false);
  const make = useScopedMutation(meetingRoomService.open, {
    invalidate: [["pi", "meeting-intel"]],
    toastErrors: false,
    onSuccess: (out) => {
      setTitle("");
      setAgreed(false);
      onOpened(out.meeting.id);
    },
  });
  const failure =
    make.error instanceof ApiError
      ? (ROOM_REFUSED[make.error.code ?? ""] ??
        "Could not open the room. Try again.")
      : make.error
        ? "Could not open the room. Try again."
        : "";
  const ready = title.trim().length > 0 && agreed && !make.isPending;
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent size="md">
        <DialogHeader
          title="Start a video room"
          description="Meet your customer in a video room. pi is present as an AI assistant, listens, and writes the transcript."
        />
        <DialogBody className="space-y-3">
          <div>
            <Label htmlFor="room-title">Title</Label>
            <Input
              id="room-title"
              value={title}
              maxLength={200}
              disabled={make.isPending}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="For example: Tiles order review"
            />
          </div>
          <label className="flex items-start gap-2 text-sm">
            <Checkbox
              checked={agreed}
              disabled={make.isPending}
              onCheckedChange={(v) => setAgreed(v === true)}
            />
            <span>
              Everyone who joins will be told that pi (an AI) is in the room and
              that the call is transcribed.
            </span>
          </label>
          {failure && <Notice tone="danger">{failure}</Notice>}
        </DialogBody>
        <DialogFooter>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={!ready}
            loading={make.isPending}
            onClick={() =>
              make.mutate({ title: title.trim(), consent: agreed })
            }
          >
            <Video /> Start room
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
