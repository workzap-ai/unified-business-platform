"use client";

/**
 * The team's picture of one customer, as in Owner OS: who they are (what they told pi,
 * including the deeper profile), their projects with the journey, pi's deep notes and
 * the customer's feedback, and their requests on the Problem Map (Map, Progress,
 * Customer's view, List). Live: the page asks for the latest picture every 20 seconds
 * and lights up what just changed. One call: GET /customers/{id}/pi-overview
 * (read-only, no AI call).
 */

import { useQuery } from "@tanstack/react-query";
import { Building2, FileText, FolderKanban, Network } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import {
  Badge,
  Card,
  CardSection,
  ErrorState,
  LoadingBlock,
  cn,
} from "@/components/ui";
import { PriorityChart } from "@/features/customer/visuals";
import { fileDownloadUrl } from "@/features/customer-files";
import {
  LEAD_STAGE,
  ProblemMapViews,
  StageChart,
  type MapCounts,
  type MapIssue,
  type MapLink,
  type MapStep,
} from "@/features/problem-map";
import { errorText, get } from "@/lib/api";
import type { CustomerIssue, IssueLink } from "@/lib/customer-api";
import { date } from "@/lib/format";
import { useBusinessKey, useCan } from "@/lib/session";

type Notes = {
  problem?: string;
  goal?: string;
  audience?: string;
  target_date?: string;
  features?: string[];
  references?: string[];
  decisions?: string[];
  questions?: string[];
};

type Feedback = { mood?: string; words?: string; at?: string | null };

type Project = {
  lead_id: string;
  title: string;
  stage: string;
  value: string | null;
  currency: string;
  service: string;
  scope: string;
  steps_done?: number;
  steps_total?: number;
  current_step?: string;
  next?: { title: string; detail: string; auto: boolean };
  documents?: { file_id: string; name: string }[];
  notes?: Notes;
  feedback?: Feedback[];
  steps?: Partial<MapStep>[];
};

type Profile = {
  name?: string;
  business_name?: string;
  business_type?: string;
  location?: string;
  role?: string;
  industry?: string;
  team_size?: string;
  customers?: string;
  channels?: string;
  website?: string;
  current_tools?: string;
  decision_maker?: string;
  found_us?: string;
  goal?: string;
  challenge?: string;
  notes?: string;
  language: string | null;
  first_chat_at: string | null;
  last_message_at: string | null;
  chats: number;
  returning: boolean;
};

type Overview = {
  profile: Profile;
  projects: Project[];
  issues: CustomerIssue[];
  links: IssueLink[];
  headline: string;
  counts: MapCounts;
};

/** How often the open page asks for the latest picture (it's live while you watch). */
const LIVE_EVERY_MS = 20_000;

const LANGUAGE: Record<string, string> = {
  en: "English",
  roman_ur: "Roman Urdu",
  ar: "Arabic",
};

/** The deeper profile pi learns in the chat, shown only once it knows each one. */
const MORE: [keyof Profile, string][] = [
  ["industry", "Industry"],
  ["team_size", "Team size"],
  ["customers", "Sells to"],
  ["channels", "Sells through"],
  ["website", "Website"],
  ["current_tools", "Uses today"],
  ["decision_maker", "Decides"],
  ["found_us", "Found us via"],
  ["goal", "Their goal"],
  ["challenge", "Main challenge"],
  ["notes", "Worth knowing"],
];

const MOOD: Record<
  string,
  { label: string; tone: "success" | "warning" | "info" }
> = {
  happy: { label: "Happy", tone: "success" },
  unhappy: { label: "Unhappy", tone: "warning" },
  neutral: { label: "Feedback", tone: "info" },
};

const text = (value: unknown) => (typeof value === "string" ? value : "");
const num = (value: unknown, fallback: number) =>
  typeof value === "number" ? value : fallback;

/** The API's issues with every field the map reads filled in. */
function mapIssues(issues: CustomerIssue[]): MapIssue[] {
  return issues.map((raw) => {
    const i = raw as unknown as Record<string, unknown>;
    return {
      title: text(i.title),
      stage: text(i.stage) || "noted",
      ball_with: text(i.ball_with) || "pi",
      summary: text(i.summary),
      next_step: text(i.next_step),
      impact: num(i.impact, 3),
      urgency: num(i.urgency, 3),
      area: text(i.area),
      open_question: text(i.open_question),
      root_cause: text(i.root_cause),
      solution_outline: text(i.solution_outline),
      solution_id: text(i.solution_id),
      original_words: text(i.original_words),
    };
  });
}

function mapLinks(links: IssueLink[]): MapLink[] {
  return links.map((raw) => {
    const l = raw as unknown as Record<string, unknown>;
    return {
      a_title: text(l.a_title),
      b_title: text(l.b_title),
      type: text(l.type),
      reason: text(l.reason),
      benefit: text(l.benefit) || null,
    };
  });
}

function steps(project: Project): MapStep[] {
  return (project.steps ?? []).map((s, i) => ({
    key: s.key ?? String(i),
    label: s.label ?? "",
    at: s.at ?? null,
    done: Boolean(s.done),
    detail: s.detail ?? "",
  }));
}

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

function Row({ label, value }: { label: string; value?: string | null }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-border py-2 text-sm last:border-0">
      <span className="shrink-0 text-muted-foreground">{label}</span>
      <span className="min-w-0 break-words text-end font-medium" data-user-text>
        {value || "—"}
      </span>
    </div>
  );
}

export function CustomerOverview({ id }: { id: string }) {
  const key = useBusinessKey();
  const can = useCan();
  const query = useQuery({
    queryKey: key(["customer-overview", id]),
    queryFn: () => get<Overview>(`/customers/${id}/pi-overview`),
    // Live: a new message, step or answer shows up while the page is open.
    refetchInterval: LIVE_EVERY_MS,
  });
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
    return <LoadingBlock rows={3} label="Loading overview" />;
  if (query.isError)
    return (
      <ErrorState
        message={errorText(query.error)}
        onRetry={() => query.refetch()}
      />
    );
  const o = query.data;
  const p = o.profile;
  const changed = seen.changed;
  const issues = mapIssues(o.issues);
  const links = mapLinks(o.links);
  const projects = o.projects.map((d) => ({
    lead_id: d.lead_id,
    title: d.title,
    stage: d.stage,
    service: d.service ?? "",
    next: d.next ? { title: d.next.title, auto: d.next.auto } : undefined,
    steps: steps(d),
  }));
  const justChanged = [
    ...o.issues.filter((i) => changed.has(i.title)).map((i) => i.title),
    ...o.projects.filter((d) => changed.has(d.lead_id)).map((d) => d.title),
  ];
  const open = o.issues.filter((i) => !["live", "closed"].includes(i.stage));
  const more = MORE.filter(([field]) => p[field]);
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          ["Waiting on them", o.counts.waiting_on_them, "text-warning"],
          ["Waiting on us", o.counts.waiting_on_us, "text-info"],
          ["Done", o.counts.done, "text-success"],
          ["Projects", o.projects.length, "text-accent"],
        ].map(([label, n, tone]) => (
          <Card key={String(label)}>
            <CardSection className="py-4">
              <p className="text-xs text-muted-foreground">{label}</p>
              <p className={`mt-1 text-2xl font-semibold ${tone}`}>{n}</p>
            </CardSection>
          </Card>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardSection className="space-y-2">
            <div className="flex items-center gap-2">
              <Building2 className="size-5 text-accent" aria-hidden />
              <div className="min-w-0">
                <h2 className="font-semibold">Business</h2>
                <p className="text-xs text-muted-foreground">
                  What they told pi about themselves
                </p>
              </div>
              {p.returning ? (
                <Badge tone="info" className="ms-auto">
                  Returning customer
                </Badge>
              ) : null}
            </div>
            <div>
              <Row label="Business" value={p.business_name} />
              <Row label="What they do" value={p.business_type} />
              <Row label="Location" value={p.location} />
              <Row label="Their role" value={p.role} />
              {more.map(([field, label]) => (
                <Row key={field} label={label} value={String(p[field])} />
              ))}
              <Row
                label="Language"
                value={p.language ? (LANGUAGE[p.language] ?? p.language) : null}
              />
              <Row
                label="First chat"
                value={p.first_chat_at ? date(p.first_chat_at) : null}
              />
              <Row label="Chats with pi" value={String(p.chats)} />
            </div>
            {!p.business_name ? (
              <p className="text-xs text-muted-foreground">
                pi asks for their business early in the chat and fills this in.
              </p>
            ) : null}
          </CardSection>
        </Card>

        <Card>
          <CardSection className="space-y-3">
            <div className="flex items-center gap-2">
              <FolderKanban className="size-5 text-accent" aria-hidden />
              <div className="min-w-0">
                <h2 className="font-semibold">Projects</h2>
                <p className="text-xs text-muted-foreground">
                  Each project they confirmed, and where its journey is
                </p>
              </div>
            </div>
            {o.projects.length === 0 ? (
              <p className="text-sm text-muted-foreground">
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
                      className={cn(
                        "rounded-lg border border-border p-3",
                        changed.has(d.lead_id) && "pm-flash",
                      )}
                    >
                      <div className="flex items-start gap-2">
                        <div className="min-w-0 flex-1">
                          {can("sales.read") ? (
                            <Link
                              href={`/deals/${d.lead_id}`}
                              className="font-medium text-accent hover:underline"
                              data-user-text
                            >
                              {d.title}
                            </Link>
                          ) : (
                            <span className="font-medium" data-user-text>
                              {d.title}
                            </span>
                          )}
                          {d.service ? (
                            <p
                              className="text-xs text-muted-foreground"
                              data-user-text
                            >
                              {d.service}
                            </p>
                          ) : null}
                        </div>
                        <Badge>{LEAD_STAGE[d.stage] ?? d.stage}</Badge>
                      </div>
                      {pct !== null ? (
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
                              className="h-full rounded-full bg-accent"
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                          <p className="mt-1 text-xs text-muted-foreground">
                            {d.steps_done} of {d.steps_total} steps · now:{" "}
                            {d.current_step}
                          </p>
                        </div>
                      ) : null}
                      {d.next ? (
                        <p className="mt-2 text-sm">
                          <span className="font-medium">Next: </span>
                          {d.next.title}
                          {d.next.auto ? (
                            <Badge tone="accent" className="ms-2">
                              pi does this
                            </Badge>
                          ) : null}
                        </p>
                      ) : null}
                      <ProjectNotes project={d} />
                      {d.documents?.length ? (
                        <ul className="mt-2 space-y-1">
                          {d.documents.map((doc) => (
                            <li key={doc.file_id}>
                              <a
                                href={fileDownloadUrl(doc.file_id)}
                                className="inline-flex min-h-8 items-center gap-1.5 text-sm text-accent hover:underline"
                                data-user-text
                              >
                                <FileText
                                  className="size-4 shrink-0"
                                  aria-hidden
                                />
                                {doc.name}
                              </a>
                            </li>
                          ))}
                        </ul>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            )}
          </CardSection>
        </Card>
      </div>

      <Card>
        <CardSection className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <Network className="size-5 text-accent" aria-hidden />
            <div className="min-w-0">
              <h2 className="font-semibold">Problem Map</h2>
              <p className="text-xs text-muted-foreground">
                {o.issues.length} request{o.issues.length === 1 ? "" : "s"} ·{" "}
                {o.links.length} connection{o.links.length === 1 ? "" : "s"}{" "}
                found by pi
              </p>
            </div>
            <LiveBadge
              fetching={query.isFetching}
              updatedAt={query.dataUpdatedAt}
            />
          </div>
          {o.headline ? (
            <p className="text-sm text-muted-foreground" data-user-text>
              {o.headline}
            </p>
          ) : null}
          {justChanged.length > 0 ? (
            <p
              key={seen.at}
              className="rounded-lg border border-success/40 bg-success-soft px-3 py-2 text-xs font-medium"
              role="status"
              data-user-text
            >
              Just updated: {justChanged.slice(0, 3).join(", ")}
              {justChanged.length > 3
                ? ` and ${justChanged.length - 3} more`
                : ""}
            </p>
          ) : null}
          {o.issues.length === 0 && o.projects.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Nothing yet. pi maps this customer&apos;s requests and how they
              connect as they talk.
            </p>
          ) : (
            <>
              <ProblemMapViews
                issues={issues}
                links={links}
                projects={projects}
                changed={changed}
                customer={p.business_name || p.name || "This customer"}
              />
              {issues.length > 0 ? (
                <StageChart issues={issues} counts={o.counts} />
              ) : null}
            </>
          )}
        </CardSection>
      </Card>

      {open.length >= 3 ? (
        <Card>
          <CardSection className="space-y-3">
            <h2 className="font-semibold">Where to start</h2>
            <PriorityChart issues={open} links={o.links} lang="en" />
          </CardSection>
        </Card>
      ) : null}
      {p.last_message_at ? (
        <p className="text-xs text-muted-foreground">
          Last message {date(p.last_message_at)}
        </p>
      ) : null}
    </div>
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
      className="ms-auto inline-flex items-center gap-1.5 rounded-full border border-border px-2.5 py-1 text-xs font-medium text-muted-foreground"
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
        : new Date(updatedAt).toLocaleTimeString("en", {
            hour: "numeric",
            minute: "2-digit",
          })}
    </span>
  );
}

/** pi's deep notes on a project: why they need it and what success means up front;
 * what it must do, what's decided, what's still open and their references one tap away.
 * The customer's latest feedback after delivery is shown with its mood. */
function ProjectNotes({ project }: { project: Project }) {
  const n = project.notes ?? {};
  const lists = (
    [
      ["Must have", n.features ?? []],
      ["Decided", n.decisions ?? []],
      ["Still open", n.questions ?? []],
      ["References", n.references ?? []],
    ] as [string, string[]][]
  ).filter(([, items]) => items.length > 0);
  const lead = (
    [
      ["Problem", n.problem],
      ["Goal", n.goal],
      ["For", n.audience],
      ["Timeline", n.target_date],
    ] as const
  ).filter(([, value]) => value);
  const said = project.feedback?.at(-1);
  if (!lead.length && !lists.length && !said) return null;
  const mood = MOOD[said?.mood ?? ""] ?? MOOD.neutral;
  return (
    <div className="mt-2 space-y-1.5 rounded-lg bg-surface-muted px-3 py-2 text-xs">
      {lead.map(([label, value]) => (
        <p key={label}>
          <span className="font-medium">{label}: </span>
          <span className="text-muted-foreground" data-user-text>
            {value}
          </span>
        </p>
      ))}
      {lists.length > 0 ? (
        <details>
          <summary className="cursor-pointer select-none py-1 font-medium text-accent">
            Project notes ·{" "}
            {lists
              .map(([label, items]) => `${items.length} ${label.toLowerCase()}`)
              .join(" · ")}
          </summary>
          <div className="mt-1.5 grid gap-2 sm:grid-cols-2">
            {lists.map(([label, items]) => (
              <div key={label}>
                <p className="font-medium">{label}</p>
                <ul className="mt-0.5 space-y-0.5 text-muted-foreground">
                  {items.map((item) => (
                    <li key={item} className="flex gap-1.5">
                      <span aria-hidden>•</span>
                      <span className="min-w-0 break-words" data-user-text>
                        {item}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </details>
      ) : null}
      {said ? (
        <p className="flex flex-wrap items-center gap-1.5">
          <Badge tone={mood.tone}>{mood.label}</Badge>
          <span className="text-muted-foreground" data-user-text>
            &ldquo;{said.words}&rdquo;
          </span>
        </p>
      ) : null}
    </div>
  );
}
