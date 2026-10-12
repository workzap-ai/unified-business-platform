"use client";

/**
 * "Arrange the meeting" for a meeting request: pick a time and how to meet (a Google
 * Meet link made by the connected calendar, your own link, or in person). pi sends it to
 * the customer on WhatsApp in their language; it never makes up a time or link.
 */

import * as React from "react";

import {
  Button,
  Dialog,
  DialogContent,
  Field,
  Input,
  Select,
  Textarea,
} from "@/components/ui";
import { post } from "@/lib/api";
import { useAction } from "@/lib/session";

type How = "google_meet" | "video" | "link" | "in_person";

function tomorrow(): string {
  return new Date(Date.now() + 86_400_000).toISOString().slice(0, 10);
}

export function MeetingDialog({
  requestId,
  question,
  googleMeet,
  onClose,
}: {
  requestId: string | null;
  question: string;
  googleMeet: boolean;
  onClose: () => void;
}) {
  const [date, setDate] = React.useState(tomorrow());
  const [time, setTime] = React.useState("17:00");
  const [duration, setDuration] = React.useState("30");
  const [how, setHow] = React.useState<How>(
    googleMeet ? "google_meet" : "video",
  );
  const [link, setLink] = React.useState("");
  const [place, setPlace] = React.useState("");
  const [note, setNote] = React.useState("");
  const arrange = useAction(
    () =>
      post(`/pi/requests/${requestId}/meeting`, {
        starts_at: `${date}T${time}`,
        duration_minutes: Number(duration),
        how,
        link: link.trim(),
        place: place.trim(),
        note: note.trim(),
      }),
    {
      success:
        "Meeting arranged. pi is sending the time and link to the customer.",
      invalidate: [["requests"], ["conversations"], ["home"]],
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
      open={requestId !== null}
      onOpenChange={(next) => (!next && !arrange.isPending ? onClose() : null)}
    >
      <DialogContent
        title="Arrange the meeting"
        description="Pick a time and how you'll meet. pi sends it to the customer on WhatsApp, in their language."
      >
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (ready) arrange.mutate(undefined);
          }}
        >
          {question ? (
            <p
              className="whitespace-pre-wrap break-words rounded-lg bg-surface-muted px-3 py-2 text-sm"
              data-user-text
            >
              {question}
            </p>
          ) : null}
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Date" htmlFor="meet-date">
              <Input
                id="meet-date"
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
              />
            </Field>
            <Field label="Time" htmlFor="meet-time">
              <Input
                id="meet-time"
                type="time"
                value={time}
                onChange={(e) => setTime(e.target.value)}
              />
            </Field>
            <Field label="Length" htmlFor="meet-duration">
              <Select
                id="meet-duration"
                value={duration}
                onChange={(e) => setDuration(e.target.value)}
              >
                {["15", "30", "45", "60", "90"].map((m) => (
                  <option key={m} value={m}>
                    {m} minutes
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <Field label="How" htmlFor="meet-how">
            <Select
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
            </Select>
          </Field>
          {how === "link" ? (
            <Field label="Meeting link" htmlFor="meet-link">
              <Input
                id="meet-link"
                inputMode="url"
                placeholder="https://zoom.us/j/…"
                value={link}
                onChange={(e) => setLink(e.target.value)}
              />
            </Field>
          ) : null}
          {how === "in_person" ? (
            <Field label="Where" htmlFor="meet-place">
              <Input
                id="meet-place"
                placeholder="e.g. Our office, 12 Main Boulevard, Lahore"
                value={place}
                onChange={(e) => setPlace(e.target.value)}
              />
            </Field>
          ) : null}
          <Field label="Note for the customer" htmlFor="meet-note" optional>
            <Textarea
              id="meet-note"
              rows={2}
              maxLength={1000}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="e.g. Please keep your sales report handy."
            />
          </Field>
          <div className="flex flex-wrap justify-end gap-2">
            <Button
              type="button"
              variant="secondary"
              onClick={onClose}
              disabled={arrange.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" loading={arrange.isPending} disabled={!ready}>
              Arrange and tell the customer
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
