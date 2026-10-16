"use client";

/**
 * Meetings board: the week of customer meetings next to the business's free time and
 * Google Calendar busy time. The team books a waiting meeting request into a free slot,
 * moves or cancels a meeting (pi tells the customer, in their language), sends the link
 * again, and records how it went; pi reads that note before its next reply.
 * All times are shown in the business's time zone, not the browser's.
 * API: app/modules/pi_saas/meeting_board.py (/pi/meetings).
 */
import { useQuery } from "@tanstack/react-query";
import {
  CalendarCheck,
  CalendarClock,
  CalendarX,
  ChevronLeft,
  ChevronRight,
  Clock,
  Copy,
  ExternalLink,
  History,
  Link2,
  MapPin,
  MessageCircle,
  Move,
  Plus,
  Send,
  Video,
  X,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { PiFace } from "@/components/brand";
import {
  Badge,
  Button,
  Card,
  CardSection,
  Dialog,
  DialogContent,
  EmptyState,
  ErrorState,
  Field,
  Input,
  LoadingBlock,
  Notice,
  PageHeader,
  Select,
  Switch,
  Textarea,
  cn,
} from "@/components/ui";
import { MeetingDialog } from "@/features/meeting-dialog";
import { errorText, get, post } from "@/lib/api";
import { useAction, useBusinessKey, useCan } from "@/lib/session";

const LIVE_EVERY_MS = 20_000;
/** Height of one half-hour row on the desktop grid, in pixels. */
const ROW_PX = 36;
const PX_PER_MINUTE = ROW_PX / 30;

type DayKey = "mon" | "tue" | "wed" | "thu" | "fri" | "sat" | "sun";
type Status =
  "scheduled" | "live" | "awaiting_outcome" | "done" | "no_show" | "cancelled";

export interface Meeting {
  id: string;
  conversation_id: string;
  customer_id: string | null;
  customer_name: string;
  phone: string | null;
  starts_at: string;
  ends_at: string;
  local: string;
  label: string;
  minutes: number;
  how: string;
  link: string;
  place: string;
  note: string;
  status: Status | string;
  outcome: string;
  change_to: string | null;
  change_label: string | null;
  calendar_event: boolean;
  actionable: boolean;
  topic: string;
}

interface Booking {
  id: string;
  customer_name: string;
  starts_at: string;
  ends_at: string;
  status: string;
  conversation_id: string | null;
}

interface FreeSlot {
  starts_at: string;
  local: string;
  label: string;
}

interface Waiting {
  request_id: string;
  conversation_id: string;
  customer_name: string;
  question: string;
  priority: "normal" | "high";
  asked_local: string | null;
  asked_label: string | null;
  how: string;
  created_at: string;
  topic: string;
}

interface Board {
  timezone: string;
  zone_name: string;
  now: string;
  start: string;
  days: number;
  hours: Record<DayKey, { open: boolean; start: string; end: string }>;
  calendar: "none" | "connected" | "error";
  busy: { starts_at: string; ends_at: string }[];
  meetings: Meeting[];
  upcoming: Meeting[];
  needs_outcome: Meeting[];
  history: Meeting[];
  bookings: Booking[];
  free: FreeSlot[];
  waiting: Waiting[];
  stats: {
    today: number;
    this_week: number;
    waiting: number;
    change_requests: number;
    needs_outcome: number;
    done: number;
    no_show: number;
  };
}

interface Told {
  ok: boolean;
  told_customer: boolean;
  calendar_moved?: boolean | null;
  calendar_removed?: boolean | null;
}

const STATUS: Record<
  string,
  {
    label: string;
    tone: "neutral" | "accent" | "success" | "warning" | "danger" | "info";
    block: string;
  }
> = {
  scheduled: {
    label: "Booked",
    tone: "accent",
    block:
      "border-accent/50 bg-accent-soft text-accent-soft-foreground hover:border-accent",
  },
  live: {
    label: "Happening now",
    tone: "success",
    block: "border-success bg-success-soft text-success ring-1 ring-success/40",
  },
  awaiting_outcome: {
    label: "How did it go?",
    tone: "warning",
    block: "border-warning/60 bg-warning-soft text-warning",
  },
  done: {
    label: "Done",
    tone: "neutral",
    block: "border-border bg-surface-muted text-foreground-secondary",
  },
  no_show: {
    label: "No-show",
    tone: "danger",
    block: "border-danger/40 bg-danger-soft text-danger",
  },
  cancelled: {
    label: "Cancelled",
    tone: "neutral",
    block:
      "border-dashed border-border bg-surface text-muted-foreground line-through opacity-70",
  },
};
const statusOf = (s: string) => STATUS[s] ?? STATUS.scheduled;

const HOW: Record<string, { label: string; icon: LucideIcon }> = {
  google_meet: { label: "Google Meet", icon: Video },
  video: { label: "Video call", icon: Video },
  link: { label: "Online link", icon: Link2 },
  in_person: { label: "In person", icon: MapPin },
};
const howOf = (how: string) =>
  HOW[how] ?? { label: "Meeting", icon: CalendarClock };

const DAY_BY_INDEX: DayKey[] = [
  "sun",
  "mon",
  "tue",
  "wed",
  "thu",
  "fri",
  "sat",
];

// ---- time helpers -----------------------------------------------------------------

function addDays(day: string, n: number): string {
  const d = new Date(`${day}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

function weekday(day: string): DayKey {
  return DAY_BY_INDEX[new Date(`${day}T00:00:00Z`).getUTCDay()];
}

function toMinutes(hm: string): number {
  const [h, m] = hm.split(":").map(Number);
  return (h || 0) * 60 + (m || 0);
}

/** A "YYYY-MM-DDTHH:MM" business wall-clock time, as a Date read in UTC. */
function wall(local: string): Date {
  return new Date(`${local.slice(0, 16)}:00Z`);
}

function formatter(zone: string, options: Intl.DateTimeFormatOptions) {
  try {
    return new Intl.DateTimeFormat(undefined, { ...options, timeZone: zone });
  } catch {
    return new Intl.DateTimeFormat(undefined, { ...options, timeZone: "UTC" });
  }
}

/** Formatting in the business's time zone. */
interface Clock {
  /** Business-local day and minutes after midnight for an instant. */
  at: (iso: string | number) => { day: string; minutes: number };
  time: (iso: string) => string;
  dayTime: (iso: string) => string;
  /** A business wall-clock "YYYY-MM-DDTHH:MM", formatted as is. */
  localDayTime: (local: string) => string;
  localTime: (local: string) => string;
  dayLabel: (day: string) => { weekday: string; date: string };
  shortDay: (day: string) => string;
}

function makeClock(zone: string): Clock {
  const parts = formatter(zone, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  });
  const time = formatter(zone, { hour: "numeric", minute: "2-digit" });
  const dayTime = formatter(zone, {
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
  });
  const utcTime = formatter("UTC", { hour: "numeric", minute: "2-digit" });
  const utcDayTime = formatter("UTC", {
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
  });
  const utcWeekday = formatter("UTC", { weekday: "short" });
  const utcDate = formatter("UTC", { day: "numeric", month: "short" });
  return {
    at(value) {
      const p: Record<string, string> = {};
      for (const part of parts.formatToParts(new Date(value)))
        p[part.type] = part.value;
      return {
        day: `${p.year}-${p.month}-${p.day}`,
        minutes: (Number(p.hour) % 24) * 60 + Number(p.minute),
      };
    },
    time: (iso) => time.format(new Date(iso)),
    dayTime: (iso) => dayTime.format(new Date(iso)),
    localDayTime: (local) => utcDayTime.format(wall(local)),
    localTime: (local) => utcTime.format(wall(local)),
    dayLabel: (day) => {
      const d = new Date(`${day}T12:00:00Z`);
      return { weekday: utcWeekday.format(d), date: utcDate.format(d) };
    },
    shortDay: (day) => utcDate.format(new Date(`${day}T12:00:00Z`)),
  };
}

const relative = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });

function fromNow(iso: string, now: number): string {
  const minutes = Math.round((new Date(iso).getTime() - now) / 60_000);
  if (Math.abs(minutes) < 1) return "now";
  if (Math.abs(minutes) < 60) return relative.format(minutes, "minute");
  const hours = Math.round(minutes / 60);
  if (Math.abs(hours) < 36) return relative.format(hours, "hour");
  return relative.format(Math.round(hours / 24), "day");
}

/** The current time, ticking every half minute (the board's "now" line). */
function useNow(): number {
  const [now, setNow] = React.useState(() => Date.now());
  React.useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 30_000);
    return () => window.clearInterval(id);
  }, []);
  return now;
}

/** Toast after a move / accept / cancel: says plainly when the customer wasn't told. */
function toldToast(done: string, result: Told, notify: boolean) {
  const calendarFailed =
    result.calendar_moved === false || result.calendar_removed === false;
  const calendar = calendarFailed
    ? " Google Calendar couldn't be updated, so change it there too."
    : "";
  if (notify && !result.told_customer) {
    toast.warning(
      `${done}. The customer wasn't messaged: WhatsApp's 24-hour window has closed. Call them, or tell them when they next write.${calendar}`,
    );
  } else if (calendarFailed) {
    toast.warning(`${done}.${calendar}`);
  } else {
    toast.success(notify ? `${done}. pi told the customer.` : `${done}.`);
  }
}

function chatHref(conversationId: string) {
  return `/inbox?conversation=${conversationId}`;
}

// ---- page -----------------------------------------------------------------------------

type MoveTarget = { meeting: Meeting; startsAt?: string };
type ArrangeTarget = { request: Waiting; startsAt?: string };

export function MeetingsPage() {
  const can = useCan();
  const key = useBusinessKey();
  const allowed = can("pi.read");
  const reply = can("pi.inbox.reply");
  const [start, setStart] = React.useState<string | null>(null);
  const board = useQuery({
    queryKey: key(["meetings", start ?? "today"]),
    queryFn: () =>
      get<Board>("/pi/meetings", { start: start ?? undefined, days: 7 }),
    enabled: allowed,
    refetchInterval: LIVE_EVERY_MS,
    placeholderData: (previous) => previous,
  });
  const data = board.data;
  const clock = React.useMemo(
    () => makeClock(data?.timezone ?? "UTC"),
    [data?.timezone],
  );
  const now = useNow();

  const [selected, setSelected] = React.useState<Meeting | null>(null);
  const [moveTarget, setMoveTarget] = React.useState<MoveTarget | null>(null);
  const [cancelTarget, setCancelTarget] = React.useState<Meeting | null>(null);
  const [picking, setPicking] = React.useState<Meeting | null>(null);
  const [slot, setSlot] = React.useState<FreeSlot | null>(null);
  const [arrange, setArrange] = React.useState<ArrangeTarget | null>(null);

  const actions = React.useMemo(
    () => ({
      open: (m: Meeting) => setSelected(m),
      move: (m: Meeting, startsAt?: string) => {
        setSelected(null);
        setMoveTarget({ meeting: m, startsAt });
      },
      cancel: (m: Meeting) => {
        setSelected(null);
        setCancelTarget(m);
      },
    }),
    [],
  );

  function pickSlot(free: FreeSlot) {
    if (picking) {
      setMoveTarget({ meeting: picking, startsAt: free.local });
      setPicking(null);
    } else if (reply) {
      setSlot(free);
    }
  }

  if (!allowed) {
    return (
      <div>
        <PageHeader title="Meetings" />
        <Notice tone="info" title="No access to meetings">
          Your role doesn&apos;t include pi&apos;s conversations. Ask your
          business owner if you need it.
        </Notice>
      </div>
    );
  }

  // Meetings the customer asked to move, wherever they are in the lists.
  const changes = data
    ? dedupe([
        ...data.upcoming,
        ...data.needs_outcome,
        ...data.meetings,
      ]).filter((m) => m.change_to && m.actionable)
    : [];

  return (
    <div>
      <PageHeader
        title="Meetings"
        description="Your week of customer meetings, next to your free time. Book a time, move or cancel a meeting and pi tells the customer on WhatsApp, in their language."
        action={
          data ? (
            <>
              <LiveBadge
                fetching={board.isFetching}
                updatedAt={board.dataUpdatedAt}
              />
              <CalendarChip state={data.calendar} />
            </>
          ) : null
        }
      />
      {board.isPending ? (
        <LoadingBlock rows={4} label="Loading meetings" />
      ) : board.isError && !data ? (
        <ErrorState
          message={errorText(board.error)}
          onRetry={() => board.refetch()}
        />
      ) : data ? (
        <div className="space-y-8">
          <Stats stats={data.stats} />
          <section aria-labelledby="week" className="space-y-3">
            <WeekNav
              data={data}
              clock={clock}
              loading={board.isFetching && board.isPlaceholderData}
              onChange={setStart}
            />
            {picking ? (
              <div
                className="flex flex-wrap items-center gap-2 rounded-lg border border-accent/40 bg-accent-soft px-3 py-2 text-sm text-accent-soft-foreground"
                role="status"
              >
                <Move className="size-4 shrink-0" aria-hidden />
                <span className="min-w-0 flex-1">
                  Pick a free time for {picking.customer_name}&apos;s meeting.
                </span>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setPicking(null)}
                >
                  <X className="size-4" aria-hidden /> Stop
                </Button>
              </div>
            ) : null}
            <WeekGrid
              data={data}
              clock={clock}
              now={now}
              picking={Boolean(picking)}
              canBook={reply}
              onMeeting={actions.open}
              onSlot={pickSlot}
            />
            <DayList
              data={data}
              clock={clock}
              picking={Boolean(picking)}
              canBook={reply}
              onMeeting={actions.open}
              onSlot={pickSlot}
            />
          </section>

          <Section
            id="waiting"
            title="Waiting for a time"
            count={data.waiting.length}
            empty="No one is waiting for a meeting time. When a customer asks for a meeting, it shows here."
          >
            {data.waiting.map((w) => (
              <WaitingCard
                key={w.request_id}
                item={w}
                clock={clock}
                reply={reply}
                onBook={(startsAt) => setArrange({ request: w, startsAt })}
              />
            ))}
          </Section>

          <Section
            id="changes"
            title="Time change asked"
            count={changes.length}
            empty="No customer has asked for another time."
          >
            {changes.map((m) => (
              <ChangeCard
                key={m.id}
                meeting={m}
                clock={clock}
                reply={reply}
                onMove={() => actions.move(m)}
              />
            ))}
          </Section>

          <Section
            id="next"
            title="Up next"
            count={data.upcoming.length}
            empty="Nothing booked yet. Pick a free time on the board to book a waiting request."
          >
            {data.upcoming.map((m) => (
              <MeetingCard
                key={m.id}
                meeting={m}
                clock={clock}
                now={now}
                reply={reply}
                actions={actions}
              />
            ))}
          </Section>

          <Section
            id="outcome"
            title="How did it go?"
            count={data.needs_outcome.length}
            empty="No meetings waiting for an outcome."
          >
            {data.needs_outcome.map((m) => (
              <li key={m.id}>
                <Card>
                  <CardSection className="space-y-3">
                    <MeetingSummary meeting={m} clock={clock} />
                    {reply && m.actionable ? <OutcomeForm meeting={m} /> : null}
                  </CardSection>
                </Card>
              </li>
            ))}
          </Section>

          <Section
            id="history"
            title="History"
            count={data.history.length}
            empty="Finished and cancelled meetings appear here."
          >
            {data.history.map((m) => (
              <HistoryRow key={m.id} meeting={m} clock={clock} />
            ))}
          </Section>
        </div>
      ) : null}

      <MeetingSheet
        meeting={selected}
        clock={clock}
        now={now}
        reply={reply}
        onClose={() => setSelected(null)}
        actions={actions}
      />
      {moveTarget && data ? (
        <MoveDialog
          key={`${moveTarget.meeting.id}:${moveTarget.startsAt ?? ""}`}
          target={moveTarget}
          free={data.free}
          clock={clock}
          onClose={() => setMoveTarget(null)}
          onPick={(m) => {
            setMoveTarget(null);
            setPicking(m);
            document
              .getElementById("week")
              ?.scrollIntoView({ behavior: "smooth", block: "start" });
          }}
        />
      ) : null}
      <CancelDialog
        key={cancelTarget?.id ?? "none"}
        meeting={cancelTarget}
        clock={clock}
        onClose={() => setCancelTarget(null)}
      />
      <SlotChooser
        slot={slot}
        waiting={data?.waiting ?? []}
        clock={clock}
        onClose={() => setSlot(null)}
        onChoose={(request) => {
          const startsAt = slot?.local;
          setSlot(null);
          setArrange({ request, startsAt });
        }}
      />
      <MeetingDialog
        key={
          arrange
            ? `${arrange.request.request_id}:${arrange.startsAt ?? ""}`
            : "none"
        }
        requestId={arrange?.request.request_id ?? null}
        question={arrange?.request.question ?? ""}
        googleMeet={data?.calendar === "connected"}
        initialStartsAt={arrange?.startsAt}
        onClose={() => setArrange(null)}
      />
    </div>
  );
}

function dedupe(items: Meeting[]): Meeting[] {
  const seen = new Set<string>();
  return items.filter((m) => (seen.has(m.id) ? false : (seen.add(m.id), true)));
}

type Actions = {
  open: (m: Meeting) => void;
  move: (m: Meeting, startsAt?: string) => void;
  cancel: (m: Meeting) => void;
};

// ---- header bits ------------------------------------------------------------------------

function LiveBadge({
  fetching,
  updatedAt,
}: {
  fetching: boolean;
  updatedAt: number;
}) {
  return (
    <span
      className="inline-flex min-h-10 items-center gap-1.5 rounded-full border border-border px-3 text-xs font-medium text-muted-foreground"
      title={`Refreshes every ${LIVE_EVERY_MS / 1000} seconds while open`}
    >
      <span className="relative flex size-2">
        <span
          className={cn(
            "absolute inline-flex size-full rounded-full bg-success opacity-60",
            fetching ? "animate-ping" : "motion-safe:animate-pulse",
          )}
        />
        <span className="relative inline-flex size-2 rounded-full bg-success" />
      </span>
      Live ·{" "}
      {fetching || !updatedAt
        ? "updating…"
        : new Date(updatedAt).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          })}
    </span>
  );
}

function CalendarChip({ state }: { state: Board["calendar"] }) {
  const base =
    "inline-flex min-h-10 items-center gap-1.5 rounded-full border px-3 text-xs font-medium";
  if (state === "connected") {
    return (
      <span
        className={cn(base, "border-success/30 bg-success-soft text-success")}
      >
        <CalendarCheck className="size-4" aria-hidden /> Google Calendar
        connected
      </span>
    );
  }
  if (state === "error") {
    return (
      <Link
        href="/my-pi/tools"
        className={cn(
          base,
          "border-warning/40 bg-warning-soft text-warning hover:underline",
        )}
      >
        <CalendarX className="size-4" aria-hidden /> Google Calendar: reconnect
      </Link>
    );
  }
  return (
    <Link
      href="/my-pi/tools"
      className={cn(
        base,
        "border-border text-foreground-secondary hover:border-accent/40 hover:text-foreground",
      )}
    >
      <CalendarClock className="size-4" aria-hidden /> Connect Google Calendar
    </Link>
  );
}

function Stats({ stats }: { stats: Board["stats"] }) {
  const tiles: {
    label: string;
    value: number;
    href?: string;
    warn?: boolean;
  }[] = [
    { label: "Today", value: stats.today },
    { label: "This week", value: stats.this_week },
    {
      label: "Waiting for a time",
      value: stats.waiting,
      href: "#waiting",
      warn: true,
    },
    {
      label: "Time change asked",
      value: stats.change_requests,
      href: "#changes",
      warn: true,
    },
    {
      label: "Needs outcome",
      value: stats.needs_outcome,
      href: "#outcome",
      warn: true,
    },
    { label: "Done", value: stats.done },
    { label: "No-shows", value: stats.no_show },
  ];
  return (
    <ul className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
      {tiles.map((t) => {
        const body = (
          <>
            <span className="block text-2xl font-semibold tabular-nums">
              {t.value}
            </span>
            <span className="mt-0.5 block text-xs text-muted-foreground">
              {t.label}
            </span>
          </>
        );
        const cls = cn(
          "block h-full rounded-xl border border-border bg-surface px-3 py-2.5",
          t.warn && t.value > 0 && "border-warning/40 bg-warning-soft/50",
        );
        return (
          <li key={t.label}>
            {t.href && t.value > 0 ? (
              <a href={t.href} className={cn(cls, "hover:border-accent/40")}>
                {body}
              </a>
            ) : (
              <div className={cls}>{body}</div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function WeekNav({
  data,
  clock,
  loading,
  onChange,
}: {
  data: Board;
  clock: Clock;
  loading: boolean;
  onChange: (start: string | null) => void;
}) {
  const last = addDays(data.start, data.days - 1);
  const today = clock.at(data.now).day;
  return (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <div className="min-w-0">
        <h2 id="week" className="scroll-mt-24 text-lg font-semibold">
          {clock.shortDay(data.start)} – {clock.shortDay(last)}
        </h2>
        <p className="text-xs text-muted-foreground">
          Times in {data.zone_name}
          {loading ? " · loading…" : ""}
        </p>
      </div>
      <div className="flex items-center gap-1">
        <Button
          size="sm"
          variant="secondary"
          aria-label="Previous week"
          onClick={() => onChange(addDays(data.start, -7))}
        >
          <ChevronLeft className="size-4" aria-hidden />
          <span className="hidden sm:inline">Prev</span>
        </Button>
        <Button
          size="sm"
          variant="secondary"
          disabled={data.start === today}
          onClick={() => onChange(null)}
        >
          Today
        </Button>
        <Button
          size="sm"
          variant="secondary"
          aria-label="Next week"
          onClick={() => onChange(addDays(data.start, 7))}
        >
          <span className="hidden sm:inline">Next</span>
          <ChevronRight className="size-4" aria-hidden />
        </Button>
      </div>
    </div>
  );
}

// ---- week grid (desktop) --------------------------------------------------------------

type Span = { top: number; bottom: number };

/** Minutes [from, to) an interval covers on `day`, or null. */
function spanOn(
  clock: Clock,
  day: string,
  startsAt: string,
  endsAt: string,
): Span | null {
  const a = clock.at(startsAt);
  const b = clock.at(endsAt);
  if (a.day > day || b.day < day) return null;
  const top = a.day === day ? a.minutes : 0;
  const bottom = b.day === day ? b.minutes : 1440;
  return bottom > top ? { top, bottom } : null;
}

function useGrid(data: Board, clock: Clock) {
  return React.useMemo(() => {
    const days = Array.from({ length: data.days }, (_, i) =>
      addDays(data.start, i),
    );
    let first = Infinity;
    let last = -Infinity;
    for (const day of days) {
      const rule = data.hours[weekday(day)];
      if (!rule?.open) continue;
      first = Math.min(first, toMinutes(rule.start));
      last = Math.max(last, toMinutes(rule.end));
    }
    if (!Number.isFinite(first) || last <= first) {
      first = 9 * 60;
      last = 18 * 60;
    }
    // Meetings and bookings outside meeting hours still show.
    for (const item of [...data.meetings, ...data.bookings]) {
      for (const day of days) {
        const span = spanOn(clock, day, item.starts_at, item.ends_at);
        if (!span) continue;
        first = Math.min(first, span.top);
        last = Math.max(last, span.bottom);
      }
    }
    first = Math.max(0, Math.floor(first / 30) * 30);
    last = Math.min(1440, Math.ceil(last / 30) * 30);
    return { days, first, last };
  }, [data, clock]);
}

/** Side-by-side lanes for overlapping blocks in one day column. */
function lanes<T extends Span>(
  items: T[],
): (T & { lane: number; of: number })[] {
  const sorted = [...items].sort((a, b) => a.top - b.top);
  const out: (T & { lane: number; of: number })[] = [];
  let cluster: (T & { lane: number; of: number })[] = [];
  let clusterEnd = -1;
  const flush = () => {
    const of = Math.max(1, ...cluster.map((c) => c.lane + 1));
    for (const c of cluster) c.of = of;
    out.push(...cluster);
    cluster = [];
  };
  for (const item of sorted) {
    if (item.top >= clusterEnd && cluster.length) flush();
    const used = new Set(
      cluster.filter((c) => c.bottom > item.top).map((c) => c.lane),
    );
    let lane = 0;
    while (used.has(lane)) lane++;
    cluster.push({ ...item, lane, of: 1 });
    clusterEnd = Math.max(clusterEnd, item.bottom);
  }
  if (cluster.length) flush();
  return out;
}

function WeekGrid({
  data,
  clock,
  now,
  picking,
  canBook,
  onMeeting,
  onSlot,
}: {
  data: Board;
  clock: Clock;
  now: number;
  picking: boolean;
  canBook: boolean;
  onMeeting: (m: Meeting) => void;
  onSlot: (slot: FreeSlot) => void;
}) {
  const { days, first, last } = useGrid(data, clock);
  const height = ((last - first) / 30) * ROW_PX;
  const y = (minutes: number) => (minutes - first) * PX_PER_MINUTE;
  const nowAt = clock.at(now);
  const rows = Array.from(
    { length: (last - first) / 30 },
    (_, i) => first + i * 30,
  );
  const hourLabel = (minutes: number) =>
    clock.localTime(
      `2000-01-01T${String(Math.floor(minutes / 60) % 24).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`,
    );

  return (
    <Card className="hidden overflow-hidden lg:block">
      <div
        className="grid border-b border-border"
        style={{
          gridTemplateColumns: `56px repeat(${days.length}, minmax(0, 1fr))`,
        }}
      >
        <div />
        {days.map((day) => {
          const label = clock.dayLabel(day);
          const open = data.hours[weekday(day)]?.open;
          const isToday = day === nowAt.day;
          return (
            <div
              key={day}
              className={cn(
                "border-s border-border px-2 py-2 text-center",
                !open && "bg-surface-sunken",
              )}
            >
              <p
                className={cn(
                  "text-xs font-medium text-muted-foreground",
                  isToday && "text-accent",
                )}
              >
                {label.weekday}
              </p>
              <p
                className={cn(
                  "text-sm font-semibold",
                  isToday &&
                    "mx-auto w-fit rounded-full bg-accent px-2 text-accent-foreground",
                )}
              >
                {label.date}
              </p>
              {!open ? (
                <p className="text-[11px] text-muted-foreground">Closed</p>
              ) : null}
            </div>
          );
        })}
      </div>
      <div
        className="relative grid"
        style={{
          gridTemplateColumns: `56px repeat(${days.length}, minmax(0, 1fr))`,
          height,
        }}
      >
        <div className="relative">
          {rows.map((m) =>
            m % 60 === 0 ? (
              <span
                key={m}
                className="absolute end-2 -translate-y-1/2 text-[11px] tabular-nums text-muted-foreground first:translate-y-0"
                style={{ top: y(m) }}
              >
                {hourLabel(m)}
              </span>
            ) : null,
          )}
        </div>
        {days.map((day) => {
          const rule = data.hours[weekday(day)];
          const open = rule?.open;
          const opens = open ? toMinutes(rule.start) : last;
          const closes = open ? toMinutes(rule.end) : last;
          const busy = data.busy
            .map((b) => spanOn(clock, day, b.starts_at, b.ends_at))
            .filter((s): s is Span => s !== null);
          const free = data.free
            .filter((f) => f.local.slice(0, 10) === day)
            .map((f) => {
              const top = toMinutes(f.local.slice(11, 16));
              return { slot: f, top, bottom: top + 30 };
            });
          const blocks = lanes([
            ...data.meetings.flatMap((m) => {
              const span = spanOn(clock, day, m.starts_at, m.ends_at);
              return span ? [{ ...span, meeting: m, booking: null }] : [];
            }),
            ...data.bookings.flatMap((b) => {
              const span = spanOn(clock, day, b.starts_at, b.ends_at);
              return span ? [{ ...span, meeting: null, booking: b }] : [];
            }),
          ]);
          return (
            <div
              key={day}
              className={cn(
                "relative border-s border-border",
                !open && "bg-surface-sunken",
              )}
            >
              {rows.map((m) => (
                <div
                  key={m}
                  aria-hidden
                  className={cn(
                    "absolute inset-x-0 border-t",
                    m % 60 === 0 ? "border-border" : "border-border/40",
                  )}
                  style={{ top: y(m) }}
                />
              ))}
              {open && opens > first ? (
                <div
                  aria-hidden
                  className="absolute inset-x-0 top-0 bg-surface-sunken"
                  style={{ height: y(Math.min(opens, last)) }}
                />
              ) : null}
              {open && closes < last ? (
                <div
                  aria-hidden
                  className="absolute inset-x-0 bottom-0 bg-surface-sunken"
                  style={{ top: y(Math.max(closes, first)) }}
                />
              ) : null}
              {busy.map((b, i) => (
                <div
                  key={i}
                  className="absolute inset-x-0.5 rounded-sm border border-border-strong/60 bg-surface-muted"
                  style={{
                    top: y(Math.max(b.top, first)),
                    height: Math.max(
                      4,
                      (Math.min(b.bottom, last) - Math.max(b.top, first)) *
                        PX_PER_MINUTE,
                    ),
                    backgroundImage:
                      "repeating-linear-gradient(135deg, var(--border-strong) 0 1px, transparent 1px 7px)",
                  }}
                  title="Busy in Google Calendar"
                >
                  <span className="sr-only">Busy in Google Calendar</span>
                </div>
              ))}
              {free.map(({ slot, top }) =>
                top >= first && top + 30 <= last ? (
                  <button
                    key={slot.local}
                    type="button"
                    disabled={!picking && !canBook}
                    onClick={() => onSlot(slot)}
                    className={cn(
                      "group absolute inset-x-0.5 flex items-center justify-center rounded-sm border border-success/20 bg-success-soft/50 text-success transition-colors hover:border-success/60 hover:bg-success-soft focus-visible:outline-2 focus-visible:outline-ring disabled:cursor-default disabled:hover:bg-success-soft/50",
                      picking && "border-success/50 bg-success-soft",
                    )}
                    style={{ top: y(top) + 1, height: ROW_PX - 2 }}
                    aria-label={`Free ${clock.localDayTime(slot.local)}. ${picking ? "Move the meeting here" : "Book this time"}`}
                  >
                    <Plus
                      className={cn(
                        "size-4 opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100",
                        picking && "opacity-70",
                      )}
                      aria-hidden
                    />
                  </button>
                ) : null,
              )}
              {blocks.map((block) => {
                const top = Math.max(block.top, first);
                const bottom = Math.min(block.bottom, last);
                const style = {
                  top: y(top) + 1,
                  height: Math.max(20, (bottom - top) * PX_PER_MINUTE - 2),
                  insetInlineStart: `calc(${(block.lane / block.of) * 100}% + 2px)`,
                  width: `calc(${100 / block.of}% - 4px)`,
                };
                if (block.meeting) {
                  const m = block.meeting;
                  const st = statusOf(m.status);
                  const How = howOf(m.how).icon;
                  return (
                    <button
                      key={m.id}
                      type="button"
                      onClick={() => onMeeting(m)}
                      className={cn(
                        "absolute z-10 overflow-hidden rounded-md border px-1.5 py-0.5 text-start text-[11px] leading-tight shadow-sm focus-visible:outline-2 focus-visible:outline-ring",
                        st.block,
                      )}
                      style={style}
                      aria-label={`${m.customer_name}, ${clock.dayTime(m.starts_at)}, ${st.label}`}
                    >
                      <span className="flex items-center gap-1 font-semibold">
                        <How className="size-3 shrink-0" aria-hidden />
                        <span className="truncate">{m.customer_name}</span>
                      </span>
                      <span className="block truncate opacity-80">
                        {clock.time(m.starts_at)}
                        {m.change_to ? " · new time asked" : ""}
                      </span>
                    </button>
                  );
                }
                const b = block.booking!;
                return (
                  <div
                    key={b.id}
                    className="absolute z-10 overflow-hidden rounded-md border border-info/40 bg-info-soft px-1.5 py-0.5 text-[11px] leading-tight text-info"
                    style={style}
                    title={`Booking: ${b.customer_name}, ${clock.time(b.starts_at)}–${clock.time(b.ends_at)}`}
                  >
                    <span className="block truncate font-semibold">
                      {b.customer_name}
                    </span>
                    <span className="block truncate opacity-80">
                      Booking · {clock.time(b.starts_at)}
                    </span>
                  </div>
                );
              })}
              {day === nowAt.day &&
              nowAt.minutes >= first &&
              nowAt.minutes <= last ? (
                <div
                  className="pointer-events-none absolute inset-x-0 z-20 flex items-center"
                  style={{ top: y(nowAt.minutes) }}
                  aria-hidden
                >
                  <span className="-ms-1 size-2 rounded-full bg-danger" />
                  <span className="h-0.5 flex-1 bg-danger" />
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
      <Legend />
    </Card>
  );
}

function Legend() {
  const item = (cls: string, label: string, style?: React.CSSProperties) => (
    <span className="inline-flex items-center gap-1.5">
      <span className={cn("size-3 rounded-sm border", cls)} style={style} />
      {label}
    </span>
  );
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 border-t border-border px-4 py-2 text-xs text-muted-foreground">
      {item("border-success/40 bg-success-soft", "Free")}
      {item("border-accent/50 bg-accent-soft", "Meeting")}
      {item("border-info/40 bg-info-soft", "Booking")}
      {item(
        "border-border-strong bg-surface-muted",
        "Busy in Google Calendar",
        {
          backgroundImage:
            "repeating-linear-gradient(135deg, var(--border-strong) 0 1px, transparent 1px 4px)",
        },
      )}
      {item("border-border bg-surface-sunken", "Closed")}
    </div>
  );
}

// ---- day list (phones and tablets) ------------------------------------------------------

function DayList({
  data,
  clock,
  picking,
  canBook,
  onMeeting,
  onSlot,
}: {
  data: Board;
  clock: Clock;
  picking: boolean;
  canBook: boolean;
  onMeeting: (m: Meeting) => void;
  onSlot: (slot: FreeSlot) => void;
}) {
  const days = Array.from({ length: data.days }, (_, i) =>
    addDays(data.start, i),
  );
  const today = clock.at(data.now).day;
  const [chosen, setChosen] = React.useState<string | null>(null);
  const day =
    chosen && days.includes(chosen)
      ? chosen
      : days.includes(today)
        ? today
        : days[0];
  const onDay = (iso: string) => clock.at(iso).day === day;
  const items = [
    ...data.meetings
      .filter((m) => onDay(m.starts_at))
      .map((m) => ({ at: m.starts_at, meeting: m, booking: null })),
    ...data.bookings
      .filter((b) => onDay(b.starts_at))
      .map((b) => ({ at: b.starts_at, meeting: null, booking: b })),
  ].sort((a, b) => a.at.localeCompare(b.at));
  const free = data.free.filter((f) => f.local.slice(0, 10) === day);
  const rule = data.hours[weekday(day)];
  const countOn = (d: string) =>
    data.meetings.filter(
      (m) => m.status !== "cancelled" && clock.at(m.starts_at).day === d,
    ).length;

  return (
    <div className="space-y-3 lg:hidden">
      <div className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
        <div className="flex w-max gap-1.5" role="tablist" aria-label="Day">
          {days.map((d) => {
            const label = clock.dayLabel(d);
            const n = countOn(d);
            const open = data.hours[weekday(d)]?.open;
            return (
              <button
                key={d}
                type="button"
                role="tab"
                aria-selected={d === day}
                onClick={() => setChosen(d)}
                className={cn(
                  "flex min-h-14 w-14 flex-col items-center justify-center rounded-xl border border-border bg-surface text-xs",
                  d === day &&
                    "border-accent bg-accent-soft text-accent-soft-foreground",
                  !open &&
                    d !== day &&
                    "bg-surface-sunken text-muted-foreground",
                )}
              >
                <span className="font-medium">
                  {d === today ? "Today" : label.weekday}
                </span>
                <span className="text-sm font-semibold">
                  {label.date.split(" ").find((p) => /\d/.test(p)) ??
                    label.date}
                </span>
                {n ? (
                  <span className="mt-0.5 size-1.5 rounded-full bg-accent" />
                ) : null}
              </button>
            );
          })}
        </div>
      </div>
      <Card>
        <CardSection className="space-y-4">
          <p className="text-sm font-semibold">
            {clock.dayLabel(day).weekday} {clock.dayLabel(day).date}
            <span className="ms-2 font-normal text-muted-foreground">
              {rule?.open
                ? `Open ${clock.localTime(`${day}T${rule.start}`)}–${clock.localTime(`${day}T${rule.end}`)}`
                : "Closed"}
            </span>
          </p>
          {items.length ? (
            <ul className="space-y-2">
              {items.map(({ meeting: m, booking: b }) =>
                m ? (
                  <li key={m.id}>
                    <button
                      type="button"
                      onClick={() => onMeeting(m)}
                      className={cn(
                        "flex w-full items-center gap-3 rounded-xl border px-3 py-2.5 text-start",
                        statusOf(m.status).block,
                      )}
                    >
                      <HowIcon how={m.how} />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-semibold">
                          {m.customer_name}
                        </span>
                        <span className="block truncate text-xs opacity-80">
                          {clock.time(m.starts_at)}–{clock.time(m.ends_at)} ·{" "}
                          {statusOf(m.status).label}
                        </span>
                      </span>
                      <ChevronRight className="size-4 shrink-0" aria-hidden />
                    </button>
                  </li>
                ) : b ? (
                  <li
                    key={b.id}
                    className="flex items-center gap-3 rounded-xl border border-info/40 bg-info-soft px-3 py-2.5 text-info"
                  >
                    <CalendarCheck className="size-4 shrink-0" aria-hidden />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-semibold">
                        {b.customer_name}
                      </span>
                      <span className="block truncate text-xs opacity-80">
                        Booking · {clock.time(b.starts_at)}–
                        {clock.time(b.ends_at)}
                      </span>
                    </span>
                    {b.conversation_id ? (
                      <Link
                        href={chatHref(b.conversation_id)}
                        className="shrink-0 text-xs font-medium underline-offset-2 hover:underline"
                      >
                        Chat
                      </Link>
                    ) : null}
                  </li>
                ) : null,
              )}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">
              No meetings or bookings this day.
            </p>
          )}
          {free.length ? (
            <div>
              <p className="mb-2 text-xs font-medium text-muted-foreground">
                {picking ? "Move the meeting to" : "Free times"}
              </p>
              <div className="flex flex-wrap gap-1.5">
                {free.map((f) => (
                  <button
                    key={f.local}
                    type="button"
                    disabled={!picking && !canBook}
                    onClick={() => onSlot(f)}
                    className="min-h-10 rounded-full border border-success/30 bg-success-soft/60 px-3 text-sm font-medium tabular-nums text-success hover:border-success/60 disabled:cursor-default"
                    aria-label={`Free ${clock.localDayTime(f.local)}. ${picking ? "Move the meeting here" : "Book this time"}`}
                  >
                    {clock.localTime(f.local)}
                  </button>
                ))}
              </div>
            </div>
          ) : rule?.open ? (
            <p className="text-xs text-muted-foreground">
              No free times left this day.
            </p>
          ) : null}
        </CardSection>
      </Card>
    </div>
  );
}

function HowIcon({ how }: { how: string }) {
  const Icon = howOf(how).icon;
  return <Icon className="size-4 shrink-0" aria-label={howOf(how).label} />;
}

// ---- sections ---------------------------------------------------------------------------

function Section({
  id,
  title,
  count,
  empty,
  children,
}: {
  id: string;
  title: string;
  count: number;
  empty: string;
  children: React.ReactNode;
}) {
  return (
    <section aria-labelledby={`${id}-title`} id={id} className="scroll-mt-24">
      <h2
        id={`${id}-title`}
        className="mb-3 flex items-center gap-2 text-lg font-semibold"
      >
        {title}
        {count ? <Badge>{count}</Badge> : null}
      </h2>
      {count ? (
        <ul className="space-y-3">{children}</ul>
      ) : (
        <p className="rounded-xl border border-dashed border-border px-4 py-5 text-center text-sm text-muted-foreground">
          {empty}
        </p>
      )}
    </section>
  );
}

function MeetingSummary({
  meeting: m,
  clock,
  now,
}: {
  meeting: Meeting;
  clock: Clock;
  now?: number;
}) {
  const st = statusOf(m.status);
  const how = howOf(m.how);
  return (
    <div className="flex items-start gap-3">
      <span className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent-soft-foreground">
        <how.icon className="size-4" aria-hidden />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="font-semibold">{m.customer_name}</span>
          <Badge tone={st.tone}>{st.label}</Badge>
        </div>
        <p className="mt-0.5 text-sm">
          {clock.dayTime(m.starts_at)} · {m.minutes} min · {how.label}
          {now !== undefined &&
          (m.status === "scheduled" || m.status === "live")
            ? ` · ${m.status === "live" ? "now" : fromNow(m.starts_at, now)}`
            : ""}
        </p>
        {m.topic ? (
          <p
            className="mt-0.5 truncate text-xs text-muted-foreground"
            data-user-text
          >
            {m.topic}
          </p>
        ) : null}
      </div>
    </div>
  );
}

function WaitingCard({
  item: w,
  clock,
  reply,
  onBook,
}: {
  item: Waiting;
  clock: Clock;
  reply: boolean;
  onBook: (startsAt?: string) => void;
}) {
  return (
    <li>
      <Card>
        <CardSection className="space-y-3">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="font-semibold">{w.customer_name}</span>
            {w.priority === "high" ? <Badge tone="danger">Urgent</Badge> : null}
            {w.how ? <Badge>{howOf(w.how).label}</Badge> : null}
          </div>
          {w.question ? (
            <p
              className="whitespace-pre-wrap break-words text-sm leading-relaxed"
              data-user-text
            >
              {w.question}
            </p>
          ) : null}
          <p className="text-xs text-muted-foreground">
            {w.asked_local
              ? `Asked for ${clock.localDayTime(w.asked_local)}`
              : "No time suggested yet"}
            {w.topic ? ` · ${w.topic}` : ""}
          </p>
          <div className="flex flex-wrap gap-2">
            {reply && w.asked_local ? (
              <Button
                size="sm"
                onClick={() => onBook(w.asked_local ?? undefined)}
              >
                <CalendarCheck className="size-4" aria-hidden /> Book{" "}
                {clock.localDayTime(w.asked_local)}
              </Button>
            ) : null}
            {reply ? (
              <Button
                size="sm"
                variant={w.asked_local ? "secondary" : "primary"}
                onClick={() => onBook(undefined)}
              >
                <CalendarClock className="size-4" aria-hidden /> Pick a time
              </Button>
            ) : null}
            <Button asChild size="sm" variant="ghost">
              <Link href={chatHref(w.conversation_id)}>
                <MessageCircle className="size-4" aria-hidden /> Open chat
              </Link>
            </Button>
          </div>
        </CardSection>
      </Card>
    </li>
  );
}

function ChangeCard({
  meeting: m,
  clock,
  reply,
  onMove,
}: {
  meeting: Meeting;
  clock: Clock;
  reply: boolean;
  onMove: () => void;
}) {
  const accept = useAction(
    () => post<Told>(`/pi/meetings/${m.conversation_id}/accept-change`),
    {
      invalidate: [["meetings"], ["requests"], ["conversations"]],
      onSuccess: (result) => toldToast("Meeting moved", result, true),
    },
  );
  return (
    <li>
      <Card>
        <CardSection className="space-y-3">
          <MeetingSummary meeting={m} clock={clock} />
          {m.change_to ? (
            <p className="rounded-lg bg-warning-soft px-3 py-2 text-sm text-warning">
              Asked to move it to <strong>{clock.dayTime(m.change_to)}</strong>
            </p>
          ) : null}
          <div className="flex flex-wrap gap-2">
            {reply ? (
              <Button
                size="sm"
                loading={accept.isPending}
                onClick={() => accept.mutate(undefined)}
              >
                <CalendarCheck className="size-4" aria-hidden /> Accept new time
              </Button>
            ) : null}
            {reply ? (
              <Button size="sm" variant="secondary" onClick={onMove}>
                <Move className="size-4" aria-hidden /> Move
              </Button>
            ) : null}
            <Button asChild size="sm" variant="ghost">
              <Link href={chatHref(m.conversation_id)}>
                <MessageCircle className="size-4" aria-hidden /> Open chat
              </Link>
            </Button>
          </div>
        </CardSection>
      </Card>
    </li>
  );
}

function RemindButton({ meeting: m }: { meeting: Meeting }) {
  const remind = useAction(
    () => post<Told>(`/pi/meetings/${m.conversation_id}/remind`),
    {
      success: "Reminder sent with the time and link.",
      invalidate: [["meetings"], ["conversations"]],
    },
  );
  return (
    <Button
      size="sm"
      variant="secondary"
      loading={remind.isPending}
      onClick={() => remind.mutate(undefined)}
    >
      <Send className="size-4" aria-hidden /> Remind
    </Button>
  );
}

function JoinButtons({ meeting: m }: { meeting: Meeting }) {
  if (!m.link) return null;
  return (
    <>
      <Button asChild size="sm">
        <a href={m.link} target="_blank" rel="noopener noreferrer">
          <ExternalLink className="size-4" aria-hidden /> Join
        </a>
      </Button>
      <Button
        size="sm"
        variant="ghost"
        onClick={() =>
          navigator.clipboard
            .writeText(m.link)
            .then(() => toast.success("Link copied"))
            .catch(() => toast.error("Couldn't copy the link"))
        }
      >
        <Copy className="size-4" aria-hidden /> Copy link
      </Button>
    </>
  );
}

function MeetingCard({
  meeting: m,
  clock,
  now,
  reply,
  actions,
}: {
  meeting: Meeting;
  clock: Clock;
  now: number;
  reply: boolean;
  actions: Actions;
}) {
  const act = reply && m.actionable;
  return (
    <li>
      <Card>
        <CardSection className="space-y-3">
          <button
            type="button"
            className="block w-full text-start"
            onClick={() => actions.open(m)}
          >
            <MeetingSummary meeting={m} clock={clock} now={now} />
          </button>
          <div className="flex flex-wrap gap-2">
            <JoinButtons meeting={m} />
            {act ? <RemindButton meeting={m} /> : null}
            {act ? (
              <Button
                size="sm"
                variant="secondary"
                onClick={() => actions.move(m)}
              >
                <Move className="size-4" aria-hidden /> Move
              </Button>
            ) : null}
            {act ? (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => actions.cancel(m)}
              >
                <X className="size-4" aria-hidden /> Cancel
              </Button>
            ) : null}
            <Button asChild size="sm" variant="ghost">
              <Link href={chatHref(m.conversation_id)}>
                <MessageCircle className="size-4" aria-hidden /> Chat
              </Link>
            </Button>
          </div>
        </CardSection>
      </Card>
    </li>
  );
}

function OutcomeForm({ meeting: m }: { meeting: Meeting }) {
  const [note, setNote] = React.useState("");
  const record = useAction(
    (status: "done" | "no_show") =>
      post<Told>(`/pi/meetings/${m.conversation_id}/outcome`, {
        status,
        note: note.trim(),
      }),
    {
      success: "Saved. pi will read this before its next reply.",
      invalidate: [["meetings"], ["conversations"]],
      onSuccess: () => setNote(""),
    },
  );
  const id = `outcome-${m.id}`;
  return (
    <div className="space-y-2">
      <Field
        label="What was agreed?"
        htmlFor={id}
        hint="pi will read this, so its next reply continues from the meeting."
        optional
      >
        <Textarea
          id={id}
          rows={2}
          maxLength={2000}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="e.g. They want the premium plan; send the proposal by Friday."
        />
      </Field>
      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          loading={record.isPending && record.variables === "done"}
          disabled={record.isPending}
          onClick={() => record.mutate("done")}
        >
          <CalendarCheck className="size-4" aria-hidden /> Done
        </Button>
        <Button
          size="sm"
          variant="danger"
          loading={record.isPending && record.variables === "no_show"}
          disabled={record.isPending}
          onClick={() => record.mutate("no_show")}
        >
          <CalendarX className="size-4" aria-hidden /> No-show
        </Button>
      </div>
    </div>
  );
}

function HistoryRow({ meeting: m, clock }: { meeting: Meeting; clock: Clock }) {
  const st = statusOf(m.status);
  return (
    <li className="flex items-start gap-3 rounded-xl border border-border bg-surface px-4 py-3">
      <History
        className="mt-0.5 size-4 shrink-0 text-muted-foreground"
        aria-hidden
      />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-sm font-semibold">{m.customer_name}</span>
          <Badge tone={st.tone}>{st.label}</Badge>
          <span className="text-xs text-muted-foreground">
            {clock.dayTime(m.starts_at)}
          </span>
        </div>
        {m.outcome ? (
          <p
            className="mt-1 whitespace-pre-wrap break-words text-sm text-foreground-secondary"
            data-user-text
          >
            {m.outcome}
          </p>
        ) : null}
      </div>
      <Link
        href={chatHref(m.conversation_id)}
        className="shrink-0 text-xs font-medium text-accent underline-offset-2 hover:underline"
      >
        Chat
      </Link>
    </li>
  );
}

// ---- dialogs ----------------------------------------------------------------------------

function MeetingSheet({
  meeting: m,
  clock,
  now,
  reply,
  onClose,
  actions,
}: {
  meeting: Meeting | null;
  clock: Clock;
  now: number;
  reply: boolean;
  onClose: () => void;
  actions: Actions;
}) {
  const act =
    reply &&
    Boolean(m?.actionable) &&
    !["done", "no_show", "cancelled"].includes(m?.status ?? "");
  const over = m?.status === "awaiting_outcome" || m?.status === "live";
  return (
    <Dialog
      open={m !== null}
      onOpenChange={(next) => (!next ? onClose() : null)}
    >
      {m ? (
        <DialogContent
          title={m.customer_name}
          description={`${clock.dayTime(m.starts_at)}–${clock.time(m.ends_at)} · ${m.minutes} minutes`}
        >
          <div className="space-y-4">
            <MeetingSummary meeting={m} clock={clock} now={now} />
            <dl className="grid gap-2 rounded-lg bg-surface-muted px-3 py-2 text-sm">
              {m.link ? (
                <Detail label="Link">
                  <a
                    href={m.link}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="break-all text-accent underline-offset-2 hover:underline"
                  >
                    {m.link}
                  </a>
                </Detail>
              ) : null}
              {m.place ? <Detail label="Where">{m.place}</Detail> : null}
              {m.note ? <Detail label="Note">{m.note}</Detail> : null}
              {m.phone ? <Detail label="Phone">{m.phone}</Detail> : null}
              <Detail label="Calendar">
                {m.calendar_event
                  ? "In your Google Calendar"
                  : "Not in a calendar"}
              </Detail>
              {m.outcome ? <Detail label="Outcome">{m.outcome}</Detail> : null}
            </dl>
            {m.change_to ? (
              <p className="rounded-lg bg-warning-soft px-3 py-2 text-sm text-warning">
                The customer asked to move it to{" "}
                <strong>{clock.dayTime(m.change_to)}</strong>.
              </p>
            ) : null}
            <div className="flex flex-wrap gap-2">
              <JoinButtons meeting={m} />
              {act ? <RemindButton meeting={m} /> : null}
              {act ? (
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => actions.move(m)}
                >
                  <Move className="size-4" aria-hidden /> Move
                </Button>
              ) : null}
              {act ? (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => actions.cancel(m)}
                >
                  <X className="size-4" aria-hidden /> Cancel
                </Button>
              ) : null}
              <Button asChild size="sm" variant="ghost">
                <Link href={chatHref(m.conversation_id)}>
                  <MessageCircle className="size-4" aria-hidden /> Open chat
                </Link>
              </Button>
            </div>
            {act && over ? (
              <div className="border-t border-border pt-4">
                <p className="mb-2 flex items-center gap-1.5 text-sm font-semibold">
                  <PiFace size={16} decorative /> How did it go?
                </p>
                <OutcomeForm meeting={m} />
              </div>
            ) : null}
            {!m.actionable ? (
              <p className="text-xs text-muted-foreground">
                This is an earlier meeting in this chat; only the current one
                can be changed.
              </p>
            ) : null}
          </div>
        </DialogContent>
      ) : null}
    </Dialog>
  );
}

function Detail({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="grid grid-cols-[5.5rem_minmax(0,1fr)] gap-2">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0 break-words" data-user-text>
        {children}
      </dd>
    </div>
  );
}

function MoveDialog({
  target,
  free,
  clock,
  onClose,
  onPick,
}: {
  target: MoveTarget;
  free: FreeSlot[];
  clock: Clock;
  onClose: () => void;
  onPick: (m: Meeting) => void;
}) {
  const m = target.meeting;
  const initial = target.startsAt ?? m.local;
  const [date, setDate] = React.useState(initial.slice(0, 10));
  const [time, setTime] = React.useState(initial.slice(11, 16));
  const [duration, setDuration] = React.useState(String(m.minutes || 30));
  const [notify, setNotify] = React.useState(true);
  const lengths = Array.from(
    new Set([15, 30, 45, 60, 90, 120, m.minutes || 30]),
  ).sort((a, b) => a - b);
  const picks = free.filter((f) => f.local !== m.local).slice(0, 6);
  const startsAt = `${date}T${time}`;
  const move = useAction(
    () =>
      post<Told>(`/pi/meetings/${m.conversation_id}/move`, {
        starts_at: startsAt,
        duration_minutes: Number(duration),
        notify,
      }),
    {
      invalidate: [["meetings"], ["conversations"]],
      onSuccess: (result) => {
        toldToast("Meeting moved", result, notify);
        onClose();
      },
    },
  );
  const ready = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(startsAt);
  return (
    <Dialog
      open
      onOpenChange={(next) => (!next && !move.isPending ? onClose() : null)}
    >
      <DialogContent
        title="Move the meeting"
        description={`${m.customer_name} · now ${clock.dayTime(m.starts_at)}. The link stays the same.`}
      >
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (ready) move.mutate(undefined);
          }}
        >
          {picks.length ? (
            <div>
              <p className="mb-2 text-sm font-medium">Free times</p>
              <div className="flex flex-wrap gap-1.5">
                {picks.map((f) => {
                  const on = f.local === startsAt;
                  return (
                    <button
                      key={f.local}
                      type="button"
                      aria-pressed={on}
                      onClick={() => {
                        setDate(f.local.slice(0, 10));
                        setTime(f.local.slice(11, 16));
                      }}
                      className={cn(
                        "min-h-10 rounded-full border border-success/30 bg-success-soft/60 px-3 text-sm font-medium text-success hover:border-success/60",
                        on &&
                          "border-success bg-success-soft ring-2 ring-success/30",
                      )}
                    >
                      {clock.localDayTime(f.local)}
                    </button>
                  );
                })}
              </div>
            </div>
          ) : null}
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Date" htmlFor="move-date">
              <Input
                id="move-date"
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
              />
            </Field>
            <Field label="Time" htmlFor="move-time">
              <Input
                id="move-time"
                type="time"
                value={time}
                onChange={(e) => setTime(e.target.value)}
              />
            </Field>
            <Field label="Length" htmlFor="move-duration">
              <Select
                id="move-duration"
                value={duration}
                onChange={(e) => setDuration(e.target.value)}
              >
                {lengths.map((n) => (
                  <option key={n} value={n}>
                    {n} minutes
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <TellCustomer id="move-notify" value={notify} onChange={setNotify} />
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:items-center">
            <Button
              type="button"
              variant="link"
              className="sm:me-auto"
              onClick={() => onPick(m)}
              disabled={move.isPending}
            >
              <Clock className="size-4" aria-hidden /> Pick on the board
            </Button>
            <Button
              type="button"
              variant="secondary"
              onClick={onClose}
              disabled={move.isPending}
            >
              Keep the time
            </Button>
            <Button type="submit" loading={move.isPending} disabled={!ready}>
              Move meeting
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function TellCustomer({
  id,
  value,
  onChange,
}: {
  id: string;
  value: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <div className="flex items-start justify-between gap-3 rounded-lg border border-border px-3 py-2.5">
      <label htmlFor={id} className="text-sm">
        <span className="font-medium">Tell the customer</span>
        <span className="block text-xs text-muted-foreground">
          pi messages them on WhatsApp, in their language. Only possible within
          24 hours of their last message.
        </span>
      </label>
      <Switch
        id={id}
        checked={value}
        onCheckedChange={onChange}
        label="Tell the customer"
      />
    </div>
  );
}

function CancelDialog({
  meeting: m,
  clock,
  onClose,
}: {
  meeting: Meeting | null;
  clock: Clock;
  onClose: () => void;
}) {
  const [reason, setReason] = React.useState("");
  const [notify, setNotify] = React.useState(true);
  const cancel = useAction(
    () =>
      post<Told>(`/pi/meetings/${m?.conversation_id}/cancel`, {
        reason: reason.trim(),
        notify,
      }),
    {
      invalidate: [["meetings"], ["conversations"]],
      onSuccess: (result) => {
        toldToast("Meeting cancelled", result, notify);
        onClose();
      },
    },
  );
  return (
    <Dialog
      open={m !== null}
      onOpenChange={(next) => (!next && !cancel.isPending ? onClose() : null)}
    >
      {m ? (
        <DialogContent
          title="Cancel the meeting?"
          description={`${m.customer_name} · ${clock.dayTime(m.starts_at)}${m.calendar_event ? ". It's removed from your Google Calendar too." : "."}`}
        >
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              cancel.mutate(undefined);
            }}
          >
            <Field
              label="Reason for the customer"
              htmlFor="cancel-reason"
              optional
            >
              <Textarea
                id="cancel-reason"
                rows={2}
                maxLength={300}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="e.g. Our designer is unwell; we'll suggest a new time."
              />
            </Field>
            <TellCustomer
              id="cancel-notify"
              value={notify}
              onChange={setNotify}
            />
            <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
              <Button
                type="button"
                variant="secondary"
                onClick={onClose}
                disabled={cancel.isPending}
              >
                Keep it
              </Button>
              <Button type="submit" variant="danger" loading={cancel.isPending}>
                Cancel meeting
              </Button>
            </div>
          </form>
        </DialogContent>
      ) : null}
    </Dialog>
  );
}

function SlotChooser({
  slot,
  waiting,
  clock,
  onClose,
  onChoose,
}: {
  slot: FreeSlot | null;
  waiting: Waiting[];
  clock: Clock;
  onClose: () => void;
  onChoose: (request: Waiting) => void;
}) {
  return (
    <Dialog
      open={slot !== null}
      onOpenChange={(next) => (!next ? onClose() : null)}
    >
      {slot ? (
        <DialogContent
          title="Book this time for…"
          description={`${clock.localDayTime(slot.local)}. Choose who is waiting for a meeting.`}
        >
          {waiting.length ? (
            <ul className="space-y-2">
              {waiting.map((w) => (
                <li key={w.request_id}>
                  <button
                    type="button"
                    onClick={() => onChoose(w)}
                    className="flex w-full items-start gap-3 rounded-xl border border-border px-3 py-2.5 text-start hover:border-accent/40 hover:bg-accent-soft/40"
                  >
                    <CalendarClock
                      className="mt-0.5 size-4 shrink-0 text-accent"
                      aria-hidden
                    />
                    <span className="min-w-0 flex-1">
                      <span className="flex flex-wrap items-center gap-1.5 text-sm font-semibold">
                        {w.customer_name}
                        {w.priority === "high" ? (
                          <Badge tone="danger">Urgent</Badge>
                        ) : null}
                      </span>
                      {w.question ? (
                        <span
                          className="line-clamp-2 block text-xs text-muted-foreground"
                          data-user-text
                        >
                          {w.question}
                        </span>
                      ) : null}
                      {w.asked_local ? (
                        <span className="block text-xs text-muted-foreground">
                          Asked for {clock.localDayTime(w.asked_local)}
                        </span>
                      ) : null}
                    </span>
                    <ChevronRight
                      className="mt-0.5 size-4 shrink-0 text-muted-foreground"
                      aria-hidden
                    />
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState
              icon={<CalendarClock className="size-6" aria-hidden />}
              title="No one is waiting for a time"
            >
              When a customer asks pi for a meeting, they show here and you can
              book them into a free time.
            </EmptyState>
          )}
        </DialogContent>
      ) : null}
    </Dialog>
  );
}
