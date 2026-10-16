"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  CalendarClock,
  CalendarDays,
  Check,
  Copy,
  ExternalLink,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/display";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/overlays";
import { Notice } from "@/components/app/states";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import { useNavItemAvailable } from "@/features/navigation/hooks";
import { cn } from "@/lib/utils";
import {
  meetingsService,
  type BookMeetingResult,
  type MeetingBoard,
} from "@/features/pi/meetings-service";
import {
  MeetingFields,
  useMeetingForm,
} from "@/features/pi/workspace/meeting-fields";

const BOARD_KEY = ["pi", "meetings", null];
const BOARD_HREF = "/pi/meetings";

/** The meeting board (this week), shared with the Meeting Board page's cache. */
function useBoard(enabled: boolean) {
  return useScopedQuery(BOARD_KEY, () => meetingsService.board(null), {
    enabled,
    staleTime: 30_000,
  });
}

function copyLink(link: string) {
  if (!navigator.clipboard) {
    toast.error("The link couldn't be copied.");
    return;
  }
  void navigator.clipboard
    .writeText(link)
    .then(() => toast.success("Meeting link copied."))
    .catch(() => toast.error("The link couldn't be copied."));
}

function zoneText(board: MeetingBoard | undefined) {
  if (!board) return null;
  return board.zone_name
    ? `${board.zone_name} (${board.timezone})`
    : board.timezone;
}

/** Whether this user can book meetings for customers from here. */
export function useCanBookMeeting() {
  const { can } = useSession();
  const available = useNavItemAvailable("pi");
  return Boolean(available) && can("pi.inbox.reply");
}

/** "Book meeting" header action: a time, how to meet and what it's about; pi tells the customer. */
export function BookMeetingAction({
  customerId,
  customerName,
}: {
  customerId: string;
  customerName: string;
}) {
  const [open, setOpen] = useState(false);
  // Remount per opening so the form starts fresh.
  const [round, setRound] = useState(0);
  const allowed = useCanBookMeeting();
  if (!allowed) return null;
  return (
    <>
      <Button
        size="sm"
        variant="secondary"
        onClick={() => {
          setRound((r) => r + 1);
          setOpen(true);
        }}
      >
        <CalendarClock /> Book meeting
      </Button>
      {open && (
        <BookMeetingDialog
          key={round}
          customerId={customerId}
          customerName={customerName}
          onClose={() => setOpen(false)}
        />
      )}
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
  const { can } = useSession();
  const router = useRouter();
  const board = useBoard(can("pi.read"));
  const googleMeet = board.data?.calendar === "connected";
  const form = useMeetingForm({ googleMeet: true });
  const [booked, setBooked] = useState<BookMeetingResult | null>(null);
  const book = useScopedMutation(
    () => meetingsService.book({ customer_id: customerId, ...form.values }),
    {
      invalidate: [
        ["pi", "meetings"],
        ["customers", "detail", customerId],
        ["customers", customerId],
      ],
      onSuccess: (r) => {
        setBooked(r);
        const message = bookedMessage(r, customerName);
        if (r.told_customer)
          toast.success(message, {
            action: {
              label: "Open Meeting Board",
              onClick: () => router.push(BOARD_HREF),
            },
          });
        else
          toast.warning(message, {
            duration: 15_000,
            action: r.link
              ? { label: "Copy link", onClick: () => copyLink(r.link) }
              : undefined,
          });
      },
    },
  );
  const zone = zoneText(board.data);
  const free = (board.data?.free ?? []).slice(0, 6);
  const picked = `${form.date}T${form.time}`;

  return (
    <Dialog open onOpenChange={(next) => !next && !book.isPending && onClose()}>
      <DialogContent size="md">
        <DialogHeader
          title={
            booked ? "Meeting booked" : `Book a meeting with ${customerName}`
          }
          description={
            booked
              ? undefined
              : "Pick a time and how you'll meet. pi sends the time and link to the customer on WhatsApp, in their language."
          }
        />
        {booked ? (
          <>
            <DialogBody className="space-y-3">
              <Notice
                tone={booked.told_customer ? "success" : "warning"}
                icon={booked.told_customer ? Check : CalendarClock}
              >
                {bookedMessage(booked, customerName)}
              </Notice>
              {booked.link && (
                <div className="flex min-w-0 items-center gap-2 rounded-lg border border-border bg-surface-muted px-3 py-2">
                  <span className="min-w-0 flex-1 truncate font-mono text-xs">
                    {booked.link}
                  </span>
                  <Button
                    size="xs"
                    variant="ghost"
                    onClick={() => copyLink(booked.link)}
                  >
                    <Copy aria-hidden="true" /> Copy
                  </Button>
                </div>
              )}
            </DialogBody>
            <DialogFooter>
              <Button variant="secondary" asChild>
                <Link href={BOARD_HREF}>
                  <CalendarDays /> Open Meeting Board
                </Link>
              </Button>
              <Button onClick={onClose}>Done</Button>
            </DialogFooter>
          </>
        ) : (
          <>
            <DialogBody className="space-y-3">
              {zone && (
                <p className="text-xs text-muted-foreground">Times in {zone}</p>
              )}
              {free.length > 0 && (
                <div>
                  <p className="mb-1.5 text-xs font-medium text-foreground-secondary">
                    Free soon
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {free.map((slot) => {
                      const active = slot.local.slice(0, 16) === picked;
                      return (
                        <button
                          key={slot.starts_at}
                          type="button"
                          aria-pressed={active}
                          onClick={() => form.pick(slot.local)}
                          className={cn(
                            "rounded-full border px-2.5 py-1 text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
                            active
                              ? "border-primary bg-primary-soft text-primary-soft-foreground"
                              : "border-border bg-surface text-foreground hover:bg-surface-muted",
                          )}
                        >
                          {slot.label || slot.local.replace("T", " ")}
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}
              <MeetingFields
                form={form}
                googleMeet={googleMeet}
                googleMeetFallback
                idPrefix="book-meet"
                noteLabel="What's it about? (optional)"
                notePlaceholder="e.g. Go through the website plan together."
              />
            </DialogBody>
            <DialogFooter>
              <Button
                variant="secondary"
                onClick={onClose}
                disabled={book.isPending}
              >
                Cancel
              </Button>
              <Button
                loading={book.isPending}
                disabled={!form.ready || book.isPending}
                onClick={() => book.mutate(undefined)}
              >
                <CalendarClock /> Book and tell the customer
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

function bookedMessage(r: BookMeetingResult, customerName: string) {
  const when = r.label || "the chosen time";
  if (r.told_customer)
    return `Meeting booked for ${when}. pi sent ${customerName} the link on WhatsApp.`;
  return `Meeting booked for ${when}. WhatsApp's 24-hour window is closed, so the customer wasn't messaged — share the link${r.link ? `: ${r.link}` : " yourself."}`;
}

/** "Next meeting" card for this customer, from the Meeting Board. */
export function CustomerNextMeeting({ customerId }: { customerId: string }) {
  const { can } = useSession();
  const available = useNavItemAvailable("pi");
  const board = useBoard(Boolean(available) && can("pi.read"));
  const next = board.data?.upcoming
    .filter((m) => m.customer_id === customerId)
    .sort((a, b) => a.starts_at.localeCompare(b.starts_at))[0];
  if (!next) return null;
  return (
    <Card>
      <CardBody className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-pi-soft text-pi">
          <CalendarClock className="size-4" aria-hidden="true" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[13px] font-medium">
            Next meeting: {next.label || next.local.replace("T", " ")}
          </p>
          {(next.topic || next.note || next.place) && (
            <p className="truncate text-xs text-muted-foreground">
              {next.topic || next.note || next.place}
            </p>
          )}
        </div>
        <div className="flex flex-wrap gap-1.5">
          {next.link && (
            <>
              <Button asChild size="xs" variant="soft">
                <a href={next.link} target="_blank" rel="noopener noreferrer">
                  <ExternalLink aria-hidden="true" /> Join
                </a>
              </Button>
              <Button
                size="xs"
                variant="ghost"
                onClick={() => copyLink(next.link)}
              >
                <Copy aria-hidden="true" /> Copy link
              </Button>
            </>
          )}
          <Button asChild size="xs" variant="ghost">
            <Link href={BOARD_HREF}>
              <CalendarDays aria-hidden="true" /> Open board
            </Link>
          </Button>
        </div>
      </CardBody>
    </Card>
  );
}
