"use client";

import { useState } from "react";
import Link from "next/link";
import { z } from "zod";
import { Building2, FolderKanban, Network } from "lucide-react";
import { Badge, Card, CardBody, CardHeader } from "@/components/ui/display";
import { useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
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
          description={
            o.headline || "Their requests, and how pi connected them"
          }
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

/** Requests as circles (size = business impact) and pi's connections as labelled lines.
 * A fixed-size drawing (it never zooms with the page); hover or focus a circle for its
 * details, a line for why pi connected the two. */
function ProblemMap({
  issues,
  links,
}: {
  issues: Issue[];
  links: Overview["links"];
}) {
  const [hover, setHover] = useState<number | null>(null);
  const [hoverLink, setHoverLink] = useState<number | null>(null);
  const shown = issues.slice(0, 8);
  const n = shown.length;
  // The ring grows with the number of requests so circles and labels never touch.
  const ringR = n <= 1 ? 0 : n === 2 ? 150 : Math.max(120, 30 + 22 * n);
  const W = 640;
  const H = n <= 2 ? 160 : 2 * ringR + 110;
  const cx = W / 2;
  const cy = n <= 2 ? 66 : ringR + 50;
  const radius = (i: Issue) => 12 + 3 * Math.max(1, Math.min(5, i.impact));
  const pos = shown.map((_, i) => {
    // Two requests sit side by side; more go round a circle starting at the top.
    const start = n === 2 ? Math.PI : -Math.PI / 2;
    const angle = start + (2 * Math.PI * i) / Math.max(1, n);
    return { x: cx + ringR * Math.cos(angle), y: cy + ringR * Math.sin(angle) };
  });
  const index = new Map(shown.map((issue, i) => [issue.title, i]));
  const visible = links
    .map((l) => ({ ...l, a: index.get(l.a_title), b: index.get(l.b_title) }))
    .filter(
      (l): l is typeof l & { a: number; b: number } =>
        l.a !== undefined && l.b !== undefined,
    );
  const touches = (i: number) =>
    visible.some(
      (l) => (l.a === hover || l.b === hover) && (l.a === i || l.b === i),
    );
  const dim = (i: number) => hover !== null && hover !== i && !touches(i);
  const short = (t: string) => (t.length > 22 ? `${t.slice(0, 21)}…` : t);
  const active = hover !== null ? shown[hover] : null;
  const activeLink = hoverLink !== null ? visible[hoverLink] : null;
  const tip = active
    ? pos[hover!]
    : activeLink
      ? {
          x: (pos[activeLink.a].x + pos[activeLink.b].x) / 2,
          y: (pos[activeLink.a].y + pos[activeLink.b].y) / 2,
        }
      : null;

  return (
    <figure className="mx-auto w-full max-w-2xl">
      <div className="relative">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="block h-auto w-full rounded-xl bg-[#1b1830]"
          role="img"
          aria-label={`Problem Map: ${n} requests, ${visible.length} connections`}
          onMouseLeave={() => {
            setHover(null);
            setHoverLink(null);
          }}
        >
          {visible.map((l, k) => {
            const a = pos[l.a];
            const b = pos[l.b];
            const dashed = l.type === "part_of" || l.type === "depends_on";
            const lit =
              hover === null ? hoverLink === k : l.a === hover || l.b === hover;
            // Lines run edge to edge; the label sits outside, away from the circles.
            const dx = b.x - a.x;
            const dy = b.y - a.y;
            const len = Math.hypot(dx, dy) || 1;
            const ra = radius(shown[l.a]) + 3;
            const rb = radius(shown[l.b]) + 3;
            const x1 = a.x + (dx / len) * ra;
            const y1 = a.y + (dy / len) * ra;
            const x2 = b.x - (dx / len) * rb;
            const y2 = b.y - (dy / len) * rb;
            const midX = (a.x + b.x) / 2;
            const midY = (a.y + b.y) / 2;
            const out = Math.hypot(midX - cx, midY - cy);
            const push = out > 1 ? 18 / out : 0;
            const mx = midX + (midX - cx) * push;
            const my = midY + (midY - cy) * push;
            const label = LINK_LABEL[l.type] ?? l.type;
            return (
              <g
                key={k}
                className="cursor-help"
                opacity={hover !== null && !lit ? 0.25 : 1}
                onMouseEnter={() => setHoverLink(k)}
                onMouseLeave={() => setHoverLink(null)}
              >
                {/* A wide invisible line makes the thin one easy to hover. */}
                <line
                  x1={x1}
                  y1={y1}
                  x2={x2}
                  y2={y2}
                  stroke="transparent"
                  strokeWidth={16}
                />
                <line
                  x1={x1}
                  y1={y1}
                  x2={x2}
                  y2={y2}
                  stroke={lit ? "#c4b8ff" : "#8b7cf8"}
                  strokeWidth={lit ? 3 : 2}
                  strokeDasharray={dashed ? "7 5" : undefined}
                />
                <rect
                  x={mx - label.length * 3.4 - 8}
                  y={my - 11}
                  width={label.length * 6.8 + 16}
                  height={22}
                  rx={11}
                  fill="#2a2546"
                  stroke="#4b4280"
                />
                <text
                  x={mx}
                  y={my + 4}
                  textAnchor="middle"
                  fontSize="11"
                  fill="#e4e0ff"
                >
                  {label}
                </text>
              </g>
            );
          })}
          {shown.map((issue, i) => {
            const t = tone(issue);
            const r = radius(issue);
            const p = pos[i];
            return (
              <g
                key={`${issue.title}-${i}`}
                tabIndex={0}
                role="button"
                aria-label={`${issue.title}: ${t.label}`}
                className="cursor-pointer outline-none"
                opacity={dim(i) ? 0.3 : 1}
                onMouseEnter={() => setHover(i)}
                onFocus={() => setHover(i)}
                onBlur={() => setHover(null)}
              >
                <circle
                  cx={p.x}
                  cy={p.y}
                  r={r + (hover === i ? 3 : 0)}
                  fill={t.fill}
                  stroke={hover === i ? "#ffffff" : t.ring}
                  strokeWidth={t.label === "Noted" ? 3 : 2}
                />
                <text
                  x={p.x}
                  y={p.y + r + 16}
                  textAnchor="middle"
                  fontSize="12"
                  fontWeight="600"
                  fill="#ffffff"
                >
                  {short(issue.title)}
                </text>
              </g>
            );
          })}
        </svg>
        {tip && (active || activeLink) && (
          <div
            role="tooltip"
            className="pointer-events-none absolute z-10 w-64 -translate-x-1/2 rounded-lg border border-border bg-surface p-3 text-left text-xs shadow-lg"
            style={{
              left: `${Math.min(85, Math.max(15, (tip.x / W) * 100))}%`,
              top: `${(tip.y / H) * 100}%`,
              transform: `translate(-50%, ${tip.y > H / 2 ? "calc(-100% - 18px)" : "18px"})`,
            }}
          >
            {active ? (
              <>
                <p className="text-[13px] font-semibold">{active.title}</p>
                <p className="mt-1">
                  <span
                    className="mr-1 inline-block size-2 rounded-full align-middle"
                    style={{ background: tone(active).ring }}
                  />
                  {tone(active).label} ·{" "}
                  {STAGES.find(([k]) => k === active.stage)?.[1] ??
                    active.stage}
                </p>
                {active.summary && (
                  <p className="mt-1 text-muted-foreground">{active.summary}</p>
                )}
                {active.next_step && (
                  <p className="mt-1">
                    <span className="font-medium">Next: </span>
                    {active.next_step}
                  </p>
                )}
              </>
            ) : activeLink ? (
              <>
                <p className="text-[13px] font-semibold">
                  {activeLink.a_title} ↔ {activeLink.b_title}
                </p>
                <p className="mt-1">{activeLink.reason}</p>
                {activeLink.benefit && (
                  <p className="mt-1 text-muted-foreground">
                    {activeLink.benefit}
                  </p>
                )}
              </>
            ) : null}
          </div>
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
        <span>
          Solid line: shared data / same cause · dashed: part of / depends on
        </span>
        <span>Hover a circle or line for details</span>
      </figcaption>
      {issues.length > shown.length && (
        <p className="mt-1 text-xs text-muted-foreground">
          +{issues.length - shown.length} more requests not drawn.
        </p>
      )}
    </figure>
  );
}

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
