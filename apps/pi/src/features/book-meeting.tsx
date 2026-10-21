"use client";

/**
 * "Book meeting" on a customer's profile: the team picks a time (a free slot from the
 * meetings board, or any time) and how to meet; pi makes the link, puts the meeting on
 * the board and sends the time and link on WhatsApp. When WhatsApp's 24-hour window is
 * closed the customer isn't messaged, and the link is shown to share by hand.
 * Also "Next meeting": this customer's next booked meeting from the board.
 * API: POST /pi/meetings/book, GET /pi/meetings (app/modules/pi_saas/meeting_board.py).
 */

import { useQuery } from "@tanstack/react-query";
import {
  CalendarClock,
  CalendarDays,
  Check,
  Copy,
  ExternalLink,
  MapPin,
} from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import {
  Badge,
  Button,
  Card,
  CardSection,
  Dialog,
  DialogContent,
  Notice,
  cn,
} from "@/components/ui";
import { MeetingFields, useMeetingForm } from "@/features/meeting-dialog";
import { errorText, get, post } from "@/lib/api";
import { useAction, useBusinessKey, useCan } from "@/lib/session";

/** The parts of GET /pi/meetings this page reads (same query as the board's first week). */
interface BoardMeeting {
  conversation_id: string;
  customer_id: string | null;
  starts_at: string;
  label: string;
  minutes: number;
  how: string;
  link: string;
  place: string;
  status: string;
}

interface BoardSummary {
  zone_name: string;
  calendar: "none" | "connected" | "error";
  upcoming: BoardMeeting[];
  free: { starts_at: string; local: string; label: string }[];
}

interface Booked {
  ok: true;
  conversation_id: string;
  label: string | null;
  link: string;
  told_customer: boolean;
}

const HOW_LABEL: Record<string, string> = {
  google_meet: "Google Meet",
  video: "Video call",
  link: "Online link",
  in_person: "In person",
};

/** The board's current week, shared with /meetings (same cache key). */
function useBoard(enabled: boolean) {
  const key = useBusinessKey();
  return useQuery({
    queryKey: key(["meetings", "today"]),
    queryFn: () =>
      get<BoardSummary>("/pi/meetings", { start: undefined, days: 7 }),
    enabled,
    staleTime: 30_000,
  });
}

async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text);
    toast.success("Link copied");
  } catch {
    toast.error("Couldn't copy. Select the link and copy it.");
  }
}

/** The header button and its dialog. Only for people who can reply to customers. */
export function BookMeetingButton({
  customerId,
  customerName,
}: {
  customerId: string;
  customerName: string;
}) {
  const can = useCan();
  const [open, setOpen] = React.useState(false);
  // Open counter: a fresh form each time the dialog opens.
  const [round, setRound] = React.useState(0);
  if (!can("pi.inbox.reply")) return null;
  return (
    <>
      <Button
        variant="secondary"
        onClick={() => {
          setRound((r) => r + 1);
          setOpen(true);
        }}
      >
        <CalendarClock className="size-4" aria-hidden /> Book meeting
      </Button>
      {open ? (
        <BookMeetingDialog
          key={round}
          customerId={customerId}
          customerName={customerName}
          onClose={() => setOpen(false)}
        />
      ) : null}
    </>
  );
}

function BookMeetingDialog({
  customerId,
  customerName,
  onClose,
}: {
  customerId: string;
  customerName: string;
  onClose: () => void;
}) {
  const can = useCan();
  const board = useBoard(can("pi.read"));
  const googleMeet = board.data?.calendar === "connected";
  const form = useMeetingForm({ googleMeet });
  // Once the board says Google Calendar is connected, start from Google Meet.
  const [defaulted, setDefaulted] = React.useState(false);
  if (!defaulted && board.data) {
    setDefaulted(true);
    if (googleMeet && form.how === "video") form.setHow("google_meet");
  }
  const [booked, setBooked] = React.useState<Booked | null>(null);
  const book = useAction(
    () => {
      const p = form.payload();
      return post<Booked>("/pi/meetings/book", {
        customer_id: customerId,
        starts_at: p.starts_at,
        duration_minutes: p.duration_minutes,
        how: p.how,
        ...(p.how === "link" ? { link: p.link } : {}),
        ...(p.how === "in_person" ? { place: p.place } : {}),
        ...(p.note ? { note: p.note } : {}),
      });
    },
    {
      invalidate: [
        ["meetings"],
        ["conversations"],
        ["requests"],
        ["home"],
        ["profile", customerId],
        ["customer-overview", customerId],
      ],
      onSuccess: (result) => setBooked(result),
    },
  );
  const picks = (board.data?.free ?? []).slice(0, 6);
  const startsAt = `${form.date}T${form.time}`;
  return (
    <Dialog
      open
      onOpenChange={(next) => (!next && !book.isPending ? onClose() : null)}
    >
      <DialogContent
        title={booked ? "Meeting booked" : "Book a meeting"}
        description={
          booked
            ? customerName
            : `With ${customerName}. pi makes the link, puts it on your meetings board and sends the time and link on WhatsApp, in their language.`
        }
      >
        {booked ? (
          <BookedResult booked={booked} onClose={onClose} />
        ) : (
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              if (form.ready) book.mutate(undefined);
            }}
          >
            {picks.length ? (
              <div>
                <p className="mb-2 text-sm font-medium">Free times</p>
                <div className="flex flex-wrap gap-1.5">
                  {picks.map((f) => {
                    const on = f.local.slice(0, 16) === startsAt;
                    return (
                      <button
                        key={f.local}
                        type="button"
                        aria-pressed={on}
                        onClick={() => {
                          form.setDate(f.local.slice(0, 10));
                          form.setTime(f.local.slice(11, 16));
                        }}
                        className={cn(
                          "min-h-10 rounded-full border border-success/30 bg-success-soft/60 px-3 text-sm font-medium text-success hover:border-success/60",
                          on &&
                            "border-success bg-success-soft ring-2 ring-success/30",
                        )}
                      >
                        {f.label}
                      </button>
                    );
                  })}
                </div>
              </div>
            ) : null}
            <MeetingFields
              form={form}
              googleMeet={googleMeet}
              idPrefix="book"
              zoneName={board.data?.zone_name}
              noteLabel="What's it about?"
              notePlaceholder="e.g. Go through the proposal and next steps."
            />
            {book.isError ? (
              <Notice tone="danger">{errorText(book.error)}</Notice>
            ) : null}
            <div className="flex flex-wrap justify-end gap-2">
              <Button
                type="button"
                variant="secondary"
                onClick={onClose}
                disabled={book.isPending}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                loading={book.isPending}
                disabled={!form.ready}
              >
                Book and tell the customer
              </Button>
            </div>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}

function BookedResult({
  booked,
  onClose,
}: {
  booked: Booked;
  onClose: () => void;
}) {
  const when = booked.label || "the time you picked";
  return (
    <div className="space-y-4">
      {booked.told_customer ? (
        <Notice tone="success" title={`Meeting booked for ${when}.`}>
          pi sent the link on WhatsApp.
        </Notice>
      ) : (
        <Notice tone="warning" title={`Meeting booked for ${when}.`}>
          WhatsApp&apos;s 24-hour window is closed, so the customer wasn&apos;t
          messaged. Share this link with them yourself.
        </Notice>
      )}
      {booked.link ? <LinkRow link={booked.link} /> : null}
      <div className="flex flex-wrap justify-end gap-2">
        <Button variant="secondary" asChild>
          <Link href="/meetings">
            <CalendarDays className="size-4" aria-hidden /> Open meetings board
          </Link>
        </Button>
        <Button onClick={onClose}>
          <Check className="size-4" aria-hidden /> Done
        </Button>
      </div>
    </div>
  );
}

function LinkRow({ link }: { link: string }) {
  return (
    <div className="flex min-w-0 items-center gap-2 rounded-lg border border-border bg-surface-muted px-3 py-2">
      <a
        href={link}
        target="_blank"
        rel="noreferrer"
        className="min-w-0 flex-1 truncate text-sm text-accent hover:underline"
        data-user-text
      >
        {link}
      </a>
      <Button
        type="button"
        variant="secondary"
        size="sm"
        onClick={() => void copyText(link)}
      >
        <Copy className="size-4" aria-hidden /> Copy
      </Button>
    </div>
  );
}

/** This customer's next booked meeting, from the meetings board. Hidden when none. */
export function NextMeetingCard({ customerId }: { customerId: string }) {
  const can = useCan();
  const board = useBoard(can("pi.read"));
  const next = (board.data?.upcoming ?? [])
    .filter((m) => m.customer_id === customerId && m.status !== "cancelled")
    .sort((a, b) => a.starts_at.localeCompare(b.starts_at))[0];
  if (!next) return null;
  const online = next.how !== "in_person" && Boolean(next.link);
  return (
    <Card>
      <CardSection className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="flex min-w-0 flex-1 items-start gap-3">
          <CalendarClock
            className="mt-0.5 size-5 shrink-0 text-accent"
            aria-hidden
          />
          <div className="min-w-0">
            <p className="text-xs text-muted-foreground">Next meeting</p>
            <p className="font-semibold">{next.label}</p>
            <p className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
              <Badge>{HOW_LABEL[next.how] ?? "Meeting"}</Badge>
              {next.minutes ? <span>{next.minutes} minutes</span> : null}
              {next.how === "in_person" && next.place ? (
                <span className="inline-flex min-w-0 items-center gap-1 break-words">
                  <MapPin className="size-3.5 shrink-0" aria-hidden />
                  <span data-user-text>{next.place}</span>
                </span>
              ) : null}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {online ? (
            <>
              <Button size="sm" asChild>
                <a href={next.link} target="_blank" rel="noreferrer">
                  <ExternalLink className="size-4" aria-hidden /> Join
                </a>
              </Button>
              <Button
                size="sm"
                variant="secondary"
                onClick={() => void copyText(next.link)}
              >
                <Copy className="size-4" aria-hidden /> Copy link
              </Button>
            </>
          ) : null}
          <Button size="sm" variant="secondary" asChild>
            <Link href="/meetings">
              <CalendarDays className="size-4" aria-hidden /> Open board
            </Link>
          </Button>
        </div>
      </CardSection>
    </Card>
  );
}
