"use client";

import { useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { z } from "zod";
import { Building2, FolderKanban, Network } from "lucide-react";
import { Badge, Card, CardBody, CardHeader } from "@/components/ui/display";
import { useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import { cn } from "@/lib/utils";
import { formatDate } from "@/lib/format";
import { apiRequest } from "@/services/api-client";

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
});
const overviewSchema = z.object({
  profile: z.object({
    business_name: z.string().optional(),
    business_type: z.string().optional(),
    location: z.string().optional(),
    role: z.string().optional(),
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
  const query = useScopedQuery(["customers", customerId, "pi-overview"], () =>
    apiRequest("GET", `/customers/${customerId}/pi-overview`, overviewSchema),
  );
  if (query.isPending)
    return <div className="h-40 animate-pulse rounded-xl bg-surface-sunken" />;
  if (query.isError) return null;
  const o = query.data;
  const p = o.profile;
  if (!p.chats && !o.projects.length) return null; // Not a pi customer yet.
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
            o.links.length ? (
              <Badge tone="info">
                {o.links.length} connection{o.links.length === 1 ? "" : "s"}
              </Badge>
            ) : null
          }
        />
        <CardBody className="space-y-4">
          {o.issues.length === 0 ? (
            <p className="text-[13px] text-muted-foreground">
              Nothing yet. pi maps this customer&apos;s requests and how they
              connect as they talk.
            </p>
          ) : (
            <>
              <ProblemMap issues={o.issues} links={o.links} />
              <StageChart issues={o.issues} counts={o.counts} />
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
}: {
  issues: Issue[];
  links: Overview["links"];
}) {
  const [active, setActive] = useState<number | null>(null);
  const [activeLink, setActiveLink] = useState<number | null>(null);
  // Open problems first (pi's pick and its linked ones together), done ones last.
  const shown = order(issues).slice(0, 8);
  const n = shown.length;
  // Two staggered columns with a wide lane between them: every line runs through the
  // lane, so its label is never hidden behind a card. Only as tall as it needs to be.
  const W = 720;
  const CARD_W = 252;
  const CARD_H = 118;
  const STEP = 148; // vertical distance between cards in the same column
  const LEFT = 24;
  const RIGHT = W - 24 - CARD_W;
  const pos = shown.map((_, i) => {
    const x = n === 1 ? (W - CARD_W) / 2 : i % 2 ? RIGHT : LEFT;
    const y = 12 + Math.floor(i / 2) * STEP + (i % 2 ? STEP / 2 : 0);
    return { x, y, cx: x + CARD_W / 2, cy: y + CARD_H / 2 };
  });
  const H = Math.max(...pos.map((p) => p.y), 0) + CARD_H + 12;
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
    // Lines meeting the same card leave from slightly different points.
    const shift = ((k % 3) - 1) * 12;
    const p = { ...pos[a], cy: pos[a].cy + shift };
    const q = { ...pos[b], cy: pos[b].cy + shift };
    if (Math.abs(p.cx - q.cx) > CARD_W) {
      // Across the lane: from the side of one card to the side of the other.
      const [l, r] = p.cx < q.cx ? [p, q] : [q, p];
      const x1 = l.x + CARD_W;
      const x2 = r.x;
      const mx = (x1 + x2) / 2;
      return {
        d: `M ${x1} ${l.cy} C ${mx} ${l.cy}, ${mx} ${r.cy}, ${x2} ${r.cy}`,
        mx,
        my: (l.cy + r.cy) / 2,
      };
    }
    // Same column: out into the lane and back, so it never runs through a card.
    const [t, u] = p.cy < q.cy ? [p, q] : [q, p];
    const side = t.x < W / 2 ? 1 : -1;
    const x = side > 0 ? t.x + CARD_W : t.x;
    const reach = 70 * side;
    return {
      d: `M ${x} ${t.cy} C ${x + reach} ${t.cy}, ${x + reach} ${u.cy}, ${x} ${u.cy}`,
      mx: x + reach * 0.75,
      my: (t.cy + u.cy) / 2,
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
      <div className="mb-3 flex flex-wrap gap-2" aria-label="At a glance">
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
      </div>
      {/* Phone: a simple list, each request with its status and connections. */}
      <ul className="space-y-2 sm:hidden">
        {shown.map((issue, i) => {
          const t = tone(issue);
          const linked = visible.filter((l) => l.a === i || l.b === i).length;
          return (
            <li
              key={`${issue.title}-${i}`}
              className="pm-in rounded-lg border border-border bg-surface px-3 py-2"
              style={{ animationDelay: `${i * 60}ms` }}
            >
              <p className="text-sm font-medium">{issue.title}</p>
              <p className="mt-0.5 flex items-center gap-1.5 text-xs text-muted-foreground">
                <StatusDot issue={issue} /> {t.label}
                {linked ? ` · linked to ${linked}` : ""}
              </p>
            </li>
          );
        })}
      </ul>
      <div
        className="relative mx-auto hidden w-full max-w-3xl sm:block"
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
                <path d={d} stroke="transparent" strokeWidth={18} fill="none" />
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
                  <circle r={3.5} fill="#a99cff" opacity={faded ? 0.15 : 0.9}>
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
          const faded = active !== null && !(l.a === active || l.b === active);
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
                <span className="font-medium text-foreground">Problem: </span>
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
              {STAGES.find(([k]) => k === detail.stage)?.[1] ?? detail.stage}
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
            Point at a request or a line to see what it is, whose turn it is and
            why pi connected them.
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
        {visible.length > 0 && <span>Dashed line: part of / depends on</span>}
      </figcaption>
      {issues.length > shown.length && (
        <p className="mt-1 text-xs text-muted-foreground">
          +{issues.length - shown.length} more requests not drawn.
        </p>
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
.pm-pulse { animation: pm-in 420ms cubic-bezier(.2,.8,.2,1) both, pm-pulse 2.4s ease-in-out 1s infinite; }
@media (prefers-reduced-motion: reduce) {
  .pm-in, .pm-draw, .pm-fade, .pm-pulse { animation: none !important; stroke-dashoffset: 0; }
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
