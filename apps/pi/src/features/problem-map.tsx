"use client";

/**
 * The team's Problem Map for one customer, as in Owner OS: four views of the same
 * picture.
 * - Map: the customer in the middle, their requests on both sides, pi's connections as
 *   labelled curves. Point at a card or a line for its details.
 * - Progress: each project's journey step by step and how far each request has come.
 * - Customer's view: the map card pi sends on WhatsApp and how it lands in the chat.
 * - List: the same requests as plain rows (always the view on a phone).
 * Motion is off for people who ask for reduced motion.
 */

import { Check } from "lucide-react";
import { useState, useSyncExternalStore } from "react";

import { Badge, cn } from "@/components/ui";
import { date } from "@/lib/format";

export type MapIssue = {
  title: string;
  stage: string;
  ball_with: string;
  summary: string;
  next_step: string;
  impact: number;
  urgency: number;
  area: string;
  open_question: string;
  root_cause: string;
  solution_outline: string;
  solution_id: string;
  original_words: string;
};

export type MapLink = {
  a_title: string;
  b_title: string;
  type: string;
  reason: string;
  benefit: string | null;
};

export type MapStep = {
  key: string;
  label: string;
  at: string | null;
  done: boolean;
  detail: string;
};

export type MapProject = {
  lead_id: string;
  title: string;
  stage: string;
  service: string;
  next?: { title: string; auto: boolean };
  steps: MapStep[];
};

export type MapCounts = {
  waiting_on_them: number;
  waiting_on_us: number;
  done: number;
  paused: number;
};

export const LEAD_STAGE: Record<string, string> = {
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

const GREEN = "#1f9d63";
const AMBER = "#f5a524";
const BLUE = "#3b82f6";
const VIOLET = "#5A47F5";
const INK = "#15132b";

/** Whose turn it is decides the colour; the label always says it too. */
function tone(issue: MapIssue): { ring: string; label: string } {
  if (["live", "closed"].includes(issue.stage))
    return { ring: GREEN, label: "Done" };
  if (issue.stage === "noted") return { ring: VIOLET, label: "Noted" };
  if (issue.ball_with === "client")
    return { ring: AMBER, label: "Waiting on them" };
  return { ring: BLUE, label: "Waiting on us" };
}

type View = "map" | "progress" | "card" | "list";
const VIEWS = [
  ["map", "Map"],
  ["progress", "Progress"],
  ["card", "Customer's view"],
  ["list", "List"],
] as const;

export function ProblemMapViews({
  issues,
  links,
  projects,
  changed,
  customer,
}: {
  issues: MapIssue[];
  links: MapLink[];
  projects: MapProject[];
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
  // The customer in the middle, their requests on both sides.
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
    // Across: alternate over and under the customer card, further out each time, so
    // two connections never share a label spot.
    const [l, r] = p.side === "left" ? [p, q] : [q, p];
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
            {sample ? <StatusDot issue={sample} /> : null}
            {count} {label.toLowerCase()}
          </span>
        ))}
        {startHere !== null ? (
          <span
            className="inline-flex items-center gap-1.5 rounded-full bg-accent-soft px-2.5 py-1 text-xs font-medium text-accent-soft-foreground"
            data-user-text
          >
            Start with: {shown[startHere].title}
          </span>
        ) : null}
        <div
          role="tablist"
          aria-label="View"
          className="ms-auto inline-flex rounded-full border border-border p-0.5"
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
                  "min-h-8 rounded-full px-2.5 py-1 text-xs font-medium transition-colors",
                  view === v
                    ? "bg-accent text-accent-foreground"
                    : "text-muted-foreground hover:text-foreground",
                  // A phone always gets the list in place of the drawing.
                  v === "list" && "hidden sm:inline-flex sm:items-center",
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
                  <p className="text-sm font-medium" data-user-text>
                    {issue.title}
                  </p>
                  <p
                    className="mt-0.5 text-xs text-muted-foreground"
                    data-user-text
                  >
                    <span className="font-medium text-foreground">
                      Problem:{" "}
                    </span>
                    {problemLine(issue)}
                  </p>
                  <p
                    className="mt-0.5 text-xs text-muted-foreground"
                    data-user-text
                  >
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
                    {!calm ? (
                      <circle r={3} fill={t.ring} opacity={faded ? 0.1 : 0.85}>
                        <animateMotion
                          dur={`${2.6 + (i % 3) * 0.5}s`}
                          begin={`${(600 + i * 90) / 1000}s`}
                          repeatCount="indefinite"
                          path={d}
                        />
                      </circle>
                    ) : null}
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
                    {!calm ? (
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
                    ) : null}
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
                  className="pm-fade absolute -translate-x-1/2 -translate-y-1/2 whitespace-nowrap rounded-full border border-accent/30 bg-surface px-2 py-0.5 text-[11px] font-medium text-foreground shadow-sm transition-opacity"
                  style={{
                    left: `${(mx / W) * 100}%`,
                    top: `${(my / H) * 100}%`,
                    opacity: faded ? 0.25 : 1,
                    animationDelay: `${n * 70 + k * 120 + 300}ms`,
                  }}
                  data-user-text
                >
                  {l.reason || LINK_LABEL[l.type] || l.type}
                </button>
              );
            })}
            <div
              className="pm-in pm-hub absolute flex flex-col items-center justify-center rounded-2xl px-3 text-center text-white shadow-md"
              style={{
                left: `${(hub.x / W) * 100}%`,
                top: `${(hub.y / H) * 100}%`,
                width: `${(HUB_W / W) * 100}%`,
                height: `${(HUB_H / H) * 100}%`,
                background: `linear-gradient(135deg, #2a2160 0%, ${INK} 100%)`,
              }}
            >
              <span className="text-[10px] font-semibold uppercase tracking-wide text-[#a99cff]">
                Customer
              </span>
              <span
                className="line-clamp-1 text-sm font-semibold"
                data-user-text
              >
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
                    "pm-in absolute flex flex-col gap-0.5 rounded-xl border bg-surface px-3 py-2.5 text-start shadow-sm transition-[opacity,transform,box-shadow] duration-200 hover:-translate-y-0.5 hover:shadow-md focus-visible:outline-2 focus-visible:outline-ring",
                    active === i ? "border-accent shadow-md" : "border-border",
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
                    borderInlineStart: `4px solid ${t.ring}`,
                  }}
                >
                  {startHere === i ? (
                    <span className="absolute -top-2.5 end-3 rounded-full bg-accent px-2 py-0.5 text-[10px] font-semibold text-accent-foreground shadow-sm">
                      Start here
                    </span>
                  ) : null}
                  {issue.area ? (
                    <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                      {issue.area}
                    </span>
                  ) : null}
                  <span
                    className="line-clamp-1 text-[13px] font-semibold leading-tight"
                    data-user-text
                  >
                    {issue.title}
                  </span>
                  <span
                    className="line-clamp-1 text-[11px] text-muted-foreground"
                    data-user-text
                  >
                    <span className="font-medium text-foreground">
                      Problem:{" "}
                    </span>
                    {problemLine(issue)}
                  </span>
                  <span
                    className="line-clamp-1 text-[11px] text-muted-foreground"
                    data-user-text
                  >
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
            className={cn(
              "mt-3 hidden min-h-[3.25rem] rounded-lg bg-surface-muted px-3 py-2 text-xs",
              !asList && "sm:block",
            )}
            aria-live="polite"
          >
            {detail ? (
              <>
                <p className="text-[13px] font-semibold" data-user-text>
                  {detail.title}
                </p>
                <p className="mt-0.5 text-muted-foreground" data-user-text>
                  {tone(detail).label} ·{" "}
                  {STAGES.find(([k]) => k === detail.stage)?.[1] ??
                    detail.stage}
                  {detail.summary ? ` · ${detail.summary}` : ""}
                </p>
                {detail.next_step ? (
                  <p className="mt-0.5" data-user-text>
                    <span className="font-medium">Next: </span>
                    {detail.next_step}
                  </p>
                ) : null}
              </>
            ) : link ? (
              <>
                <p className="text-[13px] font-semibold" data-user-text>
                  {link.a_title} ↔ {link.b_title}
                </p>
                <p className="mt-0.5" data-user-text>
                  {link.reason}
                </p>
                {link.benefit ? (
                  <p className="mt-0.5 text-muted-foreground" data-user-text>
                    {link.benefit}
                  </p>
                ) : null}
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
              [BLUE, "Waiting on us"],
              [AMBER, "Waiting on them"],
              [GREEN, "Done"],
              [VIOLET, "Noted"],
            ].map(([color, label]) => (
              <span key={label} className="inline-flex items-center gap-1.5">
                <span
                  className="inline-block size-2.5 rounded-full"
                  style={{ background: color }}
                />
                {label}
              </span>
            ))}
            {visible.length > 0 ? (
              <span>Dashed line: part of / depends on</span>
            ) : null}
          </figcaption>
          {issues.length > shown.length ? (
            <p className="mt-1 text-xs text-muted-foreground">
              +{issues.length - shown.length} more requests not drawn.
            </p>
          ) : null}
        </>
      )}
    </figure>
  );
}

/** Open problems first, the most pressing (urgency x impact) leading, each followed by
 * the requests that share its solution; done and paused ones last. */
function order(issues: MapIssue[]): MapIssue[] {
  const closed = (i: MapIssue) =>
    ["live", "closed", "paused"].includes(i.stage);
  const score = (i: MapIssue) => i.urgency * i.impact;
  const open = issues
    .filter((i) => !closed(i))
    .sort((a, b) => score(b) - score(a));
  const out: MapIssue[] = [];
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

function problemLine(issue: MapIssue): string {
  return issue.root_cause || issue.summary || issue.original_words || "—";
}

/** "Next:" on a card: who does what. */
function nextLine(issue: MapIssue): string {
  if (issue.ball_with === "client" && issue.open_question)
    return `Customer: ${issue.open_question}`;
  if (issue.next_step) return issue.next_step;
  if (["live", "closed"].includes(issue.stage)) return "Nothing, it's done";
  return "pi is working it out";
}

/** pi's one-line picture above the map: what one solution covers, otherwise what's
 * waiting on the customer, otherwise the team's next step. */
function Insight({ issues, links }: { issues: MapIssue[]; links: MapLink[] }) {
  const groups = new Map<string, MapIssue[]>();
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
    <div
      className="pm-in mb-3 rounded-xl px-4 py-3 text-white"
      style={{ background: INK }}
    >
      <p className="text-[11px] font-semibold uppercase tracking-wide text-[#a99cff]">
        pi&apos;s picture
      </p>
      <p className="mt-0.5 text-sm font-semibold" data-user-text>
        {headline}
      </p>
      {detail ? (
        <p className="mt-0.5 text-xs text-white/70" data-user-text>
          {detail}
        </p>
      ) : null}
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

function StatusDot({ issue }: { issue: MapIssue }) {
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
export function StageChart({
  issues,
  counts,
}: {
  issues: MapIssue[];
  counts: MapCounts;
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
                  className="h-full rounded-full bg-accent"
                  style={{ width: `${(n / max) * 100}%` }}
                />
              </div>
              <span className="w-5 text-end font-medium tabular-nums">{n}</span>
            </div>
          );
        })}
      </div>
      <div className="flex gap-3 text-center md:flex-col">
        <div>
          <p className="text-xl font-semibold text-warning">
            {counts.waiting_on_them}
          </p>
          <p className="text-xs text-muted-foreground">Waiting on them</p>
        </div>
        <div>
          <p className="text-xl font-semibold text-info">
            {counts.waiting_on_us}
          </p>
          <p className="text-xs text-muted-foreground">Waiting on us</p>
        </div>
        <div>
          <p className="text-xl font-semibold text-success">{counts.done}</p>
          <p className="text-xs text-muted-foreground">Done</p>
        </div>
      </div>
    </div>
  );
}

/** What's been done so far: each project's journey step by step (done with its date,
 * the step it's on now, what's still ahead) and how far each request has come. */
function Progress({
  issues,
  projects,
  changed,
}: {
  issues: MapIssue[];
  projects: MapProject[];
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
                className="pm-grow h-full rounded-full"
                style={{
                  background: GREEN,
                  width: `${Math.round(t.pct * 100)}%`,
                  animationDelay: `${200 + i * 80}ms`,
                }}
              />
            </div>
          </div>
        ))}
      </div>

      {projects.length > 0 ? (
        <section aria-label="What's been done on each project">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
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
      ) : null}

      {issues.length > 0 ? (
        <section aria-label="How far each request has come">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
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
      ) : null}
    </div>
  );
}

function ProjectTimeline({
  project,
  fresh,
  delay,
}: {
  project: MapProject;
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
          <p className="text-[13px] font-semibold" data-user-text>
            {project.title}
          </p>
          {project.service && project.service !== project.title ? (
            <p className="text-xs text-muted-foreground" data-user-text>
              {project.service}
            </p>
          ) : null}
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
              s.done && s.at ? date(s.at) : "",
            ]
              .filter(Boolean)
              .join(" · ");
            return (
              <li
                key={s.key}
                className="pm-in relative flex gap-2.5 pb-2.5 last:pb-0"
                style={{ animationDelay: `${delay + 120 + i * 45}ms` }}
              >
                {!last ? (
                  <span
                    aria-hidden="true"
                    className={cn(
                      "absolute bottom-0 start-[9px] top-5 w-0.5",
                      !s.done && "bg-border",
                    )}
                    style={s.done ? { background: GREEN } : undefined}
                  />
                ) : null}
                <span
                  aria-hidden="true"
                  className={cn(
                    "relative z-10 mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full border-2",
                    s.done
                      ? "text-white"
                      : current
                        ? "pm-now border-accent bg-surface"
                        : "border-border bg-surface",
                  )}
                  style={
                    s.done
                      ? { background: GREEN, borderColor: GREEN }
                      : undefined
                  }
                >
                  {s.done ? (
                    <Check className="size-3" strokeWidth={3} />
                  ) : current ? (
                    <span className="size-1.5 rounded-full bg-accent" />
                  ) : null}
                </span>
                <div className="min-w-0 flex-1">
                  <p
                    className={cn(
                      "text-[13px] leading-5",
                      s.done
                        ? "font-medium"
                        : current
                          ? "font-semibold text-accent"
                          : "text-muted-foreground",
                    )}
                  >
                    {s.label}
                    {current ? (
                      <span className="ms-1.5 text-[11px] font-medium">
                        · now
                      </span>
                    ) : null}
                    <span className="sr-only">
                      {s.done ? " (done)" : current ? "" : " (to do)"}
                    </span>
                  </p>
                  {note ? (
                    <p className="text-xs text-muted-foreground" data-user-text>
                      {note}
                    </p>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ol>
      )}
      {project.next && now !== -1 ? (
        <p className="mt-2 rounded-lg bg-surface-muted px-2.5 py-1.5 text-xs">
          <span className="font-medium">Next: </span>
          {project.next.title}
          {project.next.auto ? (
            <span className="ms-1 text-muted-foreground">(pi does this)</span>
          ) : null}
        </p>
      ) : null}
    </div>
  );
}

/** One request across the stages: filled up to where it is now. */
function RequestTrack({
  issue,
  fresh,
  delay,
}: {
  issue: MapIssue;
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
        <p className="text-[13px] font-medium" data-user-text>
          {issue.title}
        </p>
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
      <p
        className="mt-1 line-clamp-1 text-xs text-muted-foreground"
        data-user-text
      >
        <span className="font-medium text-foreground">Next: </span>
        {nextLine(issue)}
      </p>
    </li>
  );
}

// The preview card's rows: where the first starts and where the nodes sit.
const ROW_TOP = 6;
const NODE_X = 22;

/** "Customer's view": the Problem Map card pi sends the customer on WhatsApp (same
 * layout as the PNG: a row per request with where it stands and how far it has come,
 * pi's connections between the rows, a count per status and one line on what matters
 * most) and how it lands in the chat. */
function CustomerCardView({
  issues,
  links,
}: {
  issues: MapIssue[];
  links: MapLink[];
}) {
  const open = order(issues).filter(
    (i) => !["live", "closed"].includes(i.stage),
  );
  const shown = (open.length ? open : issues).slice(0, 5);
  const more = issues.length - shown.length;
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
    const color = label === "Solution ready" ? GREEN : t.ring;
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
      ["waiting on you", "Waiting on you", AMBER, false],
      ["we're on it", "We're on it", BLUE, false],
      ["solution ready", "Solution ready", GREEN, false],
      ["noted", "Noted", VIOLET, true],
    ] as const
  )
    .map(([label, match, color, hollow]) => ({
      label,
      color,
      hollow,
      count: rows.filter((r) => (hollow ? r.hollow : r.label === match)).length,
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
        className="pm-in mx-auto flex w-full max-w-[340px] flex-col rounded-2xl p-5 text-white shadow-md"
        style={{ background: INK, aspectRatio: "4 / 5" }}
        aria-label="The map card pi sends the customer"
      >
        <div className="flex items-center gap-2">
          <span
            className="flex size-7 items-center justify-center rounded-full text-xs font-bold"
            style={{ background: VIOLET }}
          >
            pi
          </span>
          <span className="text-sm font-bold">Your Problem Map</span>
          <span className="ms-auto text-[11px] text-[#a9a4c7]">{today}</span>
        </div>
        <div
          className="relative mt-3 flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl"
          style={{ background: "#26223f" }}
          role="img"
          aria-label={rows
            .map((r) => `${r.issue.title}: ${r.label}`)
            .join(", ")}
        >
          <div className="flex flex-wrap items-center justify-center gap-1 border-b border-[#34305a] px-2 py-2">
            {chips.map((c) => (
              <span
                key={c.label}
                className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] text-[#e7e4f7]"
                style={{ background: INK }}
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
            {more > 0 ? (
              <span className="text-[10px] text-[#a9a4c7]">+{more} more</span>
            ) : null}
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
                  fill={r.hollow ? INK : r.color}
                  stroke={r.hollow ? r.color : "#ffffff"}
                  strokeWidth={r.hollow ? 2.5 : 1.5}
                />
              ))}
            </svg>
            {rows.map((r, i) => (
              <div
                key={r.issue.title}
                className="pm-in absolute end-3 flex flex-col justify-center"
                style={{
                  insetInlineStart: NODE_X + 22,
                  top: ROW_TOP + i * ROW_H,
                  height: ROW_H,
                  animationDelay: `${120 + i * 90}ms`,
                }}
              >
                <span
                  className="line-clamp-2 text-[12px] font-semibold leading-tight"
                  data-user-text
                >
                  {r.issue.title}
                </span>
                <span className="mt-0.5 flex items-center gap-2">
                  <span
                    className="text-[10px] font-medium"
                    style={{ color: r.hollow ? "#c9c1ff" : r.color }}
                  >
                    {r.label}
                  </span>
                  <span className="ms-auto flex gap-0.5" aria-hidden="true">
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
        <p className="mt-3 text-center text-sm font-bold leading-snug">
          {insight}
        </p>
        <div className="mt-3 flex items-center">
          <span className="text-[11px] text-[#a9a4c7]">pi Customer</span>
          <span
            className="ms-auto rounded-full px-3 py-1 text-[11px] font-bold"
            style={{ background: VIOLET }}
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
          className="pm-in rounded-xl rounded-ss-sm border border-border bg-bubble-pi p-2 text-[13px] text-foreground shadow-sm"
          style={{ animationDelay: "250ms" }}
        >
          <div
            className="mx-auto mb-2 flex aspect-[4/5] w-24 items-center justify-center rounded-md"
            style={{ background: INK }}
          >
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
            <p key={line} className="px-1 leading-snug" data-user-text>
              {line}
            </p>
          ))}
          <p className="mt-1 text-end text-[10px] text-muted-foreground">
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
              className="pm-in rounded-lg border border-border bg-surface py-1.5 text-center text-[13px] font-medium text-accent shadow-sm"
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
