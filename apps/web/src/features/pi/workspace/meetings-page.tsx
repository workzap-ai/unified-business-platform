"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { keepPreviousData } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  ArrowRight,
  ArrowRightLeft,
  Bell,
  CalendarCheck,
  CalendarClock,
  CalendarDays,
  CalendarX,
  ChevronLeft,
  ChevronRight,
  CircleCheck,
  Clock,
  Copy,
  ExternalLink,
  Globe,
  History,
  Hourglass,
  Link2,
  MapPin,
  MessageCircle,
  MousePointerClick,
  Phone,
  UserX,
  Video,
  X,
  type LucideIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/display";
import { Checkbox, Label } from "@/components/ui/controls";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  SheetContent,
} from "@/components/ui/overlays";
import {
  PageHeader,
  PageShell,
  RequirePermission,
} from "@/components/app/page";
import { EmptyState, ErrorState, Notice } from "@/components/app/states";
import { PageSkeleton } from "@/components/app/page-skeleton";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import { formatTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import {
  WEEKDAYS,
  meetingsService,
  type Booking,
  type DayHours,
  type FreeSlot,
  type Meeting,
  type MeetingBoard,
  type MeetingChangeResult,
  type MeetingStatus,
  type WaitingRequest,
  type Weekday,
} from "../meetings-service";
import { MeetingDialog } from "./meeting-dialog";

const LIVE_EVERY_MS = 20_000;
const KEY = ["pi", "meetings"];
/** Pixels per 30 minutes in the week grid. */
const ROW = 28;
const NOT_TOLD =
  "The customer wasn't messaged (WhatsApp 24-hour window closed); call or message them.";

const STATUS: Record<
  MeetingStatus,
  {
    label: string;
    tone: "primary" | "success" | "warning" | "neutral" | "danger";
    block: string;
  }
> = {
  scheduled: {
    label: "Scheduled",
    tone: "primary",
    block:
      "border-l-primary bg-primary-soft text-primary-soft-foreground hover:brightness-95",
  },
  live: {
    label: "Happening now",
    tone: "success",
    block: "border-l-success bg-success-soft text-success hover:brightness-95",
  },
  awaiting_outcome: {
    label: "How did it go?",
    tone: "warning",
    block: "border-l-warning bg-warning-soft text-warning hover:brightness-95",
  },
  done: {
    label: "Done",
    tone: "neutral",
    block:
      "border-l-border-strong bg-surface-muted text-muted-foreground hover:bg-surface-sunken",
  },
  no_show: {
    label: "No-show",
    tone: "danger",
    block:
      "border-l-danger/60 bg-danger-soft/60 text-danger/90 hover:bg-danger-soft",
  },
  cancelled: {
    label: "Cancelled",
    tone: "neutral",
    block:
      "border-l-border bg-surface-muted/70 text-muted-foreground line-through opacity-75 hover:opacity-100",
  },
};

const chatHref = (conversationId: string) =>
  `/pi/inbox?conversation=${encodeURIComponent(conversationId)}`;

function howOf(how: string): { label: string; icon: LucideIcon } {
  if (how === "google_meet") return { label: "Google Meet", icon: Video };
  if (how === "video") return { label: "Video call", icon: Video };
  if (how === "link") return { label: "Online link", icon: Link2 };
  if (how === "in_person") return { label: "In person", icon: MapPin };
  return { label: "Meeting", icon: CalendarClock };
}

/* Business-time helpers ------------------------------------------------------ */

const formatters = new Map<string, Intl.DateTimeFormat>();
function fmt(tz: string, options: Intl.DateTimeFormatOptions) {
  const key = `${tz}|${JSON.stringify(options)}`;
  let f = formatters.get(key);
  if (!f) {
    try {
      f = new Intl.DateTimeFormat("en-GB", { ...options, timeZone: tz });
    } catch {
      f = new Intl.DateTimeFormat("en-GB", { ...options, timeZone: "UTC" });
    }
    formatters.set(key, f);
  }
  return f;
}

const TIME: Intl.DateTimeFormatOptions = {
  hour: "numeric",
  minute: "2-digit",
  hour12: true,
};

function timeOf(tz: string, iso: string) {
  return fmt(tz, TIME).format(new Date(iso));
}

function dateTimeOf(tz: string, iso: string) {
  return fmt(tz, {
    weekday: "short",
    day: "numeric",
    month: "short",
    ...TIME,
  }).format(new Date(iso));
}

/** The business-local calendar day and minute-of-day of an instant. */
function localParts(tz: string, iso: string) {
  const parts = fmt(tz, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(iso));
  const get = (type: string) =>
    parts.find((p) => p.type === type)?.value ?? "0";
  return {
    date: `${get("year")}-${get("month")}-${get("day")}`,
    min: (Number(get("hour")) % 24) * 60 + Number(get("minute")),
  };
}

const ymdDate = (ymd: string) => new Date(`${ymd}T12:00:00Z`);

function addDays(ymd: string, n: number) {
  const d = ymdDate(ymd);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

function weekdayOf(ymd: string): Weekday {
  return WEEKDAYS[(ymdDate(ymd).getUTCDay() + 6) % 7];
}

function dayText(ymd: string, options: Intl.DateTimeFormatOptions) {
  return fmt("UTC", options).format(ymdDate(ymd));
}

/** Minute-of-day as a clock label ("9:30 am"). */
function clock(min: number) {
  return fmt("UTC", TIME).format(
    new Date(Date.UTC(2000, 0, 1, Math.floor(min / 60) % 24, min % 60)),
  );
}

function toMin(hhmm: string) {
  const [h, m] = hhmm.split(":").map(Number);
  return (h || 0) * 60 + (m || 0);
}

/** "in 20 min", "in 3 h", "today 4:00 pm", "tomorrow 11:00 am", "Mon 19 Oct, 9:00 am". */
function whenLabel(tz: string, iso: string, nowIso: string) {
  const diff = (new Date(iso).getTime() - new Date(nowIso).getTime()) / 60_000;
  if (diff <= 0) return "now";
  if (diff < 60) return `in ${Math.max(1, Math.round(diff))} min`;
  if (diff < 6 * 60) return `in ${Math.round(diff / 60)} h`;
  const at = localParts(tz, iso).date;
  const today = localParts(tz, nowIso).date;
  const time = timeOf(tz, iso);
  if (at === today) return `today ${time}`;
  if (at === addDays(today, 1)) return `tomorrow ${time}`;
  return `${dayText(at, { weekday: "short", day: "numeric", month: "short" })}, ${time}`;
}

/** The part of [start, end) that falls on `day`, in minutes of that day. */
function span(
  tz: string,
  day: string,
  startIso: string,
  endIso: string,
): [number, number] | null {
  const s = localParts(tz, startIso);
  const e = localParts(tz, endIso);
  if (s.date > day || e.date < day) return null;
  const a = s.date < day ? 0 : s.min;
  const b = e.date > day ? 1440 : e.min;
  return b > a ? [a, b] : null;
}

/* Week model ----------------------------------------------------------------- */

type Block = { key: string; start: number; end: number } & (
  { kind: "meeting"; meeting: Meeting } | { kind: "booking"; booking: Booking }
);
type Placed = Block & { lane: number; lanes: number };

/** Side-by-side lanes for blocks that overlap. */
function layout(blocks: Block[]): Placed[] {
  const sorted = [...blocks].sort((a, b) => a.start - b.start || b.end - a.end);
  const out: Placed[] = [];
  let cluster: Placed[] = [];
  let laneEnds: number[] = [];
  let clusterEnd = -1;
  const flush = () => {
    for (const p of cluster) p.lanes = laneEnds.length;
    out.push(...cluster);
    cluster = [];
    laneEnds = [];
  };
  for (const block of sorted) {
    if (block.start >= clusterEnd) flush();
    let lane = laneEnds.findIndex((end) => end <= block.start);
    if (lane === -1) {
      lane = laneEnds.length;
      laneEnds.push(block.end);
    } else laneEnds[lane] = block.end;
    cluster.push({ ...block, lane, lanes: 1 });
    clusterEnd = Math.max(clusterEnd, block.end);
  }
  flush();
  return out;
}

type DayModel = {
  day: string;
  rule: DayHours;
  blocks: Placed[];
  busy: [number, number][];
  free: { slot: FreeSlot; start: number }[];
};

function buildWeek(data: MeetingBoard) {
  const tz = data.timezone;
  const days = Array.from({ length: Math.max(1, data.days) }, (_, i) =>
    addDays(data.start, i),
  );
  const now = localParts(tz, data.now);
  const perDay: DayModel[] = days.map((day) => {
    const blocks: Block[] = [];
    for (const m of data.meetings) {
      const s = span(tz, day, m.starts_at, m.ends_at);
      if (s)
        blocks.push({
          kind: "meeting",
          key: `m-${m.id}`,
          start: s[0],
          end: s[1],
          meeting: m,
        });
    }
    for (const b of data.bookings) {
      const s = span(tz, day, b.starts_at, b.ends_at);
      if (s)
        blocks.push({
          kind: "booking",
          key: `b-${b.id}`,
          start: s[0],
          end: s[1],
          booking: b,
        });
    }
    return {
      day,
      rule: data.hours[weekdayOf(day)],
      blocks: layout(blocks),
      busy: data.busy
        .map((b) => span(tz, day, b.starts_at, b.ends_at))
        .filter((s): s is [number, number] => s !== null),
      free: data.free
        .filter((f) => f.local.slice(0, 10) === day)
        .map((slot) => ({ slot, start: toMin(slot.local.slice(11, 16)) })),
    };
  });
  let from = Infinity;
  let to = -Infinity;
  for (const d of perDay)
    if (d.rule.open) {
      from = Math.min(from, toMin(d.rule.start));
      to = Math.max(to, toMin(d.rule.end));
    }
  if (!Number.isFinite(from) || to <= from) {
    from = 9 * 60;
    to = 18 * 60;
  }
  for (const d of perDay)
    for (const b of d.blocks) {
      from = Math.min(from, b.start);
      to = Math.max(to, b.end);
    }
  from = Math.floor(from / 30) * 30;
  to = Math.min(1440, Math.ceil(to / 30) * 30);
  return { tz, days, today: now.date, nowMin: now.min, perDay, from, to };
}
type Week = ReturnType<typeof buildWeek>;

/* Page ----------------------------------------------------------------------- */

type MoveMode = { meeting: Meeting; minutes: number; notify: boolean };
type BookFor = { id: string; question: string; startsAt: string | null };

export function MeetingsPage() {
  return (
    <RequirePermission permission="pi.read" area="pi">
      <MeetingsView />
    </RequirePermission>
  );
}

function MeetingsView() {
  const { can } = useSession();
  const canAct = can("pi.inbox.reply");
  const [start, setStart] = useState<string | null>(null);
  const [mobileDay, setMobileDay] = useState<string | null>(null);
  const [detail, setDetail] = useState<Meeting | null>(null);
  const [moveFor, setMoveFor] = useState<Meeting | null>(null);
  const [cancelFor, setCancelFor] = useState<Meeting | null>(null);
  const [moveMode, setMoveMode] = useState<MoveMode | null>(null);
  const [confirmSlot, setConfirmSlot] = useState<FreeSlot | null>(null);
  const [chooseSlot, setChooseSlot] = useState<FreeSlot | null>(null);
  const [bookFor, setBookFor] = useState<BookFor | null>(null);

  const query = useScopedQuery(
    [...KEY, start],
    () => meetingsService.board(start),
    { refetchInterval: LIVE_EVERY_MS, placeholderData: keepPreviousData },
  );
  const data = query.data;
  const week = useMemo(() => (data ? buildWeek(data) : null), [data]);

  const changes = useMemo(() => {
    if (!data) return [];
    const seen = new Set<string>();
    return [...data.upcoming, ...data.meetings, ...data.needs_outcome].filter(
      (m) => {
        if (!m.change_to || !m.actionable || seen.has(m.id)) return false;
        seen.add(m.id);
        return true;
      },
    );
  }, [data]);

  function onSlot(slot: FreeSlot) {
    if (moveMode) setConfirmSlot(slot);
    else if (canAct && data && data.waiting.length > 0) setChooseSlot(slot);
    else
      toast(`Free at ${slot.label}`, {
        description:
          "Nobody is waiting for a time. pi offers free times like this when a customer asks to meet.",
      });
  }

  function startMove(meeting: Meeting) {
    setDetail(null);
    setMoveFor(meeting);
  }

  return (
    <PageShell>
      <PageHeader
        title="Meetings"
        description="Every meeting pi and your team arranged, your free time, and who's waiting for a time."
        actions={
          <>
            <LiveBadge
              fetching={query.isFetching}
              updatedAt={query.dataUpdatedAt}
            />
            {data && <CalendarChip state={data.calendar} />}
          </>
        }
      >
        {data?.zone_name && (
          <p className="mt-2 inline-flex items-center gap-1.5 text-xs text-muted-foreground">
            <Globe className="size-3.5" aria-hidden="true" />
            Times shown in {data.zone_name}
          </p>
        )}
      </PageHeader>
      {query.isError && !data ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : !data || !week ? (
        <PageSkeleton variant="dashboard" />
      ) : (
        <div className="space-y-5">
          <StatCards
            data={data}
            onToday={() => {
              setStart(null);
              setMobileDay(null);
            }}
          />
          <section id="meet-board" className="scroll-mt-20 space-y-3">
            <WeekNav
              week={week}
              loading={query.isFetching && query.isPlaceholderData}
              onPrev={() => setStart(addDays(data.start, -7))}
              onNext={() => setStart(addDays(data.start, 7))}
              onToday={() => {
                setStart(null);
                setMobileDay(null);
              }}
              isToday={start === null}
            />
            {moveMode && (
              <div className="flex flex-wrap items-center gap-2 rounded-lg border border-primary/30 bg-primary-soft px-3 py-2 text-[13px] text-primary-soft-foreground">
                <MousePointerClick
                  className="size-4 shrink-0"
                  aria-hidden="true"
                />
                <span className="min-w-0 flex-1">
                  Pick a free time for{" "}
                  <strong>{moveMode.meeting.customer_name}</strong>
                  {"'"}s meeting (now {moveMode.meeting.label}).
                </span>
                <Button
                  size="xs"
                  variant="secondary"
                  onClick={() => setMoveMode(null)}
                >
                  <X aria-hidden="true" /> Stop moving
                </Button>
              </div>
            )}
            <WeekGrid
              week={week}
              data={data}
              moving={moveMode !== null}
              onMeeting={setDetail}
              onSlot={onSlot}
            />
            <DayList
              week={week}
              data={data}
              day={mobileDay}
              onDay={setMobileDay}
              moving={moveMode !== null}
              onMeeting={setDetail}
              onSlot={onSlot}
            />
            <Legend />
          </section>
          <div className="grid gap-5 lg:grid-cols-2">
            <div className="space-y-5">
              <WaitingSection data={data} canAct={canAct} onBook={setBookFor} />
              <ChangesSection
                tz={data.timezone}
                meetings={changes}
                canAct={canAct}
                onMove={startMove}
              />
              <UpNextSection
                data={data}
                canAct={canAct}
                onOpen={setDetail}
                onMove={startMove}
                onCancel={setCancelFor}
              />
            </div>
            <div className="space-y-5">
              <OutcomeSection data={data} canAct={canAct} onOpen={setDetail} />
              <HistorySection data={data} onOpen={setDetail} />
            </div>
          </div>
        </div>
      )}

      <Dialog
        open={detail !== null}
        onOpenChange={(o) => !o && setDetail(null)}
      >
        <SheetContent width="md">
          {detail && data && (
            <MeetingDetail
              meeting={detail}
              data={data}
              canAct={canAct}
              onMove={() => startMove(detail)}
              onCancel={() => {
                setDetail(null);
                setCancelFor(detail);
              }}
              onDone={() => setDetail(null)}
            />
          )}
        </SheetContent>
      </Dialog>
      {moveFor && data && (
        <MoveDialog
          key={moveFor.id}
          meeting={moveFor}
          data={data}
          onClose={() => setMoveFor(null)}
          onPickOnBoard={(minutes, notify) => {
            setMoveMode({ meeting: moveFor, minutes, notify });
            setMoveFor(null);
            document
              .getElementById("meet-board")
              ?.scrollIntoView({ behavior: "smooth", block: "start" });
          }}
        />
      )}
      {cancelFor && (
        <CancelDialog
          key={cancelFor.id}
          meeting={cancelFor}
          onClose={() => setCancelFor(null)}
        />
      )}
      {moveMode && confirmSlot && (
        <ConfirmMoveDialog
          key={confirmSlot.local}
          mode={moveMode}
          slot={confirmSlot}
          onClose={() => setConfirmSlot(null)}
          onMoved={() => {
            setConfirmSlot(null);
            setMoveMode(null);
          }}
        />
      )}
      {chooseSlot && data && (
        <SlotChooser
          slot={chooseSlot}
          waiting={data.waiting}
          onClose={() => setChooseSlot(null)}
          onPick={(w) => {
            setChooseSlot(null);
            setBookFor({
              id: w.request_id,
              question: w.question,
              startsAt: chooseSlot.local,
            });
          }}
        />
      )}
      <MeetingDialog
        key={bookFor ? `${bookFor.id}-${bookFor.startsAt ?? ""}` : "none"}
        request={bookFor}
        initialStartsAt={bookFor?.startsAt ?? null}
        googleMeet={data?.calendar === "connected"}
        onClose={() => setBookFor(null)}
      />
    </PageShell>
  );
}

/* Header bits ---------------------------------------------------------------- */

function CalendarChip({ state }: { state: MeetingBoard["calendar"] }) {
  if (state === "connected")
    return (
      <Badge tone="success" className="py-1">
        <CalendarCheck aria-hidden="true" /> Google Calendar connected
      </Badge>
    );
  if (state === "error")
    return (
      <Link href="/pi/setup" className="rounded-full">
        <Badge tone="warning" className="py-1 hover:brightness-95">
          <CalendarX aria-hidden="true" /> Calendar needs reconnecting
        </Badge>
      </Link>
    );
  return (
    <Link href="/pi/setup" className="rounded-full">
      <Badge tone="neutral" className="py-1 hover:bg-surface-sunken">
        <CalendarDays aria-hidden="true" /> No calendar — busy times not checked
      </Badge>
    </Link>
  );
}

function LiveBadge({
  fetching,
  updatedAt,
}: {
  fetching: boolean;
  updatedAt: number;
}) {
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border border-border px-2.5 py-1 text-xs font-medium text-muted-foreground"
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
      {fetching || !updatedAt ? "updating…" : formatTime(new Date(updatedAt))}
    </span>
  );
}

function scrollTo(id: string) {
  document
    .getElementById(id)
    ?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function StatCards({
  data,
  onToday,
}: {
  data: MeetingBoard;
  onToday: () => void;
}) {
  const s = data.stats;
  const cards: {
    label: string;
    value: number;
    icon: LucideIcon;
    target: string;
    alert?: "warning" | "danger";
    onClick?: () => void;
  }[] = [
    {
      label: "Today",
      value: s.today,
      icon: CalendarClock,
      target: "meet-board",
      onClick: onToday,
    },
    {
      label: "This week",
      value: s.this_week,
      icon: CalendarDays,
      target: "meet-board",
    },
    {
      label: "Waiting for a time",
      value: s.waiting,
      icon: Hourglass,
      target: "meet-waiting",
      alert: "warning",
    },
    {
      label: "Time change asked",
      value: s.change_requests,
      icon: ArrowRightLeft,
      target: "meet-change",
      alert: "warning",
    },
    {
      label: "Needs outcome",
      value: s.needs_outcome,
      icon: MessageCircle,
      target: "meet-outcome",
      alert: "warning",
    },
    {
      label: "Done this week",
      value: s.done,
      icon: CircleCheck,
      target: "meet-history",
    },
    {
      label: "No-shows",
      value: s.no_show,
      icon: UserX,
      target: "meet-history",
      alert: "danger",
    },
  ];
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 xl:grid-cols-7">
      {cards.map((c) => {
        const hot = c.alert && c.value > 0;
        return (
          <button
            key={c.label}
            type="button"
            onClick={() => {
              c.onClick?.();
              scrollTo(c.target);
            }}
            className={cn(
              "flex min-w-0 flex-col gap-1 rounded-xl border border-border bg-surface px-3 py-2.5 text-left shadow-sm transition-colors hover:bg-surface-muted",
              hot && c.alert === "warning" && "border-warning/40",
              hot && c.alert === "danger" && "border-danger/40",
            )}
          >
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <c.icon
                className={cn(
                  "size-3.5 shrink-0",
                  hot && c.alert === "warning" && "text-warning",
                  hot && c.alert === "danger" && "text-danger",
                )}
                aria-hidden="true"
              />
              <span className="truncate">{c.label}</span>
            </span>
            <span
              className={cn(
                "text-xl font-semibold tabular-nums",
                hot && c.alert === "warning" && "text-warning",
                hot && c.alert === "danger" && "text-danger",
              )}
            >
              {c.value}
            </span>
          </button>
        );
      })}
    </div>
  );
}

function WeekNav({
  week,
  loading,
  onPrev,
  onNext,
  onToday,
  isToday,
}: {
  week: Week;
  loading: boolean;
  onPrev: () => void;
  onNext: () => void;
  onToday: () => void;
  isToday: boolean;
}) {
  const first = week.days[0];
  const last = week.days[week.days.length - 1];
  const sameMonth = first.slice(0, 7) === last.slice(0, 7);
  const label = `${dayText(first, {
    weekday: "short",
    day: "numeric",
    ...(sameMonth ? {} : { month: "short" }),
  })} – ${dayText(last, { weekday: "short", day: "numeric", month: "short" })}`;
  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="flex items-center gap-1">
        <Button
          size="icon-sm"
          variant="secondary"
          onClick={onPrev}
          aria-label="Previous week"
        >
          <ChevronLeft aria-hidden="true" />
        </Button>
        <Button
          size="sm"
          variant="secondary"
          onClick={onToday}
          disabled={isToday}
        >
          Today
        </Button>
        <Button
          size="icon-sm"
          variant="secondary"
          onClick={onNext}
          aria-label="Next week"
        >
          <ChevronRight aria-hidden="true" />
        </Button>
      </div>
      <h2
        className={cn(
          "text-[15px] font-semibold tracking-tight",
          loading && "opacity-60",
        )}
      >
        {label}
      </h2>
    </div>
  );
}

function Legend() {
  const items = [
    ["bg-primary-soft border-l-primary", "Scheduled"],
    ["bg-success-soft border-l-success", "Happening now"],
    ["bg-warning-soft border-l-warning", "Needs outcome"],
    ["bg-info-soft border-l-info", "Booking"],
    ["bg-success-soft/50 border-l-success/40", "Free"],
  ] as const;
  return (
    <ul className="hidden flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground lg:flex">
      {items.map(([cls, label]) => (
        <li key={label} className="flex items-center gap-1.5">
          <span
            className={cn("h-3 w-4 rounded-[3px] border-l-[3px]", cls)}
            aria-hidden="true"
          />
          {label}
        </li>
      ))}
      <li className="flex items-center gap-1.5">
        <span
          className="h-3 w-4 rounded-[3px] bg-surface-muted bg-[repeating-linear-gradient(135deg,var(--border-strong)_0_1px,transparent_1px_5px)]"
          aria-hidden="true"
        />
        Busy (Google Calendar)
      </li>
      <li className="flex items-center gap-1.5">
        <span className="h-0.5 w-4 bg-danger" aria-hidden="true" />
        Now
      </li>
    </ul>
  );
}

/* Week grid (lg and up) ------------------------------------------------------ */

function WeekGrid({
  week,
  data,
  moving,
  onMeeting,
  onSlot,
}: {
  week: Week;
  data: MeetingBoard;
  moving: boolean;
  onMeeting: (m: Meeting) => void;
  onSlot: (s: FreeSlot) => void;
}) {
  const rows = (week.to - week.from) / 30;
  const height = rows * ROW;
  const columns = {
    gridTemplateColumns: `3.5rem repeat(${week.days.length}, minmax(0, 1fr))`,
  };
  const top = (min: number) =>
    ((Math.max(min, week.from) - week.from) / 30) * ROW;
  const tall = (a: number, b: number) =>
    Math.max(0, top(Math.min(b, week.to)) - top(a));
  return (
    <div className="hidden overflow-hidden rounded-xl border border-border bg-surface shadow-sm lg:block">
      <div
        className="grid border-b border-border bg-surface-muted/60"
        style={columns}
      >
        <div />
        {week.perDay.map((d) => {
          const isToday = d.day === week.today;
          const count = d.blocks.filter(
            (b) => b.kind === "booking" || b.meeting.status !== "cancelled",
          ).length;
          return (
            <div
              key={d.day}
              className="min-w-0 border-l border-border px-2 py-2 text-center"
            >
              <p
                className={cn(
                  "text-xs font-medium text-muted-foreground",
                  isToday && "text-primary",
                )}
              >
                {dayText(d.day, { weekday: "short" })}
              </p>
              <p
                className={cn(
                  "mx-auto mt-0.5 flex size-7 items-center justify-center rounded-full text-[15px] font-semibold tabular-nums",
                  isToday && "bg-primary text-primary-foreground",
                )}
              >
                {dayText(d.day, { day: "numeric" })}
              </p>
              <p className="mt-0.5 truncate text-[11px] text-muted-foreground">
                {!d.rule.open
                  ? "Closed"
                  : count
                    ? `${count} ${count === 1 ? "item" : "items"} · ${d.free.length} free`
                    : `${d.free.length} free`}
              </p>
            </div>
          );
        })}
      </div>
      <div className="max-h-[70vh] overflow-y-auto">
        <div className="grid" style={columns}>
          <div className="relative" style={{ height }}>
            {Array.from({ length: rows }, (_, i) => week.from + i * 30)
              .filter((min) => min % 60 === 0)
              .map((min) => (
                <span
                  key={min}
                  className="absolute right-1.5 -translate-y-1/2 text-[10.5px] whitespace-nowrap text-muted-foreground tabular-nums first:translate-y-0"
                  style={{ top: top(min) }}
                >
                  {clock(min)}
                </span>
              ))}
          </div>
          {week.perDay.map((d) => {
            const opens = toMin(d.rule.start);
            const closes = toMin(d.rule.end);
            const isToday = d.day === week.today;
            return (
              <div
                key={d.day}
                className={cn(
                  "relative min-w-0 border-l border-border",
                  isToday && "bg-primary-soft/20",
                )}
                style={{ height }}
              >
                {Array.from({ length: rows }, (_, i) => (
                  <div
                    key={i}
                    className={cn(
                      "border-b border-border/60",
                      (week.from + (i + 1) * 30) % 60 !== 0 &&
                        "border-dashed border-border/40",
                    )}
                    style={{ height: ROW }}
                  />
                ))}
                {!d.rule.open ? (
                  <div className="absolute inset-0 flex items-center justify-center bg-surface-sunken/70 text-xs font-medium text-muted-foreground">
                    Closed
                  </div>
                ) : (
                  <>
                    {opens > week.from && (
                      <div
                        className="absolute inset-x-0 top-0 bg-surface-sunken/60"
                        style={{ height: tall(week.from, opens) }}
                        aria-hidden="true"
                      />
                    )}
                    {closes < week.to && (
                      <div
                        className="absolute inset-x-0 bg-surface-sunken/60"
                        style={{
                          top: top(closes),
                          height: tall(closes, week.to),
                        }}
                        aria-hidden="true"
                      />
                    )}
                  </>
                )}
                {d.busy.map(([a, b]) =>
                  b <= week.from || a >= week.to ? null : (
                    <div
                      key={`busy-${a}-${b}`}
                      className="absolute inset-x-1 overflow-hidden rounded-md border border-border bg-surface-muted bg-[repeating-linear-gradient(135deg,var(--border-strong)_0_1px,transparent_1px_6px)] px-1.5 py-0.5 text-[10.5px] font-medium text-muted-foreground"
                      style={{ top: top(a) + 1, height: tall(a, b) - 2 }}
                      title={`Busy in Google Calendar, ${clock(a)} – ${clock(b)}`}
                    >
                      Busy
                    </div>
                  ),
                )}
                {d.free.map(({ slot, start }) => (
                  <button
                    key={slot.local}
                    type="button"
                    onClick={() => onSlot(slot)}
                    title={`Free at ${slot.label}`}
                    className={cn(
                      "group absolute inset-x-1 rounded-md border border-dashed border-success/30 bg-success-soft/40 px-1.5 text-left text-[10.5px] font-medium text-success/80 transition-colors hover:border-solid hover:border-success/60 hover:bg-success-soft hover:text-success focus-visible:outline-2 focus-visible:outline-ring",
                      moving &&
                        "border-solid border-primary/50 bg-primary-soft/60 text-primary-soft-foreground hover:border-primary hover:bg-primary-soft hover:text-primary-soft-foreground",
                    )}
                    style={{ top: top(start) + 2, height: ROW - 4 }}
                  >
                    <span className="group-hover:hidden">Free</span>
                    <span className="hidden truncate group-hover:inline">
                      {moving ? "Move here" : clock(start)}
                    </span>
                  </button>
                ))}
                {d.blocks.map((b) => {
                  if (b.end <= week.from || b.start >= week.to) return null;
                  const h = tall(b.start, b.end);
                  const width = 100 / b.lanes;
                  const pos = {
                    top: top(b.start) + 1,
                    height: Math.max(h - 2, 18),
                    left: `calc(${b.lane * width}% + 3px)`,
                    width: `calc(${width}% - 6px)`,
                  };
                  return b.kind === "meeting" ? (
                    <MeetingBlock
                      key={b.key}
                      meeting={b.meeting}
                      tz={data.timezone}
                      compact={h < 44}
                      style={pos}
                      onClick={() => onMeeting(b.meeting)}
                    />
                  ) : (
                    <BookingBlock
                      key={b.key}
                      booking={b.booking}
                      tz={data.timezone}
                      compact={h < 44}
                      style={pos}
                    />
                  );
                })}
                {isToday &&
                  week.nowMin >= week.from &&
                  week.nowMin <= week.to && (
                    <div
                      className="pointer-events-none absolute inset-x-0 z-10 h-0.5 bg-danger"
                      style={{ top: top(week.nowMin) }}
                      aria-label="Now"
                    >
                      <span className="absolute -top-[3px] -left-1 size-2 rounded-full bg-danger" />
                    </div>
                  )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function MeetingBlock({
  meeting: m,
  tz,
  compact,
  style,
  onClick,
}: {
  meeting: Meeting;
  tz: string;
  compact: boolean;
  style: React.CSSProperties;
  onClick: () => void;
}) {
  const how = howOf(m.how);
  const time = timeOf(tz, m.starts_at);
  return (
    <button
      type="button"
      onClick={onClick}
      style={style}
      title={`${m.customer_name} · ${m.label} · ${STATUS[m.status].label}`}
      className={cn(
        "absolute z-[1] flex min-w-0 flex-col overflow-hidden rounded-md border-l-[3px] px-1.5 py-0.5 text-left text-[11px] leading-tight shadow-sm transition focus-visible:outline-2 focus-visible:outline-ring",
        STATUS[m.status].block,
      )}
    >
      <span className="flex min-w-0 items-center gap-1 font-semibold">
        {m.status === "live" && (
          <span className="relative flex size-1.5 shrink-0">
            <span className="absolute inline-flex size-full animate-ping rounded-full bg-success opacity-70" />
            <span className="relative inline-flex size-1.5 rounded-full bg-success" />
          </span>
        )}
        <span className="truncate">{m.customer_name}</span>
        {m.change_to && (
          <ArrowRightLeft
            className="size-3 shrink-0 text-warning"
            aria-label="Customer asked for another time"
          />
        )}
      </span>
      {compact ? null : (
        <span className="mt-0.5 flex min-w-0 items-center gap-1 opacity-90">
          <how.icon className="size-3 shrink-0" aria-hidden="true" />
          <span className="truncate">{time}</span>
        </span>
      )}
      {!compact && m.topic && (
        <span className="mt-0.5 truncate opacity-75">{m.topic}</span>
      )}
    </button>
  );
}

function BookingBlock({
  booking: b,
  tz,
  compact,
  style,
}: {
  booking: Booking;
  tz: string;
  compact: boolean;
  style: React.CSSProperties;
}) {
  const body = (
    <>
      <span className="truncate font-semibold">{b.customer_name}</span>
      {!compact && (
        <span className="mt-0.5 truncate opacity-90">
          Booking · {timeOf(tz, b.starts_at)}
        </span>
      )}
    </>
  );
  const cls =
    "absolute z-[1] flex min-w-0 flex-col overflow-hidden rounded-md border-l-[3px] border-l-info bg-info-soft px-1.5 py-0.5 text-left text-[11px] leading-tight text-info shadow-sm";
  const title = `Booking: ${b.customer_name}, ${timeOf(tz, b.starts_at)} – ${timeOf(tz, b.ends_at)}`;
  return b.conversation_id ? (
    <Link
      href={chatHref(b.conversation_id)}
      className={cn(cls, "hover:brightness-95")}
      style={style}
      title={title}
    >
      {body}
    </Link>
  ) : (
    <div className={cls} style={style} title={title}>
      {body}
    </div>
  );
}

/* Day list (below lg) -------------------------------------------------------- */

function DayList({
  week,
  data,
  day,
  onDay,
  moving,
  onMeeting,
  onSlot,
}: {
  week: Week;
  data: MeetingBoard;
  day: string | null;
  onDay: (day: string) => void;
  moving: boolean;
  onMeeting: (m: Meeting) => void;
  onSlot: (s: FreeSlot) => void;
}) {
  const current =
    day && week.days.includes(day)
      ? day
      : week.days.includes(week.today)
        ? week.today
        : week.days[0];
  const model = week.perDay.find((d) => d.day === current)!;
  const tz = data.timezone;
  const items = [
    ...model.blocks.map((b) => ({ at: b.start, block: b })),
    ...model.busy.map(([a, b]) => ({ at: a, busy: [a, b] as const })),
  ].sort((x, y) => x.at - y.at);
  return (
    <div className="space-y-3 lg:hidden">
      <div
        role="tablist"
        aria-label="Day"
        className="grid gap-1"
        style={{
          gridTemplateColumns: `repeat(${week.days.length}, minmax(0, 1fr))`,
        }}
      >
        {week.perDay.map((d) => {
          const active = d.day === current;
          const count = d.blocks.length;
          return (
            <button
              key={d.day}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => onDay(d.day)}
              className={cn(
                "flex min-w-0 flex-col items-center rounded-lg border border-border bg-surface px-0.5 py-1.5 text-xs",
                active &&
                  "border-primary bg-primary text-primary-foreground shadow-sm",
                !active &&
                  !d.rule.open &&
                  "bg-surface-sunken text-muted-foreground",
              )}
            >
              <span className="text-[11px] opacity-80">
                {dayText(d.day, { weekday: "short" })}
              </span>
              <span className="text-[15px] font-semibold tabular-nums">
                {dayText(d.day, { day: "numeric" })}
              </span>
              <span
                className={cn(
                  "mt-0.5 size-1.5 rounded-full",
                  count
                    ? active
                      ? "bg-primary-foreground"
                      : "bg-primary"
                    : "bg-transparent",
                )}
                aria-hidden="true"
              />
            </button>
          );
        })}
      </div>
      <div className="rounded-xl border border-border bg-surface p-3 shadow-sm">
        <p className="mb-2 text-[13px] font-semibold">
          {dayText(current, { weekday: "long", day: "numeric", month: "long" })}
          {current === week.today && (
            <Badge tone="primary" className="ml-2">
              Today
            </Badge>
          )}
        </p>
        {!model.rule.open && (
          <p className="mb-2 rounded-md bg-surface-muted px-2.5 py-1.5 text-xs text-muted-foreground">
            Closed for meetings this day.
          </p>
        )}
        {items.length === 0 ? (
          <p className="py-2 text-[13px] text-muted-foreground">
            Nothing booked.
          </p>
        ) : (
          <ul className="space-y-1.5">
            {items.map((item) =>
              "block" in item && item.block ? (
                <li key={item.block.key}>
                  {item.block.kind === "meeting" ? (
                    <MeetingRow
                      meeting={item.block.meeting}
                      tz={tz}
                      onClick={() =>
                        item.block.kind === "meeting" &&
                        onMeeting(item.block.meeting)
                      }
                    />
                  ) : (
                    <BookingRow booking={item.block.booking} tz={tz} />
                  )}
                </li>
              ) : "busy" in item && item.busy ? (
                <li
                  key={`busy-${item.busy[0]}`}
                  className="flex items-center gap-2 rounded-md border border-border bg-surface-muted bg-[repeating-linear-gradient(135deg,var(--border-strong)_0_1px,transparent_1px_6px)] px-2.5 py-1.5 text-xs text-muted-foreground"
                >
                  <Clock className="size-3.5 shrink-0" aria-hidden="true" />
                  Busy {clock(item.busy[0])} – {clock(item.busy[1] % 1440)}
                  <span className="ml-auto">Google Calendar</span>
                </li>
              ) : null,
            )}
          </ul>
        )}
        {model.free.length > 0 && (
          <div className="mt-3">
            <p className="mb-1.5 text-xs font-medium text-muted-foreground">
              {moving ? "Tap a free time to move the meeting" : "Free times"}
            </p>
            <div className="flex flex-wrap gap-1.5">
              {model.free.map(({ slot, start }) => (
                <button
                  key={slot.local}
                  type="button"
                  onClick={() => onSlot(slot)}
                  className={cn(
                    "rounded-full border border-success/30 bg-success-soft/50 px-2.5 py-1 text-xs font-medium text-success tabular-nums hover:bg-success-soft",
                    moving &&
                      "border-primary/40 bg-primary-soft text-primary-soft-foreground",
                  )}
                >
                  {clock(start)}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function MeetingRow({
  meeting: m,
  tz,
  onClick,
}: {
  meeting: Meeting;
  tz: string;
  onClick: () => void;
}) {
  const how = howOf(m.how);
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex w-full min-w-0 items-center gap-2.5 rounded-md border-l-[3px] px-2.5 py-2 text-left text-[13px]",
        STATUS[m.status].block,
      )}
    >
      <span className="w-16 shrink-0 text-xs font-semibold tabular-nums">
        {timeOf(tz, m.starts_at)}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate font-medium">{m.customer_name}</span>
        <span className="flex items-center gap-1 truncate text-xs opacity-80">
          <how.icon className="size-3 shrink-0" aria-hidden="true" />
          {m.minutes} min{m.topic ? ` · ${m.topic}` : ""}
        </span>
      </span>
      {m.change_to && (
        <ArrowRightLeft
          className="size-3.5 shrink-0 text-warning"
          aria-label="Customer asked for another time"
        />
      )}
      <ChevronRight className="size-4 shrink-0 opacity-60" aria-hidden="true" />
    </button>
  );
}

function BookingRow({ booking: b, tz }: { booking: Booking; tz: string }) {
  const body = (
    <>
      <span className="w-16 shrink-0 text-xs font-semibold tabular-nums">
        {timeOf(tz, b.starts_at)}
      </span>
      <span className="min-w-0 flex-1 truncate font-medium">
        {b.customer_name}
      </span>
      <Badge tone="info">Booking</Badge>
    </>
  );
  const cls =
    "flex w-full min-w-0 items-center gap-2.5 rounded-md border-l-[3px] border-l-info bg-info-soft px-2.5 py-2 text-[13px] text-info";
  return b.conversation_id ? (
    <Link href={chatHref(b.conversation_id)} className={cls}>
      {body}
    </Link>
  ) : (
    <div className={cls}>{body}</div>
  );
}

/* Sections ------------------------------------------------------------------- */

function Section({
  id,
  title,
  icon: Icon,
  count,
  description,
  children,
}: {
  id: string;
  title: string;
  icon: LucideIcon;
  count?: number;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <section
      id={id}
      className="scroll-mt-20 rounded-xl border border-border bg-surface shadow-sm"
    >
      <header className="flex items-start gap-2 border-b border-border px-4 py-3">
        <Icon
          className="mt-0.5 size-4 shrink-0 text-muted-foreground"
          aria-hidden="true"
        />
        <div className="min-w-0 flex-1">
          <h2 className="flex items-center gap-2 text-[14px] font-semibold">
            {title}
            {count ? (
              <span className="rounded-full bg-surface-muted px-1.5 text-xs font-medium text-muted-foreground tabular-nums">
                {count}
              </span>
            ) : null}
          </h2>
          {description && (
            <p className="mt-0.5 text-xs text-muted-foreground">
              {description}
            </p>
          )}
        </div>
      </header>
      <div className="p-3">{children}</div>
    </section>
  );
}

function ChatLink({ conversationId }: { conversationId: string }) {
  return (
    <Button asChild size="xs" variant="ghost">
      <Link href={chatHref(conversationId)}>
        <MessageCircle aria-hidden="true" /> Open chat
      </Link>
    </Button>
  );
}

function WaitingSection({
  data,
  canAct,
  onBook,
}: {
  data: MeetingBoard;
  canAct: boolean;
  onBook: (b: BookFor) => void;
}) {
  return (
    <Section
      id="meet-waiting"
      title="Waiting for a time"
      icon={Hourglass}
      count={data.waiting.length}
      description="Customers who asked to meet. Book the time they asked for, or pick another — tap a free slot on the board too."
    >
      {data.waiting.length === 0 ? (
        <EmptyState
          compact
          icon={Hourglass}
          title="Nobody's waiting"
          description="When a customer asks to meet, pi asks you here and suggests your free times."
        />
      ) : (
        <ul className="space-y-2">
          {data.waiting.map((w) => (
            <li
              key={w.request_id}
              className="rounded-lg border border-border p-3"
            >
              <div className="flex flex-wrap items-center gap-2">
                <p className="min-w-0 truncate text-[13.5px] font-semibold">
                  {w.customer_name}
                </p>
                {w.priority === "high" && <Badge tone="danger">High</Badge>}
                {w.topic && (
                  <span className="min-w-0 truncate text-xs text-muted-foreground">
                    {w.topic}
                  </span>
                )}
              </div>
              {w.asked_label && (
                <p className="mt-1 flex items-center gap-1.5 text-[13px] text-foreground-secondary">
                  <CalendarClock
                    className="size-3.5 shrink-0"
                    aria-hidden="true"
                  />
                  Asked for {w.asked_label}
                </p>
              )}
              {w.question && (
                <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                  {w.question}
                </p>
              )}
              <div className="mt-2 flex flex-wrap gap-1.5">
                {canAct && w.asked_local && (
                  <Button
                    size="xs"
                    onClick={() =>
                      onBook({
                        id: w.request_id,
                        question: w.question,
                        startsAt: w.asked_local,
                      })
                    }
                  >
                    <CalendarCheck aria-hidden="true" /> Book asked time
                  </Button>
                )}
                {canAct && (
                  <Button
                    size="xs"
                    variant="secondary"
                    onClick={() =>
                      onBook({
                        id: w.request_id,
                        question: w.question,
                        startsAt: null,
                      })
                    }
                  >
                    <CalendarDays aria-hidden="true" /> Pick a time
                  </Button>
                )}
                <ChatLink conversationId={w.conversation_id} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

function told(
  r: MeetingChangeResult,
  notify: boolean,
  message: string,
  silent: string,
) {
  if (!notify) toast.success(silent);
  else if (r.told_customer) toast.success(message);
  else toast.warning(NOT_TOLD);
  if (r.calendar_moved === false || r.calendar_removed === false)
    toast.warning(
      "Google Calendar couldn't be updated. Change the event there too.",
    );
}

function ChangesSection({
  tz,
  meetings,
  canAct,
  onMove,
}: {
  tz: string;
  meetings: Meeting[];
  canAct: boolean;
  onMove: (m: Meeting) => void;
}) {
  return (
    <Section
      id="meet-change"
      title="Time change asked"
      icon={ArrowRightLeft}
      count={meetings.length}
      description="The customer asked to move the meeting."
    >
      {meetings.length === 0 ? (
        <EmptyState
          compact
          icon={ArrowRightLeft}
          title="No time changes asked"
          description="If a customer asks to move their meeting, it shows here to accept in one tap."
        />
      ) : (
        <ul className="space-y-2">
          {meetings.map((m) => (
            <ChangeItem
              key={m.id}
              meeting={m}
              tz={tz}
              canAct={canAct}
              onMove={onMove}
            />
          ))}
        </ul>
      )}
    </Section>
  );
}

function ChangeItem({
  meeting: m,
  tz,
  canAct,
  onMove,
}: {
  meeting: Meeting;
  tz: string;
  canAct: boolean;
  onMove: (m: Meeting) => void;
}) {
  const accept = useScopedMutation(
    () => meetingsService.acceptChange(m.conversation_id),
    {
      invalidate: [KEY],
      error: "The new time couldn't be accepted. Please try again.",
      onSuccess: (r) =>
        told(r, true, "New time accepted. pi told the customer.", ""),
    },
  );
  return (
    <li className="rounded-lg border border-warning/30 bg-warning-soft/30 p-3">
      <p className="text-[13.5px] font-semibold">{m.customer_name}</p>
      <p className="mt-1 flex flex-wrap items-center gap-1.5 text-[13px]">
        <span className="text-muted-foreground line-through">{m.label}</span>
        <ArrowRight
          className="size-3.5 shrink-0 text-warning"
          aria-hidden="true"
        />
        <span className="font-medium">
          {m.change_label ?? (m.change_to ? dateTimeOf(tz, m.change_to) : "")}
        </span>
      </p>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {canAct && (
          <>
            <Button
              size="xs"
              loading={accept.isPending}
              onClick={() => accept.mutate(undefined)}
            >
              <CircleCheck aria-hidden="true" /> Accept new time
            </Button>
            <Button size="xs" variant="secondary" onClick={() => onMove(m)}>
              <CalendarClock aria-hidden="true" /> Move to another time
            </Button>
          </>
        )}
        <ChatLink conversationId={m.conversation_id} />
      </div>
    </li>
  );
}

function LinkActions({ meeting: m }: { meeting: Meeting }) {
  if (!m.link) return null;
  return (
    <>
      <Button asChild size="xs" variant="soft">
        <a href={m.link} target="_blank" rel="noopener noreferrer">
          <ExternalLink aria-hidden="true" /> Join
        </a>
      </Button>
      <Button
        size="xs"
        variant="ghost"
        onClick={() => {
          void navigator.clipboard
            ?.writeText(m.link)
            .then(() => toast.success("Meeting link copied."))
            .catch(() => toast.error("The link couldn't be copied."));
        }}
      >
        <Copy aria-hidden="true" /> Copy link
      </Button>
    </>
  );
}

function useRemind(meeting: Meeting) {
  return useScopedMutation(
    () => meetingsService.remind(meeting.conversation_id),
    {
      invalidate: [KEY],
      success: "Reminder sent on WhatsApp with the time and link.",
      error: "The reminder couldn't be sent. Please try again.",
    },
  );
}

function UpNextSection({
  data,
  canAct,
  onOpen,
  onMove,
  onCancel,
}: {
  data: MeetingBoard;
  canAct: boolean;
  onOpen: (m: Meeting) => void;
  onMove: (m: Meeting) => void;
  onCancel: (m: Meeting) => void;
}) {
  return (
    <Section
      id="meet-next"
      title="Up next"
      icon={CalendarClock}
      count={data.upcoming.length}
    >
      {data.upcoming.length === 0 ? (
        <EmptyState
          compact
          icon={CalendarClock}
          title="No meetings coming up"
          description="Meetings pi or your team arrange appear here, with the link ready to join."
        />
      ) : (
        <ul className="divide-y divide-border">
          {data.upcoming.map((m) => (
            <UpNextItem
              key={m.id}
              meeting={m}
              data={data}
              canAct={canAct}
              onOpen={onOpen}
              onMove={onMove}
              onCancel={onCancel}
            />
          ))}
        </ul>
      )}
    </Section>
  );
}

function UpNextItem({
  meeting: m,
  data,
  canAct,
  onOpen,
  onMove,
  onCancel,
}: {
  meeting: Meeting;
  data: MeetingBoard;
  canAct: boolean;
  onOpen: (m: Meeting) => void;
  onMove: (m: Meeting) => void;
  onCancel: (m: Meeting) => void;
}) {
  const remind = useRemind(m);
  const how = howOf(m.how);
  const live = m.status === "live";
  const act = canAct && m.actionable;
  return (
    <li className="py-2.5 first:pt-0 last:pb-0">
      <div className="flex items-start gap-3">
        <div
          className={cn(
            "w-20 shrink-0 rounded-md px-2 py-1 text-center text-xs font-semibold",
            live
              ? "bg-success-soft text-success"
              : "bg-primary-soft text-primary-soft-foreground",
          )}
        >
          {live ? "Now" : whenLabel(data.timezone, m.starts_at, data.now)}
        </div>
        <button
          type="button"
          onClick={() => onOpen(m)}
          className="min-w-0 flex-1 text-left"
        >
          <p className="truncate text-[13.5px] font-semibold hover:underline">
            {m.customer_name}
          </p>
          <p className="flex items-center gap-1 truncate text-xs text-muted-foreground">
            <how.icon className="size-3 shrink-0" aria-hidden="true" />
            {dateTimeOf(data.timezone, m.starts_at)} · {m.minutes} min
            {m.topic ? ` · ${m.topic}` : ""}
          </p>
        </button>
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5 pl-[5.75rem] max-sm:pl-0">
        <LinkActions meeting={m} />
        {act && (
          <>
            <Button
              size="xs"
              variant="ghost"
              loading={remind.isPending}
              onClick={() => remind.mutate(undefined)}
            >
              <Bell aria-hidden="true" /> Remind
            </Button>
            <Button size="xs" variant="ghost" onClick={() => onMove(m)}>
              <CalendarClock aria-hidden="true" /> Move
            </Button>
            <Button
              size="xs"
              variant="ghost"
              className="text-danger hover:text-danger"
              onClick={() => onCancel(m)}
            >
              <CalendarX aria-hidden="true" /> Cancel
            </Button>
          </>
        )}
      </div>
    </li>
  );
}

function OutcomeSection({
  data,
  canAct,
  onOpen,
}: {
  data: MeetingBoard;
  canAct: boolean;
  onOpen: (m: Meeting) => void;
}) {
  return (
    <Section
      id="meet-outcome"
      title="How did it go?"
      icon={MessageCircle}
      count={data.needs_outcome.length}
      description="Tell pi what was agreed, so its next reply carries on from the meeting."
    >
      {data.needs_outcome.length === 0 ? (
        <EmptyState
          compact
          icon={CircleCheck}
          title="All caught up"
          description="After a meeting ends, it waits here for a quick note on how it went."
        />
      ) : (
        <ul className="space-y-2">
          {data.needs_outcome.map((m) => (
            <li key={m.id} className="rounded-lg border border-border p-3">
              <button
                type="button"
                onClick={() => onOpen(m)}
                className="block w-full min-w-0 text-left"
              >
                <p className="truncate text-[13.5px] font-semibold hover:underline">
                  {m.customer_name}
                </p>
                <p className="truncate text-xs text-muted-foreground">
                  {m.label}
                  {m.topic ? ` · ${m.topic}` : ""}
                </p>
              </button>
              {canAct && m.actionable ? (
                <OutcomeForm meeting={m} className="mt-2" />
              ) : (
                <p className="mt-2 text-xs text-muted-foreground">
                  Someone who can reply in the inbox can record this.
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

function OutcomeForm({
  meeting,
  className,
  onSaved,
}: {
  meeting: Meeting;
  className?: string;
  onSaved?: () => void;
}) {
  const [status, setStatus] = useState<"done" | "no_show">("done");
  const [note, setNote] = useState("");
  const save = useScopedMutation(
    () =>
      meetingsService.outcome({
        conversation_id: meeting.conversation_id,
        status,
        note: note.trim(),
      }),
    {
      invalidate: [KEY],
      success:
        status === "done"
          ? "Saved. pi will carry on from what was agreed."
          : "Marked as a no-show.",
      error: "The outcome couldn't be saved. Please try again.",
      onSuccess: () => onSaved?.(),
    },
  );
  const id = `outcome-${meeting.id}`;
  return (
    <div className={cn("space-y-2", className)}>
      <div
        role="radiogroup"
        aria-label="How it went"
        className="grid grid-cols-2 gap-1 rounded-lg bg-surface-sunken p-1 sm:w-fit"
      >
        {(
          [
            ["done", "Done", CircleCheck],
            ["no_show", "No-show", UserX],
          ] as const
        ).map(([value, label, Icon]) => (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={status === value}
            onClick={() => setStatus(value)}
            className={cn(
              "inline-flex items-center justify-center gap-1.5 rounded-md px-3 py-1 text-[13px] font-medium text-muted-foreground",
              status === value && "bg-surface text-foreground shadow-sm",
              status === value && value === "no_show" && "text-danger",
            )}
          >
            <Icon className="size-3.5" aria-hidden="true" />
            {label}
          </button>
        ))}
      </div>
      <Label htmlFor={id} className="sr-only">
        Outcome note
      </Label>
      <Textarea
        id={id}
        rows={2}
        maxLength={2000}
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder={
          status === "done"
            ? "What was agreed? pi will read this"
            : "Anything to note? e.g. didn't pick up, will rebook"
        }
      />
      <div className="flex justify-end">
        <Button
          size="sm"
          loading={save.isPending}
          onClick={() => save.mutate(undefined)}
        >
          Save outcome
        </Button>
      </div>
    </div>
  );
}

function HistorySection({
  data,
  onOpen,
}: {
  data: MeetingBoard;
  onOpen: (m: Meeting) => void;
}) {
  return (
    <Section id="meet-history" title="History" icon={History}>
      {data.history.length === 0 ? (
        <EmptyState
          compact
          icon={History}
          title="No past meetings yet"
          description="Finished, missed and cancelled meetings are kept here with what was agreed."
        />
      ) : (
        <ul className="divide-y divide-border">
          {data.history.map((m) => (
            <li key={m.id}>
              <button
                type="button"
                onClick={() => onOpen(m)}
                className="flex w-full min-w-0 items-start gap-2.5 py-2 text-left hover:bg-surface-muted/50"
              >
                <Badge tone={STATUS[m.status].tone} className="mt-0.5">
                  {STATUS[m.status].label}
                </Badge>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13px] font-medium">
                    {m.customer_name}
                    <span className="font-normal text-muted-foreground">
                      {" "}
                      · {m.label}
                    </span>
                  </span>
                  {m.outcome && (
                    <span className="mt-0.5 line-clamp-2 block text-xs text-muted-foreground">
                      {m.outcome}
                    </span>
                  )}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

/* Detail sheet --------------------------------------------------------------- */

function MeetingDetail({
  meeting: m,
  data,
  canAct,
  onMove,
  onCancel,
  onDone,
}: {
  meeting: Meeting;
  data: MeetingBoard;
  canAct: boolean;
  onMove: () => void;
  onCancel: () => void;
  onDone: () => void;
}) {
  const tz = data.timezone;
  const how = howOf(m.how);
  const remind = useRemind(m);
  const accept = useScopedMutation(
    () => meetingsService.acceptChange(m.conversation_id),
    {
      invalidate: [KEY],
      error: "The new time couldn't be accepted. Please try again.",
      onSuccess: (r) => {
        told(r, true, "New time accepted. pi told the customer.", "");
        onDone();
      },
    },
  );
  const open = m.status === "scheduled" || m.status === "live";
  const act = canAct && m.actionable;
  return (
    <>
      <DialogHeader
        title={m.customer_name}
        description={`${dateTimeOf(tz, m.starts_at)} – ${timeOf(tz, m.ends_at)} · ${m.minutes} min`}
      />
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-4">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={STATUS[m.status].tone}>{STATUS[m.status].label}</Badge>
          {m.calendar_event && (
            <Badge tone="outline">
              <CalendarCheck aria-hidden="true" /> In Google Calendar
            </Badge>
          )}
        </div>
        <dl className="grid grid-cols-[6rem_1fr] gap-x-3 gap-y-2 text-[13px]">
          {m.topic && (
            <>
              <dt className="text-muted-foreground">About</dt>
              <dd className="min-w-0">{m.topic}</dd>
            </>
          )}
          <dt className="text-muted-foreground">How</dt>
          <dd className="flex min-w-0 items-center gap-1.5">
            <how.icon className="size-3.5 shrink-0" aria-hidden="true" />
            {how.label}
          </dd>
          {m.place && (
            <>
              <dt className="text-muted-foreground">Where</dt>
              <dd className="min-w-0">{m.place}</dd>
            </>
          )}
          {m.link && (
            <>
              <dt className="text-muted-foreground">Link</dt>
              <dd className="min-w-0 truncate">
                <a
                  href={m.link}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary hover:underline"
                >
                  {m.link}
                </a>
              </dd>
            </>
          )}
          {m.phone && (
            <>
              <dt className="text-muted-foreground">Phone</dt>
              <dd className="min-w-0">
                <a
                  href={`tel:${m.phone}`}
                  className="inline-flex items-center gap-1 hover:underline"
                >
                  <Phone className="size-3.5" aria-hidden="true" />
                  {m.phone}
                </a>
              </dd>
            </>
          )}
          {m.note && (
            <>
              <dt className="text-muted-foreground">Note</dt>
              <dd className="min-w-0 whitespace-pre-wrap">{m.note}</dd>
            </>
          )}
          {m.outcome && (
            <>
              <dt className="text-muted-foreground">
                {m.status === "cancelled" ? "Reason" : "Outcome"}
              </dt>
              <dd className="min-w-0 whitespace-pre-wrap">{m.outcome}</dd>
            </>
          )}
        </dl>
        {m.link && (
          <div className="flex flex-wrap gap-1.5">
            <LinkActions meeting={m} />
          </div>
        )}
        {m.change_to && (
          <Notice
            tone="warning"
            icon={ArrowRightLeft}
            title="The customer asked for another time"
            action={
              act ? (
                <Button
                  size="xs"
                  loading={accept.isPending}
                  onClick={() => accept.mutate(undefined)}
                >
                  Accept
                </Button>
              ) : undefined
            }
          >
            {m.change_label ?? dateTimeOf(tz, m.change_to)}
          </Notice>
        )}
        {m.status === "awaiting_outcome" && act && (
          <div className="rounded-lg border border-border p-3">
            <p className="mb-2 text-[13px] font-semibold">How did it go?</p>
            <OutcomeForm meeting={m} onSaved={onDone} />
          </div>
        )}
        {!m.actionable && (
          <p className="rounded-md bg-surface-muted px-3 py-2 text-xs text-muted-foreground">
            An earlier meeting in this chat. Only the chat{"'"}s current meeting
            can be changed.
          </p>
        )}
      </div>
      <DialogFooter className="flex-row flex-wrap justify-start sm:justify-start">
        <Button asChild size="sm" variant="secondary">
          <Link href={chatHref(m.conversation_id)}>
            <MessageCircle aria-hidden="true" /> Open chat
          </Link>
        </Button>
        {act && open && (
          <>
            <Button
              size="sm"
              variant="secondary"
              loading={remind.isPending}
              onClick={() => remind.mutate(undefined)}
            >
              <Bell aria-hidden="true" /> Remind
            </Button>
            <Button size="sm" variant="secondary" onClick={onMove}>
              <CalendarClock aria-hidden="true" /> Move
            </Button>
            <Button size="sm" variant="danger-outline" onClick={onCancel}>
              <CalendarX aria-hidden="true" /> Cancel
            </Button>
          </>
        )}
      </DialogFooter>
    </>
  );
}

/* Dialogs -------------------------------------------------------------------- */

function NotifyBox({
  id,
  checked,
  onChange,
}: {
  id: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <Checkbox
        id={id}
        checked={checked}
        onCheckedChange={(v) => onChange(v === true)}
      />
      <Label htmlFor={id} className="mb-0">
        Tell the customer on WhatsApp
      </Label>
    </div>
  );
}

function useMove(onDone: () => void) {
  return useScopedMutation(meetingsService.move, {
    invalidate: [KEY],
    error: "The meeting couldn't be moved. Please try again.",
    onSuccess: (r, input) => {
      told(
        r,
        input.notify !== false,
        "Meeting moved. pi told the customer the new time.",
        "Meeting moved. The customer wasn't told.",
      );
      onDone();
    },
  });
}

function MoveDialog({
  meeting,
  data,
  onClose,
  onPickOnBoard,
}: {
  meeting: Meeting;
  data: MeetingBoard;
  onClose: () => void;
  onPickOnBoard: (minutes: number, notify: boolean) => void;
}) {
  const [date, setDate] = useState(meeting.local.slice(0, 10));
  const [time, setTime] = useState(meeting.local.slice(11, 16));
  const [minutes, setMinutes] = useState(String(meeting.minutes));
  const [notify, setNotify] = useState(true);
  const move = useMove(onClose);
  const durations = [
    ...new Set([15, 30, 45, 60, 90, 120, meeting.minutes]),
  ].sort((a, b) => a - b);
  const suggestions = data.free
    .filter((f) => f.local !== meeting.local)
    .slice(0, 6);
  const picked = `${date}T${time}`;
  const ready =
    /^\d{4}-\d{2}-\d{2}$/.test(date) &&
    /^\d{2}:\d{2}$/.test(time) &&
    picked !== meeting.local;
  return (
    <Dialog open onOpenChange={(o) => !o && !move.isPending && onClose()}>
      <DialogContent size="md">
        <DialogHeader
          title={`Move ${meeting.customer_name}'s meeting`}
          description={`Now ${meeting.label}. Times are in ${data.zone_name || data.timezone}.`}
        />
        <DialogBody className="space-y-4">
          {suggestions.length > 0 && (
            <div>
              <p className="mb-1.5 text-xs font-medium text-muted-foreground">
                Free times
              </p>
              <div className="flex flex-wrap gap-1.5">
                {suggestions.map((f) => (
                  <button
                    key={f.local}
                    type="button"
                    onClick={() => {
                      setDate(f.local.slice(0, 10));
                      setTime(f.local.slice(11, 16));
                    }}
                    className={cn(
                      "rounded-full border border-success/30 bg-success-soft/50 px-2.5 py-1 text-xs font-medium text-success hover:bg-success-soft",
                      picked === f.local &&
                        "border-primary bg-primary text-primary-foreground hover:bg-primary",
                    )}
                  >
                    {f.label}
                  </button>
                ))}
              </div>
            </div>
          )}
          <div className="grid gap-3 sm:grid-cols-3">
            <div>
              <Label htmlFor="move-date">Date</Label>
              <Input
                id="move-date"
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="move-time">Time</Label>
              <Input
                id="move-time"
                type="time"
                value={time}
                onChange={(e) => setTime(e.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="move-length">Length</Label>
              <NativeSelect
                id="move-length"
                value={minutes}
                onChange={(e) => setMinutes(e.target.value)}
              >
                {durations.map((m) => (
                  <option key={m} value={String(m)}>
                    {m} minutes
                  </option>
                ))}
              </NativeSelect>
            </div>
          </div>
          <NotifyBox id="move-notify" checked={notify} onChange={setNotify} />
        </DialogBody>
        <DialogFooter className="sm:justify-between">
          <Button
            variant="ghost"
            onClick={() => onPickOnBoard(Number(minutes), notify)}
            disabled={move.isPending}
          >
            <MousePointerClick aria-hidden="true" /> Pick on the board
          </Button>
          <div className="flex flex-col-reverse gap-2 sm:flex-row">
            <Button
              variant="secondary"
              onClick={onClose}
              disabled={move.isPending}
            >
              Keep the time
            </Button>
            <Button
              loading={move.isPending}
              disabled={!ready || move.isPending}
              onClick={() =>
                move.mutate({
                  conversation_id: meeting.conversation_id,
                  starts_at: picked,
                  duration_minutes: Number(minutes),
                  notify,
                })
              }
            >
              Move meeting
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ConfirmMoveDialog({
  mode,
  slot,
  onClose,
  onMoved,
}: {
  mode: MoveMode;
  slot: FreeSlot;
  onClose: () => void;
  onMoved: () => void;
}) {
  const [notify, setNotify] = useState(mode.notify);
  const move = useMove(onMoved);
  return (
    <Dialog open onOpenChange={(o) => !o && !move.isPending && onClose()}>
      <DialogContent size="sm">
        <DialogHeader
          title="Move the meeting here?"
          description={`${mode.meeting.customer_name}: ${mode.meeting.label} → ${slot.label}`}
        />
        <DialogBody>
          <NotifyBox
            id="confirm-move-notify"
            checked={notify}
            onChange={setNotify}
          />
        </DialogBody>
        <DialogFooter>
          <Button
            variant="secondary"
            onClick={onClose}
            disabled={move.isPending}
          >
            Back
          </Button>
          <Button
            loading={move.isPending}
            onClick={() =>
              move.mutate({
                conversation_id: mode.meeting.conversation_id,
                starts_at: slot.local,
                duration_minutes: mode.minutes,
                notify,
              })
            }
          >
            Move to {slot.label}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function CancelDialog({
  meeting,
  onClose,
}: {
  meeting: Meeting;
  onClose: () => void;
}) {
  const [reason, setReason] = useState("");
  const [notify, setNotify] = useState(true);
  const cancel = useScopedMutation(meetingsService.cancel, {
    invalidate: [KEY],
    error: "The meeting couldn't be cancelled. Please try again.",
    onSuccess: (r, input) => {
      told(
        r,
        input.notify !== false,
        "Meeting cancelled. pi told the customer.",
        "Meeting cancelled. The customer wasn't told.",
      );
      onClose();
    },
  });
  return (
    <Dialog open onOpenChange={(o) => !o && !cancel.isPending && onClose()}>
      <DialogContent size="sm">
        <DialogHeader
          title={`Cancel ${meeting.customer_name}'s meeting?`}
          description={`${meeting.label}. The calendar event is removed too.`}
        />
        <DialogBody className="space-y-3">
          <div>
            <Label htmlFor="cancel-reason">Reason (optional)</Label>
            <Input
              id="cancel-reason"
              maxLength={300}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="e.g. Something came up — sorry for the change."
            />
          </div>
          <NotifyBox id="cancel-notify" checked={notify} onChange={setNotify} />
        </DialogBody>
        <DialogFooter>
          <Button
            variant="secondary"
            onClick={onClose}
            disabled={cancel.isPending}
          >
            Keep it
          </Button>
          <Button
            variant="danger"
            loading={cancel.isPending}
            onClick={() =>
              cancel.mutate({
                conversation_id: meeting.conversation_id,
                reason: reason.trim(),
                notify,
              })
            }
          >
            Cancel meeting
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function SlotChooser({
  slot,
  waiting,
  onClose,
  onPick,
}: {
  slot: FreeSlot;
  waiting: WaitingRequest[];
  onClose: () => void;
  onPick: (w: WaitingRequest) => void;
}) {
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent size="sm">
        <DialogHeader
          title="Book this time for…"
          description={`Free at ${slot.label}`}
        />
        <DialogBody>
          <ul className="space-y-1.5">
            {waiting.map((w) => (
              <li key={w.request_id}>
                <button
                  type="button"
                  onClick={() => onPick(w)}
                  className="flex w-full min-w-0 items-center gap-2 rounded-lg border border-border px-3 py-2 text-left hover:bg-surface-muted"
                >
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-1.5 text-[13px] font-medium">
                      <span className="truncate">{w.customer_name}</span>
                      {w.priority === "high" && (
                        <Badge tone="danger">High</Badge>
                      )}
                    </span>
                    <span className="block truncate text-xs text-muted-foreground">
                      {w.asked_label
                        ? `Asked for ${w.asked_label}`
                        : w.topic || "Asked to meet"}
                    </span>
                  </span>
                  <ChevronRight
                    className="size-4 shrink-0 text-muted-foreground"
                    aria-hidden="true"
                  />
                </button>
              </li>
            ))}
          </ul>
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}
