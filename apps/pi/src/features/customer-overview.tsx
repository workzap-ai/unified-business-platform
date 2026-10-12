"use client";

/**
 * The team's picture of one customer: who they are (what they told pi), their projects
 * with the journey, and their requests on the Problem Map. One call:
 * GET /customers/{id}/pi-overview (read-only, no AI call).
 */

import { useQuery } from "@tanstack/react-query";
import { Building2, FolderKanban, Network } from "lucide-react";
import Link from "next/link";

import {
  Badge,
  Card,
  CardSection,
  ErrorState,
  LoadingBlock,
} from "@/components/ui";
import { PriorityChart, ProblemMap } from "@/features/customer/visuals";
import { errorText, get } from "@/lib/api";
import type { CustomerIssue, IssueLink } from "@/lib/customer-api";
import { date } from "@/lib/format";
import { useBusinessKey, useCan } from "@/lib/session";

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
};

type Overview = {
  profile: {
    name?: string;
    business_name?: string;
    business_type?: string;
    location?: string;
    role?: string;
    language: string | null;
    first_chat_at: string | null;
    last_message_at: string | null;
    chats: number;
    returning: boolean;
  };
  projects: Project[];
  issues: CustomerIssue[];
  links: IssueLink[];
  headline: string;
  counts: {
    waiting_on_them: number;
    waiting_on_us: number;
    done: number;
    paused: number;
  };
};

const LANGUAGE: Record<string, string> = {
  en: "English",
  roman_ur: "Roman Urdu",
  ar: "Arabic",
};

const STAGE: Record<string, string> = {
  new: "New",
  qualified: "Brief confirmed",
  proposal: "Proposal",
  won: "Won",
  lost: "Lost",
};

function Row({ label, value }: { label: string; value?: string | null }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-border py-2 text-sm last:border-0">
      <span className="text-muted-foreground">{label}</span>
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
  });
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
  const open = o.issues.filter((i) => !["live", "closed"].includes(i.stage));
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
              <h2 className="font-semibold">Business</h2>
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
              <h2 className="font-semibold">Projects</h2>
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
                      className="rounded-lg border border-border p-3"
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
                        <Badge>{STAGE[d.stage] ?? d.stage}</Badge>
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
                    </li>
                  );
                })}
              </ul>
            )}
          </CardSection>
        </Card>
      </div>

      <Card>
        <CardSection className="space-y-3">
          <div className="flex items-center gap-2">
            <Network className="size-5 text-accent" aria-hidden />
            <h2 className="font-semibold">Problem Map</h2>
            {o.links.length ? (
              <Badge tone="info" className="ms-auto">
                {o.links.length} connection{o.links.length === 1 ? "" : "s"}
              </Badge>
            ) : null}
          </div>
          {o.headline ? (
            <p className="text-sm text-muted-foreground" data-user-text>
              {o.headline}
            </p>
          ) : null}
          {o.issues.length ? (
            <ProblemMap issues={o.issues} links={o.links} lang="en" />
          ) : (
            <p className="text-sm text-muted-foreground">
              Nothing yet. pi maps this customer&apos;s requests and how they
              connect as they talk.
            </p>
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
