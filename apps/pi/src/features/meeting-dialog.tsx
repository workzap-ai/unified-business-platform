"use client";

/**
 * "Arrange the meeting" for a meeting request: pick a time and how to meet (a Google
 * Meet link made by the connected calendar, your own link, or in person). pi sends it to
 * the customer on WhatsApp in their language; it never makes up a time or link.
 * The form fields (MeetingFields + useMeetingForm) are shared with "Book meeting" on a
 * customer's profile (book-meeting.tsx).
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

export type How = "google_meet" | "video" | "link" | "in_person";

function tomorrow(): string {
  return new Date(Date.now() + 86_400_000).toISOString().slice(0, 10);
}

/** The meeting form's state: time, length, how, link, place and note. */
export function useMeetingForm({
  googleMeet,
  initialStartsAt,
}: {
  googleMeet: boolean;
  /** A time to start from, "YYYY-MM-DDTHH:MM" in business time. */
  initialStartsAt?: string;
}) {
  const prefill = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(initialStartsAt ?? "")
    ? initialStartsAt
    : undefined;
  const [date, setDate] = React.useState(prefill?.slice(0, 10) ?? tomorrow());
  const [time, setTime] = React.useState(prefill?.slice(11, 16) ?? "17:00");
  const [duration, setDuration] = React.useState("30");
  const [how, setHow] = React.useState<How>(
    googleMeet ? "google_meet" : "video",
  );
  const [link, setLink] = React.useState("");
  const [place, setPlace] = React.useState("");
  const [note, setNote] = React.useState("");
  const ready =
    Boolean(date && time) &&
    (how === "google_meet" ||
      how === "video" ||
      (how === "link" && /^https?:\/\//.test(link.trim())) ||
      (how === "in_person" && place.trim().length > 1));
  return {
    date,
    setDate,
    time,
    setTime,
    duration,
    setDuration,
    how,
    setHow,
    link,
    setLink,
    place,
    setPlace,
    note,
    setNote,
    ready,
    /** The fields as the API takes them (starts_at in business-local time). */
    payload: () => ({
      starts_at: `${date}T${time}`,
      duration_minutes: Number(duration),
      how,
      link: link.trim(),
      place: place.trim(),
      note: note.trim(),
    }),
  };
}

export type MeetingForm = ReturnType<typeof useMeetingForm>;

/** Date, time, length, how, link / place and a note for the customer. */
export function MeetingFields({
  form,
  googleMeet,
  idPrefix = "meet",
  zoneName,
  noteLabel = "Note for the customer",
  notePlaceholder = "e.g. Please keep your sales report handy.",
}: {
  form: MeetingForm;
  googleMeet: boolean;
  idPrefix?: string;
  /** The business's time zone, shown under the time ("Times in …"). */
  zoneName?: string;
  noteLabel?: string;
  notePlaceholder?: string;
}) {
  const id = (name: string) => `${idPrefix}-${name}`;
  return (
    <>
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="Date" htmlFor={id("date")}>
          <Input
            id={id("date")}
            type="date"
            value={form.date}
            onChange={(e) => form.setDate(e.target.value)}
          />
        </Field>
        <Field label="Time" htmlFor={id("time")}>
          <Input
            id={id("time")}
            type="time"
            value={form.time}
            onChange={(e) => form.setTime(e.target.value)}
          />
        </Field>
        <Field label="Length" htmlFor={id("duration")}>
          <Select
            id={id("duration")}
            value={form.duration}
            onChange={(e) => form.setDuration(e.target.value)}
          >
            {["15", "30", "45", "60", "90"].map((m) => (
              <option key={m} value={m}>
                {m} minutes
              </option>
            ))}
          </Select>
        </Field>
      </div>
      {zoneName ? (
        <p className="-mt-2 text-xs text-muted-foreground">
          Times in {zoneName}
        </p>
      ) : null}
      <Field label="How" htmlFor={id("how")}>
        <Select
          id={id("how")}
          value={form.how}
          onChange={(e) => form.setHow(e.target.value as How)}
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
      {form.how === "link" ? (
        <Field label="Meeting link" htmlFor={id("link")}>
          <Input
            id={id("link")}
            inputMode="url"
            placeholder="https://zoom.us/j/…"
            value={form.link}
            onChange={(e) => form.setLink(e.target.value)}
          />
        </Field>
      ) : null}
      {form.how === "in_person" ? (
        <Field label="Where" htmlFor={id("place")}>
          <Input
            id={id("place")}
            placeholder="e.g. Our office, 12 Main Boulevard, Lahore"
            value={form.place}
            onChange={(e) => form.setPlace(e.target.value)}
          />
        </Field>
      ) : null}
      <Field label={noteLabel} htmlFor={id("note")} optional>
        <Textarea
          id={id("note")}
          rows={2}
          maxLength={1000}
          value={form.note}
          onChange={(e) => form.setNote(e.target.value)}
          placeholder={notePlaceholder}
        />
      </Field>
    </>
  );
}

export function MeetingDialog({
  requestId,
  question,
  googleMeet,
  onClose,
  initialStartsAt,
}: {
  requestId: string | null;
  question: string;
  googleMeet: boolean;
  onClose: () => void;
  /** A time to start from, "YYYY-MM-DDTHH:MM" in business time (the meetings board). */
  initialStartsAt?: string;
}) {
  const form = useMeetingForm({ googleMeet, initialStartsAt });
  const arrange = useAction(
    () => post(`/pi/requests/${requestId}/meeting`, form.payload()),
    {
      success:
        "Meeting arranged. pi is sending the time and link to the customer.",
      invalidate: [["requests"], ["conversations"], ["home"], ["meetings"]],
      onSuccess: () => onClose(),
    },
  );
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
            if (form.ready) arrange.mutate(undefined);
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
          <MeetingFields form={form} googleMeet={googleMeet} />
          <div className="flex flex-wrap justify-end gap-2">
            <Button
              type="button"
              variant="secondary"
              onClick={onClose}
              disabled={arrange.isPending}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              loading={arrange.isPending}
              disabled={!form.ready}
            >
              Arrange and tell the customer
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
