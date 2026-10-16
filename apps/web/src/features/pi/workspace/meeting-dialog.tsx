"use client";

import { useState } from "react";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/controls";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/overlays";
import { useScopedMutation } from "@/hooks/use-scoped";
import { piRequestsService, type PiRequest } from "../requests-service";

type How = "google_meet" | "video" | "link" | "in_person";

function tomorrow(): string {
  const d = new Date(Date.now() + 86_400_000);
  return d.toISOString().slice(0, 10);
}

/** "Arrange meeting": pick a time and how to meet; pi sends it to the customer. */
export function MeetingDialog({
  request,
  googleMeet,
  onClose,
  initialStartsAt,
}: {
  request: Pick<PiRequest, "id" | "question"> | null;
  googleMeet: boolean;
  onClose: () => void;
  /** Prefill the date and time ("YYYY-MM-DDTHH:MM", business time). */
  initialStartsAt?: string | null;
}) {
  const preset = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(initialStartsAt ?? "")
    ? initialStartsAt!
    : null;
  const [date, setDate] = useState(preset ? preset.slice(0, 10) : tomorrow());
  const [time, setTime] = useState(preset ? preset.slice(11, 16) : "17:00");
  const [duration, setDuration] = useState("30");
  const [how, setHow] = useState<How>(googleMeet ? "google_meet" : "video");
  const [link, setLink] = useState("");
  const [place, setPlace] = useState("");
  const [note, setNote] = useState("");
  const arrange = useScopedMutation(
    () =>
      piRequestsService.arrangeMeeting(request!.id, {
        starts_at: `${date}T${time}`,
        duration_minutes: Number(duration),
        how,
        link: link.trim(),
        place: place.trim(),
        note: note.trim(),
      }),
    {
      invalidate: [["pi", "requests"], ["pi", "meetings"], ["pi"]],
      success:
        "Meeting arranged. pi is sending the time and link to the customer.",
      onSuccess: () => onClose(),
    },
  );
  const ready =
    Boolean(date && time) &&
    (how === "google_meet" ||
      how === "video" ||
      (how === "link" && /^https?:\/\//.test(link.trim())) ||
      (how === "in_person" && place.trim().length > 1));
  return (
    <Dialog
      open={request !== null}
      onOpenChange={(next) => !next && !arrange.isPending && onClose()}
    >
      <DialogContent size="md">
        <DialogHeader
          title="Arrange the meeting"
          description="Pick a time and how you'll meet. pi sends it to the customer on WhatsApp, in their language."
        />
        <DialogBody className="space-y-3">
          {request && (
            <p className="rounded-lg bg-surface-muted px-3 py-2 text-[13px] whitespace-pre-wrap">
              {request.question}
            </p>
          )}
          <div className="grid gap-3 sm:grid-cols-3">
            <div>
              <Label htmlFor="meet-date">Date</Label>
              <Input
                id="meet-date"
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="meet-time">Time</Label>
              <Input
                id="meet-time"
                type="time"
                value={time}
                onChange={(e) => setTime(e.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="meet-duration">Length</Label>
              <NativeSelect
                id="meet-duration"
                value={duration}
                onChange={(e) => setDuration(e.target.value)}
              >
                {["15", "30", "45", "60", "90"].map((m) => (
                  <option key={m} value={m}>
                    {m} minutes
                  </option>
                ))}
              </NativeSelect>
            </div>
          </div>
          <div>
            <Label htmlFor="meet-how">How</Label>
            <NativeSelect
              id="meet-how"
              value={how}
              onChange={(e) => setHow(e.target.value as How)}
            >
              <option value="google_meet" disabled={!googleMeet}>
                Google Meet (link made for you)
                {googleMeet ? "" : " · connect Google Calendar first"}
              </option>
              <option value="video">
                Video call (link made for you, no sign-up)
              </option>
              <option value="link">My own link (Zoom, Teams…)</option>
              <option value="in_person">In person</option>
            </NativeSelect>
          </div>
          {how === "link" && (
            <div>
              <Label htmlFor="meet-link">Meeting link</Label>
              <Input
                id="meet-link"
                inputMode="url"
                placeholder="https://zoom.us/j/…"
                value={link}
                onChange={(e) => setLink(e.target.value)}
              />
            </div>
          )}
          {how === "in_person" && (
            <div>
              <Label htmlFor="meet-place">Where</Label>
              <Input
                id="meet-place"
                placeholder="e.g. Our office, 12 Main Boulevard, Lahore"
                value={place}
                onChange={(e) => setPlace(e.target.value)}
              />
            </div>
          )}
          <div>
            <Label htmlFor="meet-note">Note for the customer (optional)</Label>
            <Textarea
              id="meet-note"
              rows={2}
              maxLength={1000}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="e.g. Please keep your sales report handy."
            />
          </div>
        </DialogBody>
        <DialogFooter>
          <Button
            variant="secondary"
            onClick={onClose}
            disabled={arrange.isPending}
          >
            Cancel
          </Button>
          <Button
            loading={arrange.isPending}
            disabled={!ready || arrange.isPending}
            onClick={() => arrange.mutate(undefined)}
          >
            Arrange and tell the customer
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
