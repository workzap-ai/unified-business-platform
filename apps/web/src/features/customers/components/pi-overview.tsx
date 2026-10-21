"use client";

import { useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { z } from "zod";
import {
  Building2,
  Check,
  FileText,
  FolderKanban,
  Network,
} from "lucide-react";
import { Badge, Card, CardBody, CardHeader } from "@/components/ui/display";
import { useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import { cn } from "@/lib/utils";
import { formatDate, formatTime } from "@/lib/format";
import { apiRequest } from "@/services/api-client";
import { customerFilesService } from "../files-service";

/**
 * The team's picture of one customer from pi: who they are (what they told pi), their
 * projects with the journey, and their requests on a Problem Map with how they connect.
 * Backend: /customers/{id}/pi-overview (read-only, no AI call).
 */

const issueSchema = z.object({
  title: z.string(),
  stage: z.string().catch("noted"),
  ball_with: z.string().catch("pi"),
  summary: z.string().catch(""),
  next_step: z.string().catch(""),
  impact: z.number().catch(3),
  urgency: z.number().catch(3),
  area: z.string().catch(""),
  open_question: z.string().catch(""),
  root_cause: z.string().catch(""),
  solution_outline: z.string().catch(""),
  outcome: z.string().catch(""),
  solution_id: z.string().catch(""),
  original_words: z.string().catch(""),
});
const linkSchema = z.object({
  a_title: z.string(),
  b_title: z.string(),
  type: z.string(),
  reason: z.string().catch(""),
  benefit: z.string().nullable().catch(""),
});
const projectSchema = z.object({
  lead_id: z.string(),
  title: z.string(),
  stage: z.string(),
  service: z.string().catch(""),
  steps_done: z.number().optional(),
  steps_total: z.number().optional(),
  current_step: z.string().optional(),
  next: z
    .object({ title: z.string(), auto: z.boolean().catch(false) })
    .optional(),
  documents: z
    .array(z.object({ file_id: z.string(), name: z.string() }))
    .catch([]),
  notes: z
    .object({
      problem: z.string().optional(),
      goal: z.string().optional(),
      audience: z.string().optional(),
      target_date: z.string().optional(),
      features: z.array(z.string()).optional(),
      references: z.array(z.string()).optional(),
      decisions: z.array(z.string()).optional(),
      questions: z.array(z.string()).optional(),
    })
    .catch({}),
  feedback: z
    .array(
      z.object({
        mood: z.string().catch("neutral"),
        words: z.string().catch(""),
        at: z.string().nullable().catch(null),
      }),
    )
    .catch([]),
  steps: z
    .array(
      z.object({
        key: z.string(),
        label: z.string(),
        at: z.string().nullable().catch(null),
        done: z.boolean(),
        detail: z.string().catch(""),
      }),
    )
    .catch([]),
});
const overviewSchema = z.object({
  profile: z.object({
    name: z.string().optional(),
    business_name: z.string().optional(),
    business_type: z.string().optional(),
    location: z.string().optional(),
    role: z.string().optional(),
    industry: z.string().optional(),
    team_size: z.string().optional(),
    customers: z.string().optional(),
    channels: z.string().optional(),
    website: z.string().optional(),
    current_tools: z.string().optional(),
    decision_maker: z.string().optional(),
    found_us: z.string().optional(),
    goal: z.string().optional(),
    challenge: z.string().optional(),
    notes: z.string().optional(),
    language: z.string().nullable().catch(null),
    first_chat_at: z.string().nullable().catch(null),
    chats: z.number().catch(0),
    returning: z.boolean().catch(false),
  }),
  projects: z.array(projectSchema).catch([]),
  issues: z.array(issueSchema).catch([]),
  links: z.array(linkSchema).catch([]),
  headline: z.string().catch(""),
  counts: z.object({
    waiting_on_them: z.number(),
    waiting_on_us: z.number(),
    done: z.number(),
    paused: z.number(),
  }),
});
type Overview = z.infer<typeof overviewSchema>;
type Issue = Overview["issues"][number];
type Project = Overview["projects"][number];

/** How often the open page asks for the latest picture (it's live while you watch). */
const LIVE_EVERY_MS = 20_000;

/** What each request and project looked like, to spot what just changed. */
function signatures(o: Overview): Map<string, string> {
  return new Map([
    ...o.issues.map(
      (i) => [i.title, `${i.stage}|${i.ball_with}|${i.next_step}`] as const,
    ),
    ...o.projects.map(
      (p) => [p.lead_id, `${p.stage}|${p.steps_done ?? ""}`] as const,
    ),
  ]);
}

const LANGUAGE: Record<string, string> = {
  en: "English",
  roman_ur: "Roman Urdu",
  ar: "Arabic",
};
const LEAD_STAGE: Record<string, string> = {
  new: "New",
  qualified: "Brief confirmed",
  proposal: "Proposal",
  won: "Won",
  lost: "Lost",
};
const STAGES = [
  ["noted", "Noted"],
  ["need_answer", "Needs their answer"],
  ["on_it", "We're on it"],
  ["solution_ready", "Solution ready"],
  ["building", "Building"],
  ["live", "Live"],
] as const;
const LINK_LABEL: Record<string, string> = {
  shared_data: "shares data",
  same_cause: "same cause",
  depends_on: "depends on",
  part_of: "part of",
};

/** Whose turn it is decides the colour; the label always says it too. */
function tone(issue: Issue): { fill: string; ring: string; label: string } {
  if (["live", "closed"].includes(issue.stage))
    return { fill: "#1f9d63", ring: "#1f9d63", label: "Done" };
  if (issue.stage === "noted")
    return { fill: "#1b1830", ring: "#5A47F5", label: "Noted" };
  if (issue.ball_with === "client")
    return { fill: "#f5a524", ring: "#f5a524", label: "Waiting on them" };
  return { fill: "#3b82f6", ring: "#3b82f6", label: "Waiting on us" };
}

export function CustomerPiOverview({ customerId }: { customerId: string }) {
  const { can } = useSession();
  const query = useScopedQuery(
    ["customers", customerId, "pi-overview"],
    () =>
      apiRequest("GET", `/customers/${customerId}/pi-overview`, overviewSchema),
    // Live: a new message, step or answer shows up while the page is open.
    { refetchInterval: LIVE_EVERY_MS },
  );
  // What changed since the last look lights up for a moment.
  const [seen, setSeen] = useState<{
    at: number;
    sig: Map<string, string>;
    changed: Set<string>;
  }>({ at: 0, sig: new Map(), changed: new Set() });
  if (query.data && query.dataUpdatedAt !== seen.at) {
    const sig = signatures(query.data);
    const changed = new Set(
      seen.at
        ? [...sig].filter(([k, s]) => seen.sig.get(k) !== s).map(([k]) => k)
        : [],
    );
    setSeen({ at: query.dataUpdatedAt, sig, changed });
  }
  if (query.isPending)
    return <div className="h-40 animate-pulse rounded-xl bg-surface-sunken" />;
  if (query.isError) return null;
  const o = query.data;
  const p = o.profile;
  if (!p.chats && !o.projects.length) return null; // Not a pi customer yet.
  const changed = seen.changed;
  const justChanged = [
    ...o.issues.filter((i) => changed.has(i.title)).map((i) => i.title),
    ...o.projects.filter((d) => changed.has(d.lead_id)).map((d) => d.title),
  ];
  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader
            title="Business"
            icon={<Building2 />}
            description="What they told pi about themselves"
            actions={
              p.returning ? <Badge tone="info">Returning customer</Badge> : null
            }
          />
          <CardBody>
            <dl className="divide-y divide-border text-[13px]">
              {(
                [
                  ["Business", p.business_name],
                  ["What they do", p.business_type],
                  ["Location", p.location],
                  ["Their role", p.role],
                  ...(
                    [
                      ["Industry", p.industry],
                      ["Team size", p.team_size],
                      ["Sells to", p.customers],
                      ["Sells through", p.channels],
                      ["Website", p.website],
                      ["Uses today", p.current_tools],
                      ["Decides", p.decision_maker],
                      ["Found us via", p.found_us],
                      ["Their goal", p.goal],
                      ["Main challenge", p.challenge],
                      ["Worth knowing", p.notes],
                    ] as const
                  ).filter(([, value]) => value),
                  [
                    "Language",
                    p.language ? (LANGUAGE[p.language] ?? p.language) : "",
                  ],
                  [
                    "First chat",
                    p.first_chat_at ? formatDate(p.first_chat_at) : "",
                  ],
                  ["Chats with pi", String(p.chats)],
                ] as const
              ).map(([label, value]) => (
                <div
                  key={label}
                  className="flex justify-between gap-4 py-2 first:pt-0 last:pb-0"
                >
                  <dt className="text-muted-foreground">{label}</dt>
                  <dd className="min-w-0 text-right font-medium break-words">
                    {value || "—"}
                  </dd>
                </div>
              ))}
            </dl>
          </CardBody>
        </Card>
        <Card>
          <CardHeader
            title="Projects"
            icon={<FolderKanban />}
            description="Each project they confirmed, and where its journey is"
          />
          <CardBody>
            {o.projects.length === 0 ? (
              <p className="text-[13px] text-muted-foreground">
                No projects yet. Each project the customer confirms with pi
                becomes a deal here.
              </p>
            ) : (
              <ul className="space-y-3">
                {o.projects.map((d) => {
                  const pct =
                    d.steps_total && d.steps_done !== undefined
                      ? Math.round((d.steps_done / d.steps_total) * 100)
                      : null;
                  return (
                    <li
                      key={d.lead_id}
                      className="rounded-lg border border-border p-3"
                    >
                      <div className="flex items-start gap-2">
                        <div className="min-w-0 flex-1">
                          {can("sales.read") ? (
                            <Link
                              href={`/sales/leads/${d.lead_id}`}
                              className="text-[13px] font-medium text-primary hover:underline"
                            >
                              {d.title}
                            </Link>
                          ) : (
                            <span className="text-[13px] font-medium">
                              {d.title}
                            </span>
                          )}
                          {d.service && (
                            <p className="text-xs text-muted-foreground">
                              {d.service}
                            </p>
                          )}
                        </div>
                        <Badge>{LEAD_STAGE[d.stage] ?? d.stage}</Badge>
                      </div>
                      {pct !== null && (
                        <div className="mt-2">
                          <div
                            className="h-2 overflow-hidden rounded-full bg-surface-muted"
                            role="progressbar"
                            aria-valuenow={pct}
                            aria-valuemin={0}
                            aria-valuemax={100}
                            aria-label={`${d.title} journey`}
                          >
                            <div
                              className="h-full rounded-full bg-primary"
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                          <p className="mt-1 text-xs text-muted-foreground">
                            {d.steps_done} of {d.steps_total} steps · now:{" "}
                            {d.current_step}
                          </p>
                        </div>
                      )}
                      {d.next && (
                        <p className="mt-2 text-[13px]">
                          <span className="font-medium">Next: </span>
                          {d.next.title}
                          {d.next.auto && (
                            <Badge tone="info" className="ml-2">
                              pi does this
                            </Badge>
                          )}
                        </p>
                      )}
                      <ProjectNotes project={d} />
                      {d.documents.length > 0 && (
                        <ul className="mt-2 space-y-1">
                          {d.documents.map((doc) => (
                            <li key={doc.file_id}>
                              <a
                                href={customerFilesService.downloadUrl(
                                  doc.file_id,
                                )}
                                className="inline-flex items-center gap-1.5 text-[13px] text-primary hover:underline"
                              >
                                <FileText
                                  className="size-3.5"
                                  aria-hidden="true"
                                />
                                {doc.name}
                              </a>
                            </li>
                          ))}
                        </ul>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </CardBody>
        </Card>
      </div>
      <Card>
        <CardHeader
          title="Problem Map"
          icon={<Network />}
          description={`${o.issues.length} request${o.issues.length === 1 ? "" : "s"} · ${o.links.length} connection${o.links.length === 1 ? "" : "s"} found by pi`}
          actions={
            <span
              className="inline-flex items-center gap-1.5 rounded-full border border-border px-2.5 py-1 text-xs font-medium text-muted-foreground"
              title={`Refreshes every ${LIVE_EVERY_MS / 1000} seconds while open`}
            >
              <span className="relative flex size-2">
                <span
                  className={cn(
                    "absolute inline-flex size-full rounded-full bg-[#1f9d63] opacity-60",
                    query.isFetching
                      ? "animate-ping"
                      : "motion-safe:animate-pulse",
                  )}
                />
                <span className="relative inline-flex size-2 rounded-full bg-[#1f9d63]" />
              </span>
              Live ·{" "}
              {query.isFetching
                ? "updating…"
                : formatTime(new Date(query.dataUpdatedAt))}
            </span>
          }
        />
        <CardBody className="space-y-4">
          {justChanged.length > 0 && (
            <p
              key={seen.at}
              className="pm-in rounded-lg border border-[#1f9d63]/40 bg-[#1f9d63]/10 px-3 py-2 text-xs font-medium"
              role="status"
            >
              Just updated: {justChanged.slice(0, 3).join(", ")}
              {justChanged.length > 3
                ? ` and ${justChanged.length - 3} more`
                : ""}
            </p>
          )}
          {o.issues.length === 0 && o.projects.length === 0 ? (
            <p className="text-[13px] text-muted-foreground">
              Nothing yet. pi maps this customer&apos;s requests and how they
              connect as they talk.
            </p>
          ) : (
            <>
              <ProblemMap
                issues={o.issues}
                links={o.links}
                projects={o.projects}
                changed={changed}
                customer={p.business_name || p.name || "This customer"}
              />
              {o.issues.length > 0 && (
                <StageChart issues={o.issues} counts={o.counts} />
              )}
            </>
          )}
        </CardBody>
      </Card>
    </div>
  );
}

/** The Problem Map: each request is a card (full title, whose turn it is), and pi's
 * connections are curved, labelled lines between them. Cards fade in one by one, lines
 * draw themselves and anything waiting on the customer pulses gently (all motion is off
 * for people who ask for reduced motion). Pick a card or a line for its details. On a
 * phone it's a simple list. */
function ProblemMap({
  issues,
  links,
  projects,
  changed,
  customer,
}: {
  issues: Issue[];
  links: Overview["links"];
  projects: Project[];
  changed: Set<string>;
  customer: string;
}) {
  const [active, setActive] = useState<number | null>(null);
  const [picked, setPicked] = useState<View | null>(null);
  // No requests to draw yet: what's been done on the projects is the picture.
  const view: View = picked ?? (issues.length ? "map" : "progress");
  const asList = view === "list";
  const [activeLink, setActiveLink] = useState<number | null>(null);
  // Open problems first (pi's pick and its linked ones together), done ones last.
  const shown = order(issues).slice(0, 8);
  const n = shown.length;
  // The customer in the middle, their requests on both sides: every request hangs off
  // the customer, so it reads as one connected picture even with one or two requests.
  const W = 800;
  const CARD_W = 236;
  const CARD_H = 118;
  const STEP = 140;
  const HUB_W = 196;
  const HUB_H = 104;
  const sides = shown.map(
    (_, i) => (i % 2 ? "right" : "left") as "left" | "right",
  );
  const perSide = (side: "left" | "right") =>
    sides.filter((x) => x === side).length;
  const tallest = Math.max(perSide("left"), perSide("right"), 1);
  const H = Math.max(tallest * STEP - (STEP - CARD_H), HUB_H) + 32;
  const pos = shown.map((_, i) => {
    const side = sides[i];
    const count = perSide(side);
    const slot = sides.slice(0, i).filter((x) => x === side).length;
    const block = count * STEP - (STEP - CARD_H);
    const x = side === "left" ? 8 : W - 8 - CARD_W;
    const y = (H - block) / 2 + slot * STEP;
    return { x, y, cx: x + CARD_W / 2, cy: y + CARD_H / 2, side };
  });
  const hub = { x: (W - HUB_W) / 2, y: (H - HUB_H) / 2 };
  const spoke = (i: number) => {
    const p = pos[i];
    const fromX = p.side === "left" ? hub.x : hub.x + HUB_W;
    const fromY = H / 2 + (p.cy - H / 2) * 0.25;
    const toX = p.side === "left" ? p.x + CARD_W : p.x;
    const mx = (fromX + toX) / 2;
    return `M ${fromX} ${fromY} C ${mx} ${fromY}, ${mx} ${p.cy}, ${toX} ${p.cy}`;
  };
  const index = new Map(shown.map((issue, i) => [issue.title, i]));
  const visible = links
    .map((l) => ({ ...l, a: index.get(l.a_title), b: index.get(l.b_title) }))
    .filter(
      (l): l is typeof l & { a: number; b: number } =>
        l.a !== undefined && l.b !== undefined && l.a !== l.b,
    );
  const touches = (i: number) =>
    active !== null &&
    visible.some(
      (l) => (l.a === active || l.b === active) && (l.a === i || l.b === i),
    );
  const curve = (a: number, b: number, k = 0) => {
    const p = pos[a];
    const q = pos[b];
    const shift = ((k % 3) - 1) * 10;
    const inner = (c: typeof p) => (c.side === "left" ? c.x + CARD_W : c.x);
    if (p.side === q.side) {
      // Same side: a loop into the middle lane and back.
      const [t, u] = p.cy < q.cy ? [p, q] : [q, p];
      const x = inner(t);
      const reach = (t.side === "left" ? 1 : -1) * 64;
      return {
        d: `M ${x} ${t.cy + 18 + shift} C ${x + reach} ${t.cy + 18}, ${x + reach} ${u.cy - 18}, ${x} ${u.cy - 18 + shift}`,
        mx: x + reach * 0.78,
        my: (t.cy + u.cy) / 2,
      };
    }
    // Across: arc over (or under) the customer card.
    const [l, r] = p.side === "left" ? [p, q] : [q, p];
    // Alternate over and under the customer card, further out each time, so two
    // connections never share a label spot.
    const crossing = visible
      .slice(0, k)
      .filter((x) => pos[x.a].side !== pos[x.b].side).length;
    const above = crossing % 2 === 0;
    const out = 26 + Math.floor(crossing / 2) * 24;
    const arc = above ? hub.y - out : hub.y + HUB_H + out;
    const x1 = inner(l);
    const x2 = inner(r);
    return {
      d: `M ${x1} ${l.cy + shift} C ${x1 + 60} ${arc}, ${x2 - 60} ${arc}, ${x2} ${r.cy + shift}`,
      mx: W / 2,
      my: above ? hub.y - out + 10 : hub.y + HUB_H + out - 10,
    };
  };
  // pi's pick to start with: the open request that hurts most (urgency x impact).
  const open = shown
    .map((issue, i) => ({ i, score: issue.urgency * issue.impact, issue }))
    .filter(({ issue }) => !["live", "closed", "paused"].includes(issue.stage));
  const startHere =
    n > 1 && open.length
      ? open.reduce((best, x) => (x.score > best.score ? x : best)).i
      : null;
  const calm = useReducedMotion();
  const summary = (
    ["Waiting on them", "Waiting on us", "Noted", "Done"] as const
  )
    .map((label) => ({
      label,
      count: shown.filter((i) => tone(i).label === label).length,
      sample: shown.find((i) => tone(i).label === label),
    }))
    .filter((x) => x.count > 0);
  const detail = active !== null ? shown[active] : null;
  const link = activeLink !== null ? visible[activeLink] : null;

  return (
    <figure className="w-full">
      <Insight issues={shown} links={visible} />
      <style>{MAP_MOTION}</style>
      <div
        className="mb-3 flex flex-wrap items-center gap-2"
        aria-label="At a glance"
      >
        {summary.map(({ label, count, sample }) => (
          <span
            key={label}
            className="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface px-2.5 py-1 text-xs font-medium"
          >
            {sample && <StatusDot issue={sample} />}
            {count} {label.toLowerCase()}
          </span>
        ))}
        {startHere !== null && (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary">
            Start with: {shown[startHere].title}
          </span>
        )}
        <div
          role="tablist"
          aria-label="View"
          className="ml-auto inline-flex rounded-full border border-border p-0.5"
        >
          {VIEWS.filter(([v]) => issues.length || v === "progress").map(
            ([v, label]) => (
              <button
                key={v}
                type="button"
                role="tab"
                aria-selected={view === v}
                onClick={() => setPicked(v)}
                className={cn(
                  "rounded-full px-2.5 py-1 text-xs font-medium transition-colors",
                  view === v
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:text-foreground",
                  // A phone always gets the list in place of the drawing.
                  v === "list" && "hidden sm:inline-flex",
                )}
              >
                {label}
              </button>
            ),
          )}
        </div>
      </div>
      {view === "progress" ? (
        <Progress issues={issues} projects={projects} changed={changed} />
      ) : view === "card" ? (
        <CustomerCardView issues={issues} links={links} />
      ) : (
        <>
          {/* Phone: a simple list, each request with its status and connections. */}
          <ul className={cn("space-y-2", !asList && "sm:hidden")}>
            {shown.map((issue, i) => {
              const t = tone(issue);
              const linked = visible.filter(
                (l) => l.a === i || l.b === i,
              ).length;
              return (
                <li
                  key={`${issue.title}-${i}`}
                  className={cn(
                    "pm-in rounded-lg border border-border bg-surface px-3 py-2",
                    changed.has(issue.title) && "pm-flash",
                  )}
                  style={{ animationDelay: `${i * 60}ms` }}
                >
                  <p className="text-sm font-medium">{issue.title}</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    <span className="font-medium text-foreground">
                      Problem:{" "}
                    </span>
                    {issue.root_cause ||
                      issue.summary ||
                      issue.original_words ||
                      "—"}
                  </p>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    <span className="font-medium text-foreground">Next: </span>
                    {nextLine(issue)}
                  </p>
                  <p className="mt-0.5 flex items-center gap-1.5 text-xs text-muted-foreground">
                    <StatusDot issue={issue} /> {t.label}
                    {linked ? ` · linked to ${linked}` : ""}
                  </p>
                </li>
              );
            })}
          </ul>
          <div
            className={cn(
              "relative mx-auto hidden w-full max-w-3xl",
              !asList && "sm:block",
            )}
            style={{ aspectRatio: `${W} / ${H}` }}
            onMouseLeave={() => {
              setActive(null);
              setActiveLink(null);
            }}
          >
            <svg
              viewBox={`0 0 ${W} ${H}`}
              className="absolute inset-0 h-full w-full overflow-visible"
              aria-hidden="true"
            >
              {shown.map((issue, i) => {
                const d = spoke(i);
                const t = tone(issue);
                const faded = active !== null && active !== i;
                return (
                  <g key={`spoke-${i}`}>
                    <path
                      d={d}
                      fill="none"
                      pathLength={1}
                      className="pm-draw"
                      stroke={t.ring}
                      strokeWidth={active === i ? 2.5 : 1.5}
                      strokeLinecap="round"
                      style={{
                        animationDelay: `${150 + i * 90}ms`,
                        opacity: faded ? 0.15 : 0.55,
                        transition: "opacity 200ms",
                      }}
                    />
                    {!calm && (
                      <circle r={3} fill={t.ring} opacity={faded ? 0.1 : 0.85}>
                        <animateMotion
                          dur={`${2.6 + (i % 3) * 0.5}s`}
                          begin={`${(600 + i * 90) / 1000}s`}
                          repeatCount="indefinite"
                          path={d}
                        />
                      </circle>
                    )}
                  </g>
                );
              })}
              {visible.map((l, k) => {
                const { d } = curve(l.a, l.b, k);
                const lit =
                  activeLink === k ||
                  (active !== null && (l.a === active || l.b === active));
                const faded = active !== null && !lit;
                const dashed = l.type === "part_of" || l.type === "depends_on";
                return (
                  <g
                    key={k}
                    className="cursor-pointer"
                    onMouseEnter={() => {
                      setActiveLink(k);
                      setActive(null);
                    }}
                    onClick={() => setActiveLink(k)}
                  >
                    <path
                      d={d}
                      stroke="transparent"
                      strokeWidth={18}
                      fill="none"
                    />
                    <path
                      d={d}
                      fill="none"
                      pathLength={1}
                      className={dashed ? "pm-fade" : "pm-draw"}
                      style={{
                        animationDelay: `${n * 70 + k * 120}ms`,
                        opacity: faded ? 0.2 : 1,
                        transition: "opacity 200ms, stroke-width 200ms",
                      }}
                      stroke={lit ? "#7c6cf7" : "#8b7cf8"}
                      strokeWidth={lit ? 3 : 2}
                      strokeLinecap="round"
                      strokeDasharray={dashed ? "0.03 0.025" : undefined}
                    />
                    {!calm && (
                      <circle
                        r={3.5}
                        fill="#a99cff"
                        opacity={faded ? 0.15 : 0.9}
                      >
                        <animateMotion
                          dur={`${3.2 + (k % 3) * 0.6}s`}
                          begin={`${(n * 70 + k * 120 + 700) / 1000}s`}
                          repeatCount="indefinite"
                          path={d}
                        />
                      </circle>
                    )}
                  </g>
                );
              })}
            </svg>
            {visible.map((l, k) => {
              const { mx, my } = curve(l.a, l.b, k);
              const faded =
                active !== null && !(l.a === active || l.b === active);
              return (
                <button
                  type="button"
                  key={`label-${k}`}
                  onMouseEnter={() => {
                    setActiveLink(k);
                    setActive(null);
                  }}
                  onFocus={() => setActiveLink(k)}
                  className="pm-fade absolute -translate-x-1/2 -translate-y-1/2 rounded-full border border-primary/30 bg-surface px-2 py-0.5 text-[11px] font-medium whitespace-nowrap text-foreground shadow-sm transition-opacity"
                  style={{
                    left: `${(mx / W) * 100}%`,
                    top: `${(my / H) * 100}%`,
                    opacity: faded ? 0.25 : 1,
                    animationDelay: `${n * 70 + k * 120 + 300}ms`,
                  }}
                >
                  {l.reason || LINK_LABEL[l.type] || l.type}
                </button>
              );
            })}
            <div
              className="pm-in pm-hub absolute flex flex-col items-center justify-center rounded-2xl px-3 text-center text-white shadow-lg"
              style={{
                left: `${(hub.x / W) * 100}%`,
                top: `${(hub.y / H) * 100}%`,
                width: `${(HUB_W / W) * 100}%`,
                height: `${(HUB_H / H) * 100}%`,
                background: "linear-gradient(135deg, #2a2160 0%, #1b1830 100%)",
              }}
            >
              <span className="text-[10px] font-semibold tracking-wide text-[#a99cff] uppercase">
                Customer
              </span>
              <span className="line-clamp-1 text-sm font-semibold">
                {customer}
              </span>
              <span className="mt-0.5 text-[11px] text-white/70">
                {n} request{n === 1 ? "" : "s"} · {visible.length} connected
              </span>
            </div>
            {shown.map((issue, i) => {
              const t = tone(issue);
              const p = pos[i];
              const waiting = t.label === "Waiting on them";
              const dim = active !== null && active !== i && !touches(i);
              return (
                <button
                  type="button"
                  key={`${issue.title}-${i}`}
                  onMouseEnter={() => {
                    setActive(i);
                    setActiveLink(null);
                  }}
                  onFocus={() => {
                    setActive(i);
                    setActiveLink(null);
                  }}
                  onClick={() => setActive(i)}
                  aria-label={`${issue.title}: ${t.label}`}
                  className={cn(
                    "pm-in absolute flex flex-col gap-0.5 rounded-xl border bg-surface px-3 py-2.5 text-left shadow-sm transition-[opacity,transform,box-shadow] duration-200 hover:-translate-y-0.5 hover:shadow-md focus-visible:outline-2 focus-visible:outline-primary",
                    active === i ? "border-primary shadow-md" : "border-border",
                    waiting && "pm-pulse",
                    changed.has(issue.title) && "pm-flash",
                  )}
                  style={{
                    left: `${(p.x / W) * 100}%`,
                    top: `${(p.y / H) * 100}%`,
                    width: `${(CARD_W / W) * 100}%`,
                    height: `${(CARD_H / H) * 100}%`,
                    opacity: dim ? 0.35 : 1,
                    animationDelay: `${i * 70}ms`,
                    borderLeft: `4px solid ${t.ring}`,
                  }}
                >
                  {startHere === i && (
                    <span className="absolute -top-2.5 right-3 rounded-full bg-primary px-2 py-0.5 text-[10px] font-semibold text-primary-foreground shadow-sm">
                      Start here
                    </span>
                  )}
                  {issue.area && (
                    <span className="text-[10px] font-semibold tracking-wide text-muted-foreground uppercase">
                      {issue.area}
                    </span>
                  )}
                  <span className="line-clamp-1 text-[13px] leading-tight font-semibold">
                    {issue.title}
                  </span>
                  <span className="line-clamp-1 text-[11px] text-muted-foreground">
                    <span className="font-medium text-foreground">
                      Problem:{" "}
                    </span>
                    {issue.root_cause ||
                      issue.summary ||
                      issue.original_words ||
                      "—"}
                  </span>
                  <span className="line-clamp-1 text-[11px] text-muted-foreground">
                    <span className="font-medium text-foreground">Next: </span>
                    {nextLine(issue)}
                  </span>
                  <span className="mt-auto flex items-center gap-1.5 text-[11px] text-muted-foreground">
                    <StatusDot issue={issue} />
                    {t.label}
                  </span>
                </button>
              );
            })}
          </div>
          <div
            className="mt-3 min-h-[3.25rem] rounded-lg bg-surface-muted px-3 py-2 text-xs"
            aria-live="polite"
          >
            {detail ? (
              <>
                <p className="text-[13px] font-semibold">{detail.title}</p>
                <p className="mt-0.5 text-muted-foreground">
                  {tone(detail).label} ·{" "}
                  {STAGES.find(([k]) => k === detail.stage)?.[1] ??
                    detail.stage}
                  {detail.summary ? ` · ${detail.summary}` : ""}
                </p>
                {detail.next_step && (
                  <p className="mt-0.5">
                    <span className="font-medium">Next: </span>
                    {detail.next_step}
                  </p>
                )}
              </>
            ) : link ? (
              <>
                <p className="text-[13px] font-semibold">
                  {link.a_title} ↔ {link.b_title}
                </p>
                <p className="mt-0.5">{link.reason}</p>
                {link.benefit && (
                  <p className="mt-0.5 text-muted-foreground">{link.benefit}</p>
                )}
              </>
            ) : (
              <p className="pt-1 text-muted-foreground">
                Point at a request or a line to see what it is, whose turn it is
                and why pi connected them.
              </p>
            )}
          </div>
          <figcaption className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
            {[
              ["#3b82f6", "Waiting on us"],
              ["#f5a524", "Waiting on them"],
              ["#1f9d63", "Done"],
              ["#5A47F5", "Noted"],
            ].map(([color, label]) => (
              <span key={label} className="inline-flex items-center gap-1.5">
                <span
                  className="inline-block size-2.5 rounded-full"
                  style={{ background: color }}
                />
                {label}
              </span>
            ))}
            {visible.length > 0 && (
              <span>Dashed line: part of / depends on</span>
            )}
          </figcaption>
          {issues.length > shown.length && (
            <p className="mt-1 text-xs text-muted-foreground">
              +{issues.length - shown.length} more requests not drawn.
            </p>
          )}
        </>
      )}
    </figure>
  );
}

/** Open problems first, the most pressing (urgency x impact) leading, each followed by
 * the requests that share its solution; done and paused ones last. */
function order(issues: Issue[]): Issue[] {
  const closed = (i: Issue) => ["live", "closed", "paused"].includes(i.stage);
  const score = (i: Issue) => i.urgency * i.impact;
  const open = issues
    .filter((i) => !closed(i))
    .sort((a, b) => score(b) - score(a));
  const out: Issue[] = [];
  for (const issue of open) {
    if (out.includes(issue)) continue;
    out.push(issue);
    if (issue.solution_id)
      out.push(
        ...open.filter(
          (o) =>
            o !== issue &&
            o.solution_id === issue.solution_id &&
            !out.includes(o),
        ),
      );
  }
  return [...out, ...issues.filter(closed)];
}

/** "Next:" on a card: who does what. */
function nextLine(issue: Issue): string {
  if (issue.ball_with === "client" && issue.open_question)
    return `Customer: ${issue.open_question}`;
  if (issue.next_step) return issue.next_step;
  if (["live", "closed"].includes(issue.stage)) return "Nothing, it's done";
  return "pi is working it out";
}

/** pi's one-line picture above the map: what one solution covers, otherwise what's
 * waiting on the customer, otherwise the team's next step. */
function Insight({
  issues,
  links,
}: {
  issues: Issue[];
  links: Overview["links"];
}) {
  const groups = new Map<string, Issue[]>();
  for (const issue of issues)
    if (issue.solution_id && !["live", "closed"].includes(issue.stage))
      groups.set(issue.solution_id, [
        ...(groups.get(issue.solution_id) ?? []),
        issue,
      ]);
  const merged = [...groups.values()].find((g) => g.length > 1);
  const waiting = issues.find(
    (i) => i.ball_with === "client" && i.open_question,
  );
  let headline = "";
  let detail = "";
  if (merged) {
    const titles = merged.map((i) => i.title);
    const names =
      titles.length > 2
        ? `${titles.slice(0, -1).join(", ")} and ${titles.at(-1)}`
        : titles.join(" and ");
    const link = links.find(
      (l) => titles.includes(l.a_title) && titles.includes(l.b_title),
    );
    headline = `One solution can cover ${names}.`;
    detail =
      link?.benefit ||
      link?.reason ||
      merged.find((i) => i.solution_outline)?.solution_outline ||
      "";
  } else if (waiting) {
    headline = `Waiting on the customer: ${waiting.open_question}`;
    detail = waiting.title;
  } else {
    const next = issues.find(
      (i) => i.next_step && !["live", "closed"].includes(i.stage),
    );
    if (next) {
      headline = `Next: ${next.next_step}`;
      detail = next.title;
    }
  }
  if (!headline) return null;
  return (
    <div className="pm-in mb-3 rounded-xl bg-[#1b1830] px-4 py-3 text-white">
      <p className="text-[11px] font-semibold tracking-wide text-[#a99cff] uppercase">
        pi&apos;s picture
      </p>
      <p className="mt-0.5 text-sm font-semibold">{headline}</p>
      {detail && <p className="mt-0.5 text-xs text-white/70">{detail}</p>}
    </div>
  );
}

/** True when the person asked their device for less motion. */
function useReducedMotion(): boolean {
  return useSyncExternalStore(
    (change) => {
      const query = window.matchMedia(REDUCED);
      query.addEventListener("change", change);
      return () => query.removeEventListener("change", change);
    },
    () => window.matchMedia(REDUCED).matches,
    () => false,
  );
}
const REDUCED = "(prefers-reduced-motion: reduce)";

function StatusDot({ issue }: { issue: Issue }) {
  const t = tone(issue);
  return t.label === "Noted" ? (
    <span
      className="inline-block size-2.5 shrink-0 rounded-full border-2"
      style={{ borderColor: t.ring }}
    />
  ) : (
    <span
      className="inline-block size-2.5 shrink-0 rounded-full"
      style={{ background: t.ring }}
    />
  );
}

const MAP_MOTION = `
@keyframes pm-in { from { opacity: 0; transform: translateY(8px) scale(.97); } to { opacity: 1; transform: none; } }
@keyframes pm-draw { from { stroke-dashoffset: 1; } to { stroke-dashoffset: 0; } }
@keyframes pm-fade { from { opacity: 0; } to { opacity: 1; } }
@keyframes pm-pulse { 0%, 100% { box-shadow: 0 0 0 0 rgba(245,165,36,.45); } 50% { box-shadow: 0 0 0 6px rgba(245,165,36,0); } }
.pm-in { animation: pm-in 420ms cubic-bezier(.2,.8,.2,1) both; }
.pm-draw { stroke-dasharray: 1; stroke-dashoffset: 1; animation: pm-draw 700ms ease-out forwards; }
.pm-fade { animation: pm-fade 500ms ease-out both; }
@keyframes pm-glow { 0%, 100% { box-shadow: 0 0 0 0 rgba(139,124,248,.35); } 50% { box-shadow: 0 0 0 10px rgba(139,124,248,0); } }
.pm-hub { animation: pm-in 420ms cubic-bezier(.2,.8,.2,1) both, pm-glow 3s ease-in-out 1s infinite; }
.pm-pulse { animation: pm-in 420ms cubic-bezier(.2,.8,.2,1) both, pm-pulse 2.4s ease-in-out 1s infinite; }
@keyframes pm-flash { 0%, 60% { box-shadow: 0 0 0 3px rgba(31,157,99,.7); } 100% { box-shadow: 0 0 0 0 rgba(31,157,99,0); } }
.pm-flash { animation: pm-flash 3s ease-out both !important; }
@keyframes pm-now { 0%, 100% { box-shadow: 0 0 0 0 rgba(90,71,245,.45); } 50% { box-shadow: 0 0 0 5px rgba(90,71,245,0); } }
.pm-now { animation: pm-now 2s ease-in-out infinite; }
@keyframes pm-grow { from { transform: scaleX(0); } to { transform: scaleX(1); } }
@keyframes pm-pop { from { opacity: 0; transform: scale(.4); } to { opacity: 1; transform: none; } }
.pm-pop { transform-box: fill-box; transform-origin: center; animation: pm-pop 500ms cubic-bezier(.3,1.4,.5,1) both; }
.pm-grow { transform-origin: left; animation: pm-grow 700ms cubic-bezier(.2,.8,.2,1) both; }
@media (prefers-reduced-motion: reduce) {
  .pm-in, .pm-draw, .pm-fade, .pm-pulse, .pm-hub, .pm-flash, .pm-now, .pm-grow, .pm-pop { animation: none !important; stroke-dashoffset: 0; }
}
`;

/** How many requests sit at each stage of the journey. */
function StageChart({
  issues,
  counts,
}: {
  issues: Issue[];
  counts: Overview["counts"];
}) {
  const max = Math.max(
    1,
    ...STAGES.map(([k]) => issues.filter((i) => i.stage === k).length),
  );
  return (
    <div className="grid gap-4 md:grid-cols-[1fr_auto]">
      <div className="space-y-1.5" aria-label="Requests by stage">
        {STAGES.map(([key, label]) => {
          const n = issues.filter((i) => i.stage === key).length;
          return (
            <div key={key} className="flex items-center gap-2 text-xs">
              <span className="w-32 shrink-0 text-muted-foreground">
                {label}
              </span>
              <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-surface-muted">
                <div
                  className="h-full rounded-full bg-primary"
                  style={{ width: `${(n / max) * 100}%` }}
                />
              </div>
              <span className="w-5 text-right font-medium tabular-nums">
                {n}
              </span>
            </div>
          );
        })}
      </div>
      <div className="flex gap-3 text-center md:flex-col">
        <div>
          <p className="text-xl font-semibold text-[#c2810c]">
            {counts.waiting_on_them}
          </p>
          <p className="text-xs text-muted-foreground">Waiting on them</p>
        </div>
        <div>
          <p className="text-xl font-semibold text-[#3b82f6]">
            {counts.waiting_on_us}
          </p>
          <p className="text-xs text-muted-foreground">Waiting on us</p>
        </div>
        <div>
          <p className="text-xl font-semibold text-[#1f9d63]">{counts.done}</p>
          <p className="text-xs text-muted-foreground">Done</p>
        </div>
      </div>
    </div>
  );
}

type View = "map" | "progress" | "card" | "list";
const VIEWS = [
  ["map", "Map"],
  ["progress", "Progress"],
  ["card", "Customer's view"],
  ["list", "List"],
] as const;

/** What's been done so far: each project's journey step by step (done with its date,
 * the step it's on now, what's still ahead) and how far each request has come. */
function Progress({
  issues,
  projects,
  changed,
}: {
  issues: Issue[];
  projects: Project[];
  changed: Set<string>;
}) {
  const steps = projects.flatMap((d) => d.steps);
  const stepsDone = steps.filter((s) => s.done).length;
  const closed = issues.filter((i) =>
    ["live", "closed"].includes(i.stage),
  ).length;
  const moving = issues.filter(
    (i) => !["noted", "live", "closed", "paused"].includes(i.stage),
  ).length;
  const tiles = [
    {
      label: "Project steps done",
      value: steps.length ? `${stepsDone} of ${steps.length}` : "—",
      pct: steps.length ? stepsDone / steps.length : 0,
    },
    {
      label: "Requests in progress",
      value: `${moving} of ${issues.length}`,
      pct: issues.length ? moving / issues.length : 0,
    },
    {
      label: "Requests done",
      value: `${closed} of ${issues.length}`,
      pct: issues.length ? closed / issues.length : 0,
    },
  ];
  return (
    <div className="space-y-5">
      <div className="grid gap-3 sm:grid-cols-3">
        {tiles.map((t, i) => (
          <div
            key={t.label}
            className="pm-in rounded-xl border border-border bg-surface px-3 py-2.5"
            style={{ animationDelay: `${i * 60}ms` }}
          >
            <p className="text-xs text-muted-foreground">{t.label}</p>
            <p className="mt-0.5 text-lg font-semibold tabular-nums">
              {t.value}
            </p>
            <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-surface-muted">
              <div
                className="pm-grow h-full rounded-full bg-[#1f9d63]"
                style={{
                  width: `${Math.round(t.pct * 100)}%`,
                  animationDelay: `${200 + i * 80}ms`,
                }}
              />
            </div>
          </div>
        ))}
      </div>

      {projects.length > 0 && (
        <section aria-label="What's been done on each project">
          <h3 className="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
            What&apos;s been done
          </h3>
          <div className="grid gap-3 lg:grid-cols-2">
            {projects.map((d, k) => (
              <ProjectTimeline
                key={d.lead_id}
                project={d}
                fresh={changed.has(d.lead_id)}
                delay={k * 90}
              />
            ))}
          </div>
        </section>
      )}

      {issues.length > 0 && (
        <section aria-label="How far each request has come">
          <h3 className="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
            Each request
          </h3>
          <ul className="space-y-2">
            {order(issues).map((issue, i) => (
              <RequestTrack
                key={`${issue.title}-${i}`}
                issue={issue}
                fresh={changed.has(issue.title)}
                delay={i * 60}
              />
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function ProjectTimeline({
  project,
  fresh,
  delay,
}: {
  project: Project;
  fresh: boolean;
  delay: number;
}) {
  const now = project.steps.findIndex((s) => !s.done);
  const done = project.steps.filter((s) => s.done).length;
  return (
    <div
      className={cn(
        "pm-in rounded-xl border border-border bg-surface p-3",
        fresh && "pm-flash",
      )}
      style={{ animationDelay: `${delay}ms` }}
    >
      <div className="mb-2 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-[13px] font-semibold">{project.title}</p>
          {project.service && project.service !== project.title && (
            <p className="text-xs text-muted-foreground">{project.service}</p>
          )}
        </div>
        <Badge tone={now === -1 ? "success" : "info"}>
          {now === -1 ? "Complete" : `${done}/${project.steps.length}`}
        </Badge>
      </div>
      {project.steps.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          {LEAD_STAGE[project.stage] ?? project.stage}
        </p>
      ) : (
        <ol className="relative">
          {project.steps.map((s, i) => {
            const current = i === now;
            const last = i === project.steps.length - 1;
            const note = [
              s.detail !== project.title ? s.detail : "",
              s.done && s.at ? formatDate(s.at) : "",
            ]
              .filter(Boolean)
              .join(" · ");
            return (
              <li
                key={s.key}
                className="pm-in relative flex gap-2.5 pb-2.5 last:pb-0"
                style={{ animationDelay: `${delay + 120 + i * 45}ms` }}
              >
                {!last && (
                  <span
                    aria-hidden="true"
                    className={cn(
                      "absolute top-5 bottom-0 left-[9px] w-0.5",
                      s.done ? "bg-[#1f9d63]" : "bg-border",
                    )}
                  />
                )}
                <span
                  aria-hidden="true"
                  className={cn(
                    "relative z-10 mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full border-2",
                    s.done
                      ? "border-[#1f9d63] bg-[#1f9d63] text-white"
                      : current
                        ? "pm-now border-primary bg-surface"
                        : "border-border bg-surface",
                  )}
                >
                  {s.done ? (
                    <Check className="size-3" strokeWidth={3} />
                  ) : current ? (
                    <span className="size-1.5 rounded-full bg-primary" />
                  ) : null}
                </span>
                <div className="min-w-0 flex-1">
                  <p
                    className={cn(
                      "text-[13px] leading-5",
                      s.done
                        ? "font-medium"
                        : current
                          ? "font-semibold text-primary"
                          : "text-muted-foreground",
                    )}
                  >
                    {s.label}
                    {current && (
                      <span className="ml-1.5 text-[11px] font-medium">
                        · now
                      </span>
                    )}
                    <span className="sr-only">
                      {s.done ? " (done)" : current ? "" : " (to do)"}
                    </span>
                  </p>
                  {note && (
                    <p className="text-xs text-muted-foreground">{note}</p>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      )}
      {project.next && now !== -1 && (
        <p className="mt-2 rounded-lg bg-surface-muted px-2.5 py-1.5 text-xs">
          <span className="font-medium">Next: </span>
          {project.next.title}
          {project.next.auto && (
            <span className="ml-1 text-muted-foreground">(pi does this)</span>
          )}
        </p>
      )}
    </div>
  );
}

/** One request across the stages: filled up to where it is now. */
function RequestTrack({
  issue,
  fresh,
  delay,
}: {
  issue: Issue;
  fresh: boolean;
  delay: number;
}) {
  const t = tone(issue);
  const at =
    issue.stage === "closed"
      ? STAGES.length - 1
      : STAGES.findIndex(([k]) => k === issue.stage);
  const label =
    issue.stage === "paused"
      ? "Paused"
      : (STAGES[Math.max(at, 0)]?.[1] ?? issue.stage);
  return (
    <li
      className={cn(
        "pm-in rounded-lg border border-border bg-surface px-3 py-2",
        fresh && "pm-flash",
      )}
      style={{ animationDelay: `${delay}ms` }}
    >
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-0.5">
        <p className="text-[13px] font-medium">{issue.title}</p>
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <StatusDot issue={issue} />
          {label}
        </p>
      </div>
      <div
        className="mt-1.5 grid grid-cols-6 gap-1"
        role="img"
        aria-label={`${issue.title}: ${label}, stage ${Math.max(at, 0) + 1} of ${STAGES.length}`}
      >
        {STAGES.map(([key, name], i) => (
          <span
            key={key}
            title={name}
            className={cn(
              "pm-grow h-1.5 rounded-full",
              i > at && "bg-surface-muted",
            )}
            style={{
              background: i <= at ? t.ring : undefined,
              animationDelay: `${delay + 150 + i * 60}ms`,
            }}
          />
        ))}
      </div>
      <p className="mt-1 line-clamp-1 text-xs text-muted-foreground">
        <span className="font-medium text-foreground">Next: </span>
        {nextLine(issue)}
      </p>
    </li>
  );
}

const CARD_INK = "#1b1830";
// The preview card's rows: where the first starts and where the nodes sit.
const ROW_TOP = 6;
const NODE_X = 22;

/** "Customer's view": the Problem Map card pi sends the customer on WhatsApp (same
 * layout as the 1080 x 1350 PNG: a row per request with where it stands and how far it
 * has come, pi's connections between the rows, a count per status and one line on what
 * matters most) and how it lands in the chat. */
function CustomerCardView({
  issues,
  links,
}: {
  issues: Issue[];
  links: Overview["links"];
}) {
  const open = order(issues).filter(
    (i) => !["live", "closed"].includes(i.stage),
  );
  const shown = (open.length ? open : issues).slice(0, 5);
  const more = issues.length - shown.length;
  // Each request with where it stands, in the customer's words, like the PNG card.
  const rows = shown.map((issue) => {
    const t = tone(issue);
    const step = Math.max(
      issue.stage === "closed"
        ? STAGES.length - 1
        : STAGES.findIndex(([k]) => k === issue.stage),
      0,
    );
    const label =
      t.label === "Noted"
        ? "Noted"
        : t.label === "Done"
          ? "Done"
          : issue.stage === "solution_ready"
            ? "Solution ready"
            : t.label === "Waiting on them"
              ? "Waiting on you"
              : "We're on it";
    const color = label === "Solution ready" ? "#1f9d63" : t.ring;
    return { issue, label, step, color, hollow: t.label === "Noted" };
  });
  const ROW_H = rows.length <= 3 ? 64 : 46;
  const rowY = (i: number) => ROW_TOP + i * ROW_H + ROW_H / 2;
  const at = (title: string) => shown.findIndex((i) => i.title === title);
  const lines = links.filter((l) => at(l.a_title) >= 0 && at(l.b_title) >= 0);
  const groups = new Map<string, number>();
  for (const i of shown)
    if (i.solution_id)
      groups.set(i.solution_id, (groups.get(i.solution_id) ?? 0) + 1);
  const merged = Math.max(0, ...groups.values());
  const waiting = rows.filter((r) => r.label === "Waiting on you").length;
  const working = rows.filter((r) => r.label === "We're on it").length;
  const insight =
    merged >= 2
      ? `One system can fix ${merged === 3 ? "all three" : `${merged} of them`}.`
      : waiting
        ? `${waiting} request${waiting === 1 ? " needs" : "s need"} your answer.`
        : working
          ? `We're working on ${working} of your ${issues.length} requests.`
          : `Your ${issues.length} request${issues.length === 1 ? "" : "s"} at a glance.`;
  const chips = (
    [
      ["waiting on you", "#f5a524", false],
      ["we're on it", "#3b82f6", false],
      ["solution ready", "#1f9d63", false],
      ["noted", "#5A47F5", true],
    ] as const
  )
    .map(([label, color, hollow]) => ({
      label,
      color,
      hollow,
      count: rows.filter((r) =>
        hollow
          ? r.hollow
          : r.label ===
            (label === "waiting on you"
              ? "Waiting on you"
              : label === "we're on it"
                ? "We're on it"
                : "Solution ready"),
      ).length,
    }))
    .filter((c) => c.count > 0);
  const caption = [
    lines.length
      ? `pi found ${lines.length} connection${lines.length === 1 ? "" : "s"}.`
      : `Here's your map: ${shown.length} request${shown.length === 1 ? "" : "s"}.`,
    lines[0]?.reason || lines[0]?.benefit || "",
    "Full map: on your pi Customer page",
  ].filter(Boolean);
  const buttons = ["Makes sense", "Not related", "Show solution"];
  const today = new Date().toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
  });

  return (
    <div className="grid items-start gap-6 md:grid-cols-[minmax(0,340px)_minmax(0,1fr)] md:justify-center">
      {/* The card itself (4:5, like the PNG). */}
      <div
        className="pm-in mx-auto flex w-full max-w-[340px] flex-col rounded-2xl p-5 text-white shadow-lg"
        style={{ background: CARD_INK, aspectRatio: "4 / 5" }}
        aria-label="The map card pi sends the customer"
      >
        <div className="flex items-center gap-2">
          <span
            className="flex size-7 items-center justify-center rounded-full text-xs font-bold"
            style={{ background: "#5A47F5" }}
          >
            pi
          </span>
          <span className="text-sm font-bold">Your Problem Map</span>
          <span className="ml-auto text-[11px] text-[#a9a4c7]">{today}</span>
        </div>
        <div
          className="relative mt-3 flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl"
          style={{ background: "#26223f" }}
          role="img"
          aria-label={rows
            .map((r) => `${r.issue.title}: ${r.label}`)
            .join(", ")}
        >
          {/* A count per status: the card's legend. */}
          <div className="flex flex-wrap items-center justify-center gap-1 border-b border-[#34305a] px-2 py-2">
            {chips.map((c) => (
              <span
                key={c.label}
                className="inline-flex items-center gap-1 rounded-full bg-[#1b1830] px-2 py-0.5 text-[10px] text-[#e7e4f7]"
              >
                <span
                  className="inline-block size-2 rounded-full"
                  style={
                    c.hollow
                      ? { border: `2px solid ${c.color}` }
                      : { background: c.color }
                  }
                />
                {c.count} {c.label}
              </span>
            ))}
            {more > 0 && (
              <span className="text-[10px] text-[#a9a4c7]">+{more} more</span>
            )}
          </div>
          <div className="relative flex-1">
            <svg
              className="absolute inset-0 h-full w-full overflow-visible"
              aria-hidden="true"
            >
              {lines.map((l, k) => {
                const ya = rowY(at(l.a_title));
                const yb = rowY(at(l.b_title));
                const reach = 10 + (k % 3) * 6;
                const dashed = l.type === "part_of" || l.type === "depends_on";
                const d = `M ${NODE_X} ${ya} C ${NODE_X - reach * 2} ${ya}, ${NODE_X - reach * 2} ${yb}, ${NODE_X} ${yb}`;
                return (
                  <path
                    key={`${l.a_title}-${l.b_title}`}
                    d={d}
                    pathLength={1}
                    className={dashed ? "pm-fade" : "pm-draw"}
                    fill="none"
                    stroke="#a99cff"
                    strokeWidth={2}
                    strokeDasharray={dashed ? "0.05 0.04" : undefined}
                    style={{ animationDelay: `${400 + k * 150}ms` }}
                  />
                );
              })}
              {rows.map((r, i) => (
                <circle
                  key={r.issue.title}
                  className="pm-pop"
                  style={{ animationDelay: `${i * 110}ms` }}
                  cx={NODE_X}
                  cy={rowY(i)}
                  r={8 + Math.min(Math.max(r.issue.impact, 1), 5)}
                  fill={r.hollow ? CARD_INK : r.color}
                  stroke={r.hollow ? r.color : "#ffffff"}
                  strokeWidth={r.hollow ? 2.5 : 1.5}
                />
              ))}
            </svg>
            {rows.map((r, i) => (
              <div
                key={r.issue.title}
                className="pm-in absolute right-3 flex flex-col justify-center"
                style={{
                  left: NODE_X + 22,
                  top: ROW_TOP + i * ROW_H,
                  height: ROW_H,
                  animationDelay: `${120 + i * 90}ms`,
                }}
              >
                <span className="line-clamp-2 text-[12px] leading-tight font-semibold">
                  {r.issue.title}
                </span>
                <span className="mt-0.5 flex items-center gap-2">
                  <span
                    className="text-[10px] font-medium"
                    style={{ color: r.hollow ? "#c9c1ff" : r.color }}
                  >
                    {r.label}
                  </span>
                  <span className="ml-auto flex gap-0.5" aria-hidden="true">
                    {STAGES.map(([key], s) => (
                      <span
                        key={key}
                        className="h-1 w-2.5 rounded-full"
                        style={{
                          background: s <= r.step ? r.color : "#3a3558",
                        }}
                      />
                    ))}
                  </span>
                </span>
              </div>
            ))}
          </div>
        </div>
        <p className="mt-3 text-center text-sm leading-snug font-bold">
          {insight}
        </p>
        <div className="mt-3 flex items-center">
          <span className="text-[11px] text-[#a9a4c7]">pi Customer</span>
          <span
            className="ml-auto rounded-full px-3 py-1 text-[11px] font-bold"
            style={{ background: "#5A47F5" }}
          >
            See full map
          </span>
        </div>
      </div>

      {/* How it lands in the customer's WhatsApp. */}
      <div className="mx-auto w-full max-w-[300px] md:mx-0">
        <p className="mb-2 text-xs font-semibold text-muted-foreground">
          How it arrives in WhatsApp
        </p>
        <div
          className="pm-in rounded-xl rounded-tl-sm bg-[#dcf8c6] p-2 text-[13px] text-[#111b21] shadow-sm"
          style={{ animationDelay: "250ms" }}
        >
          <div
            className="mx-auto mb-2 flex aspect-[4/5] w-24 items-center justify-center rounded-md"
            style={{ background: CARD_INK }}
          >
            {/* A tiny version of the card: one bar per request. */}
            <div className="flex w-[78%] flex-col gap-1.5" aria-hidden="true">
              {rows.map((r) => (
                <div key={r.issue.title} className="flex items-center gap-1">
                  <span
                    className="size-2 shrink-0 rounded-full"
                    style={
                      r.hollow
                        ? { border: `1.5px solid ${r.color}` }
                        : { background: r.color }
                    }
                  />
                  <span className="h-1 flex-1 rounded-full bg-white/70" />
                </div>
              ))}
            </div>
          </div>
          {caption.map((line) => (
            <p key={line} className="px-1 leading-snug">
              {line}
            </p>
          ))}
          <p className="mt-1 text-right text-[10px] text-[#667781]">
            {new Date().toLocaleTimeString("en-GB", {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </p>
        </div>
        <div className="mt-1 space-y-1">
          {buttons.map((b, i) => (
            <div
              key={b}
              className="pm-in rounded-lg bg-[#f0fdf4] py-1.5 text-center text-[13px] font-medium text-[#047857] shadow-sm dark:bg-[#1f2c26] dark:text-[#4ade80]"
              style={{ animationDelay: `${400 + i * 80}ms` }}
            >
              {b}
            </div>
          ))}
        </div>
        <p className="mt-3 text-xs text-muted-foreground">
          pi sends this card when it finds a connection, when a new request
          makes three or more, or when the customer asks for their map (at least
          2 hours apart, inside the 24-hour window). &quot;Not related&quot;
          removes the connection.
        </p>
      </div>
    </div>
  );
}

const MOOD: Record<
  string,
  { label: string; tone: "success" | "warning" | "info" }
> = {
  happy: { label: "Happy", tone: "success" },
  unhappy: { label: "Unhappy", tone: "warning" },
  neutral: { label: "Feedback", tone: "info" },
};

/** pi's deep notes on a project: why they need it and what success means up front;
 * what it must do, what's decided, what's still open and their references one tap away.
 * The customer's feedback after delivery is shown with its mood. */
function ProjectNotes({ project }: { project: Project }) {
  const n = project.notes;
  const lists = (
    [
      ["Must have", n.features],
      ["Decided", n.decisions],
      ["Still open", n.questions],
      ["References", n.references],
    ] as const
  ).filter(([, items]) => items && items.length > 0);
  const lead = (
    [
      ["Problem", n.problem],
      ["Goal", n.goal],
      ["For", n.audience],
      ["Timeline", n.target_date],
    ] as const
  ).filter(([, value]) => value);
  const said = project.feedback.at(-1);
  if (!lead.length && !lists.length && !said) return null;
  return (
    <div className="mt-2 space-y-1.5 rounded-lg bg-surface-muted px-2.5 py-2 text-xs">
      {lead.map(([label, value]) => (
        <p key={label}>
          <span className="font-medium">{label}: </span>
          <span className="text-muted-foreground">{value}</span>
        </p>
      ))}
      {lists.length > 0 && (
        <details className="group">
          <summary className="cursor-pointer font-medium text-primary select-none">
            Project notes ·{" "}
            {lists
              .map(
                ([label, items]) => `${items!.length} ${label.toLowerCase()}`,
              )
              .join(" · ")}
          </summary>
          <div className="mt-1.5 grid gap-2 sm:grid-cols-2">
            {lists.map(([label, items]) => (
              <div key={label}>
                <p className="font-medium">{label}</p>
                <ul className="mt-0.5 space-y-0.5 text-muted-foreground">
                  {items!.map((item) => (
                    <li key={item} className="flex gap-1.5">
                      <span aria-hidden="true">•</span>
                      <span className="min-w-0 break-words">{item}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </details>
      )}
      {said && (
        <p className="flex flex-wrap items-center gap-1.5">
          <Badge tone={(MOOD[said.mood] ?? MOOD.neutral).tone}>
            {(MOOD[said.mood] ?? MOOD.neutral).label}
          </Badge>
          <span className="text-muted-foreground">
            &ldquo;{said.words}&rdquo;
          </span>
        </p>
      )}
    </div>
  );
}
