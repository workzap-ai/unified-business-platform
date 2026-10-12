"use client";

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
    return { fill: "transparent", ring: "#5A47F5", label: "Noted" };
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

/** Requests as circles (size = business impact) and pi's connections as labelled lines. */
function ProblemMap({
  issues,
  links,
}: {
  issues: Issue[];
  links: Overview["links"];
}) {
  const shown = issues.slice(0, 8);
  const W = 640;
  const H = shown.length <= 2 ? 220 : 320;
  const cx = W / 2;
  const cy = H / 2;
  const r = shown.length <= 1 ? 0 : Math.min(W, H) / 2 - 70;
  const at = new Map(
    shown.map((issue, i) => {
      const angle = (2 * Math.PI * i) / shown.length - Math.PI / 2;
      return [
        issue.title,
        { x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) },
      ] as const;
    }),
  );
  const visible = links.filter((l) => at.has(l.a_title) && at.has(l.b_title));
  return (
    <figure>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="h-auto w-full rounded-xl bg-[#1b1830]"
        role="img"
        aria-label={`Problem Map: ${shown.length} requests, ${visible.length} connections`}
      >
        {visible.map((l, i) => {
          const a = at.get(l.a_title)!;
          const b = at.get(l.b_title)!;
          const dashed = l.type === "part_of" || l.type === "depends_on";
          return (
            <g key={i}>
              <line
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                stroke="#8b7cf8"
                strokeWidth={3}
                strokeDasharray={dashed ? "8 6" : undefined}
              />
              <text
                x={(a.x + b.x) / 2}
                y={(a.y + b.y) / 2 - 8}
                textAnchor="middle"
                fontSize="13"
                fill="#d9d4ff"
              >
                {LINK_LABEL[l.type] ?? l.type}
              </text>
            </g>
          );
        })}
        {shown.map((issue) => {
          const pos = at.get(issue.title)!;
          const t = tone(issue);
          const radius = 22 + 5 * Math.max(1, Math.min(5, issue.impact));
          return (
            <g key={issue.title}>
              <circle
                cx={pos.x}
                cy={pos.y}
                r={radius}
                fill={t.fill}
                stroke={t.ring}
                strokeWidth={t.fill === "transparent" ? 4 : 2}
              />
              <text
                x={pos.x}
                y={pos.y + radius + 18}
                textAnchor="middle"
                fontSize="14"
                fontWeight="600"
                fill="#ffffff"
              >
                {issue.title.length > 26
                  ? `${issue.title.slice(0, 25)}…`
                  : issue.title}
              </text>
            </g>
          );
        })}
      </svg>
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
        <span>Solid line: shared data / same cause · dashed: part of</span>
      </figcaption>
      {visible.length > 0 && (
        <ul className="mt-3 space-y-1 text-[13px]">
          {visible.map((l, i) => (
            <li key={i}>
              <span className="font-medium">
                {l.a_title} ↔ {l.b_title}:
              </span>{" "}
              {l.reason}
              {l.benefit ? ` (${l.benefit})` : ""}
            </li>
          ))}
        </ul>
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
