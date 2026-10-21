"use client";

import { useState } from "react";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/controls";

export type MeetingHow = "google_meet" | "video" | "link" | "in_person";

export type MeetingFormValues = {
  starts_at: string;
  duration_minutes: number;
  how: MeetingHow;
  link: string;
  place: string;
  note: string;
};

function tomorrow(): string {
  const d = new Date(Date.now() + 86_400_000);
  return d.toISOString().slice(0, 10);
}

const STARTS_AT = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/;

/** State for the meeting form: date, time, length, how, link/place and a note. */
export function useMeetingForm({
  googleMeet,
  initialStartsAt,
}: {
  googleMeet: boolean;
  /** Prefill the date and time ("YYYY-MM-DDTHH:MM", business time). */
  initialStartsAt?: string | null;
}) {
  const preset = STARTS_AT.test(initialStartsAt ?? "")
    ? initialStartsAt!
    : null;
  const [date, setDate] = useState(preset ? preset.slice(0, 10) : tomorrow());
  const [time, setTime] = useState(preset ? preset.slice(11, 16) : "17:00");
  const [duration, setDuration] = useState("30");
  const [how, setHow] = useState<MeetingHow>(
    googleMeet ? "google_meet" : "video",
  );
  const [link, setLink] = useState("");
  const [place, setPlace] = useState("");
  const [note, setNote] = useState("");
  const ready =
    Boolean(date && time) &&
    (how === "google_meet" ||
      how === "video" ||
      (how === "link" && /^https?:\/\//.test(link.trim())) ||
      (how === "in_person" && place.trim().length > 1));
  const values: MeetingFormValues = {
    starts_at: `${date}T${time}`,
    duration_minutes: Number(duration),
    how,
    link: link.trim(),
    place: place.trim(),
    note: note.trim(),
  };
  /** Fill date and time from "YYYY-MM-DDTHH:MM". */
  const pick = (startsAt: string) => {
    if (!STARTS_AT.test(startsAt)) return;
    setDate(startsAt.slice(0, 10));
    setTime(startsAt.slice(11, 16));
  };
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
    values,
    pick,
  };
}

export type MeetingForm = ReturnType<typeof useMeetingForm>;

/** The shared meeting fields (arrange from a request, or book from a customer). */
export function MeetingFields({
  form,
  googleMeet,
  idPrefix = "meet",
  noteLabel = "Note for the customer (optional)",
  notePlaceholder = "e.g. Please keep your sales report handy.",
  googleMeetFallback = false,
}: {
  form: MeetingForm;
  googleMeet: boolean;
  idPrefix?: string;
  noteLabel?: string;
  notePlaceholder?: string;
  /** Keep Google Meet selectable when Calendar isn't usable (the server falls back to pi's video link). */
  googleMeetFallback?: boolean;
}) {
  const id = (name: string) => `${idPrefix}-${name}`;
  return (
    <>
      <div className="grid gap-3 sm:grid-cols-3">
        <div>
          <Label htmlFor={id("date")}>Date</Label>
          <Input
            id={id("date")}
            type="date"
            value={form.date}
            onChange={(e) => form.setDate(e.target.value)}
          />
        </div>
        <div>
          <Label htmlFor={id("time")}>Time</Label>
          <Input
            id={id("time")}
            type="time"
            value={form.time}
            onChange={(e) => form.setTime(e.target.value)}
          />
        </div>
        <div>
          <Label htmlFor={id("duration")}>Length</Label>
          <NativeSelect
            id={id("duration")}
            value={form.duration}
            onChange={(e) => form.setDuration(e.target.value)}
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
        <Label htmlFor={id("how")}>How</Label>
        <NativeSelect
          id={id("how")}
          value={form.how}
          onChange={(e) => form.setHow(e.target.value as MeetingHow)}
        >
          <option
            value="google_meet"
            disabled={!googleMeet && !googleMeetFallback}
          >
            Google Meet (link made for you)
            {googleMeet
              ? ""
              : googleMeetFallback
                ? " · pi's video link until Google Calendar is connected"
                : " · connect Google Calendar first"}
          </option>
          <option value="video">
            Video call (link made for you, no sign-up)
          </option>
          <option value="link">My own link (Zoom, Teams…)</option>
          <option value="in_person">In person</option>
        </NativeSelect>
      </div>
      {form.how === "link" && (
        <div>
          <Label htmlFor={id("link")}>Meeting link</Label>
          <Input
            id={id("link")}
            inputMode="url"
            placeholder="https://zoom.us/j/…"
            value={form.link}
            onChange={(e) => form.setLink(e.target.value)}
          />
        </div>
      )}
      {form.how === "in_person" && (
        <div>
          <Label htmlFor={id("place")}>Where</Label>
          <Input
            id={id("place")}
            placeholder="e.g. Our office, 12 Main Boulevard, Lahore"
            value={form.place}
            onChange={(e) => form.setPlace(e.target.value)}
          />
        </div>
      )}
      <div>
        <Label htmlFor={id("note")}>{noteLabel}</Label>
        <Textarea
          id={id("note")}
          rows={2}
          maxLength={1000}
          value={form.note}
          onChange={(e) => form.setNote(e.target.value)}
          placeholder={notePlaceholder}
        />
      </div>
    </>
  );
}
