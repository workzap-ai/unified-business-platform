"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowLeft, ShieldCheck } from "lucide-react";
import { formatDateTime, humanize, relativeTime } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Badge, Card, CardBody } from "@/components/ui/display";
import { Textarea } from "@/components/ui/input";
import {
  PageHeader,
  PageShell,
  RequirePermission,
  SectionHeader,
} from "@/components/app/page";
import { EmptyState, ErrorState } from "@/components/app/states";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useUrlState } from "@/hooks/use-url-state";
import { useSession } from "@/features/auth/session-provider";
import {
  piReviewService,
  type AlertLevel,
  type ConversationReview,
  type ReviewAlert,
} from "../review-service";
import { inboxHref } from "./lib";

const LEVEL_TONE: Record<
  AlertLevel,
  "danger" | "warning" | "info" | "neutral"
> = { red: "danger", amber: "warning", yellow: "warning", blue: "info" };

const STATUS_TONE: Record<
  string,
  "success" | "info" | "neutral" | "warning" | "primary"
> = {
  open: "neutral",
  confirmed: "success",
  in_box: "primary",
  parked: "neutral",
  resolved: "success",
  stale: "warning",
};

function Pending() {
  return <div className="h-40 animate-pulse rounded-xl bg-surface-sunken" />;
}

export function ReviewPage() {
  return (
    <RequirePermission permission="pi.handoffs.manage" area="pi">
      <ReviewView />
    </RequirePermission>
  );
}

function ReviewView() {
  const [url, setUrl] = useUrlState({ c: "" });
  return (
    <PageShell>
      <PageHeader
        title="Conversation review"
        description="What pi understood, how it read the owner, and why it handed over. Read-only: the map and the dials are the briefing when a person takes over."
        actions={
          url.c ? (
            <Button variant="outline" onClick={() => setUrl({ c: "" })}>
              <ArrowLeft className="size-4" aria-hidden="true" /> Needs
              attention
            </Button>
          ) : null
        }
      />
      {url.c ? (
        <Detail id={url.c} />
      ) : (
        <Attention onOpen={(c) => setUrl({ c })} />
      )}
    </PageShell>
  );
}

function AlertBadges({ alerts }: { alerts: ReviewAlert[] }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {alerts.map((a) => (
        <Badge key={a.key} tone={LEVEL_TONE[a.level]} title={a.detail}>
          {a.label}
        </Badge>
      ))}
    </div>
  );
}

function Attention({ onOpen }: { onOpen: (id: string) => void }) {
  const query = useScopedQuery(["pi", "review", "attention"], () =>
    piReviewService.attention(),
  );
  if (query.isError)
    return (
      <ErrorState error={query.error} onRetry={() => void query.refetch()} />
    );
  if (query.isPending) return <Pending />;
  const items = query.data.items;
  if (items.length === 0)
    return (
      <EmptyState
        icon={ShieldCheck}
        title="Nothing needs attention"
        description="Conversations with a churn risk, an unanswered request, frustration or an open handoff appear here, most urgent first."
      />
    );
  return (
    <ul className="space-y-3">
      {items.map((i) => (
        <li key={i.conversation_id}>
          <Card>
            <CardBody className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0 space-y-1.5">
                <AlertBadges alerts={i.alerts} />
                <p className="text-xs text-muted-foreground">
                  Owner {i.customer_ref} · {i.phone}
                  {i.language ? ` · ${i.language}` : ""} ·{" "}
                  {i.mode === "human" ? "with a person" : "pi is replying"} ·{" "}
                  <span title={formatDateTime(i.last_message_at)}>
                    {relativeTime(i.last_message_at)}
                  </span>
                </p>
              </div>
              <Button
                variant="outline"
                onClick={() => onOpen(i.conversation_id)}
              >
                Review
              </Button>
            </CardBody>
          </Card>
        </li>
      ))}
    </ul>
  );
}

function Panel({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mb-6">
      <SectionHeader title={title} />
      <Card>
        <CardBody className="space-y-3 text-[13px]">{children}</CardBody>
      </Card>
    </section>
  );
}

function Detail({ id }: { id: string }) {
  const query = useScopedQuery(["pi", "review", id], () =>
    piReviewService.review(id),
  );
  if (query.isError)
    return (
      <ErrorState error={query.error} onRetry={() => void query.refetch()} />
    );
  if (query.isPending) return <Pending />;
  return <Body data={query.data} />;
}

function Body({ data: d }: { data: ConversationReview }) {
  const c = d.conversation;
  return (
    <div>
      <div className="mb-5 flex flex-wrap items-center gap-2 text-[13px]">
        <span className="font-medium">
          Owner {c.customer_ref} · {c.phone}
        </span>
        <Badge tone={c.mode === "human" ? "warning" : "pi"}>
          {c.mode === "human" ? "With a person" : "pi is replying"}
        </Badge>
        {c.flow_state && <Badge>{humanize(c.flow_state)}</Badge>}
        <Link
          href={inboxHref(c.id)}
          className="text-primary underline-offset-2 hover:underline"
        >
          Open in inbox
        </Link>
      </div>
      {d.labels.alerts.length > 0 && (
        <div className="mb-5">
          <AlertBadges alerts={d.labels.alerts} />
        </div>
      )}
      <MapPanel d={d} />
      <ThinkingPanel d={d} />
      <DiagnosisPanel d={d} />
      <HandoverPanel d={d} />
      <BoxPanel d={d} />
      <LabelsPanel d={d} />
      <NotesPanel id={c.id} />
    </div>
  );
}

function MapPanel({ d }: { d: ConversationReview }) {
  const m = d.map;
  const title = new Map(m.nodes.map((n) => [n.id, n.title]));
  return (
    <Panel title="Problem map">
      <p className="text-muted-foreground">
        {m.version === null
          ? "No map yet."
          : `Version ${m.version}. ${
              m.shared_at
                ? `Last shared with the owner as version ${m.shared_version}, ${relativeTime(m.shared_at)}${
                    m.up_to_date_with_owner ? "" : " (changed since)"
                  }.`
                : "Not shared with the owner yet."
            }`}
      </p>
      {m.nodes.length > 0 && (
        <ul className="space-y-2">
          {m.nodes.map((n) => (
            <li
              key={n.id}
              className="flex flex-wrap items-center gap-1.5 rounded-lg bg-surface-muted px-3 py-2"
            >
              <span className="font-semibold">{n.id}</span>
              <span className="min-w-0 break-words">{n.title}</span>
              <Badge tone={STATUS_TONE[n.status]}>{humanize(n.status)}</Badge>
              {n.rank !== null && <Badge tone="primary">Rank {n.rank}</Badge>}
              <Badge>{n.category_label || n.category}</Badge>
              {n.subtype && <Badge tone="outline">{humanize(n.subtype)}</Badge>}
              {n.goal_verb && <Badge tone="outline">{n.goal_verb}</Badge>}
              {n.raised_voluntarily && (
                <Badge tone="info">Raised by the owner</Badge>
              )}
            </li>
          ))}
        </ul>
      )}
      {m.links.length > 0 && (
        <div>
          <p className="mb-1 text-2xs font-semibold tracking-wide text-muted-foreground uppercase">
            Links
          </p>
          <ul className="space-y-1">
            {m.links.map((l) => (
              <li key={`${l.from}-${l.to}-${l.type}`}>
                {l.from} {humanize(l.type)} {l.to}{" "}
                <Badge
                  tone={l.evidence === "pi_inferred" ? "warning" : "success"}
                >
                  {l.evidence === "owner_said"
                    ? "Owner said"
                    : l.evidence === "confirmed"
                      ? "Confirmed"
                      : "pi inferred"}
                </Badge>
                <span className="sr-only">
                  {title.get(l.from)} to {title.get(l.to)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Panel>
  );
}

function ThinkingPanel({ d }: { d: ConversationReview }) {
  const t = d.thinking;
  return (
    <Panel title="Dials, moves and hypotheses">
      <div className="flex flex-wrap gap-1.5">
        <Badge tone="pi">Openness {t.dials.openness}</Badge>
        <Badge tone="pi">Pace {t.dials.pace}</Badge>
        <Badge tone="pi">Mode {t.dials.mode}</Badge>
        <Badge tone="pi">Trust {t.dials.trust_trend}</Badge>
        {t.dials.fatigue && <Badge tone="warning">Fatigue</Badge>}
        <Badge tone="outline">Posture: {t.posture}</Badge>
      </div>
      <p className="text-xs text-muted-foreground">
        Read again now from the owner&apos;s last {t.messages_read} messages;
        nothing is stored.
      </p>
      {t.moves.length > 0 && (
        <ul className="space-y-1">
          {t.moves.map((m, i) => (
            <li key={`${m.at}-${i}`}>
              <span className="font-medium">{humanize(m.move)}</span>
              {m.reason ? ` · ${m.reason}` : ""}{" "}
              <span className="text-muted-foreground">
                {relativeTime(m.at)}
                {m.had_question ? " · asked a question" : ""}
              </span>
            </li>
          ))}
        </ul>
      )}
      {t.hypotheses.length > 0 && (
        <ul className="space-y-1">
          {t.hypotheses.map((h) => (
            <li key={h.text}>
              {h.text}{" "}
              <Badge tone={h.confirmed_by_owner ? "success" : "neutral"}>
                {h.confirmed_by_owner
                  ? "Owner confirmed"
                  : `Open, ${h.confidence}`}
              </Badge>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

function DiagnosisPanel({ d }: { d: ConversationReview }) {
  const x = d.diagnosis;
  const i = d.ideas;
  return (
    <Panel title="Diagnosis and idea budget">
      {x ? (
        <div className="space-y-1">
          <p>
            <span className="font-medium">Main problem:</span> {x.main_problem}
          </p>
          {x.likely_causes.length > 0 && (
            <p>
              <span className="font-medium">Likely causes:</span>{" "}
              {x.likely_causes.join("; ")}
            </p>
          )}
          {x.suggested_next_question && (
            <p>
              <span className="font-medium">Suggested next question:</span>{" "}
              {x.suggested_next_question}
            </p>
          )}
        </div>
      ) : (
        <p className="text-muted-foreground">No diagnosis cached yet.</p>
      )}
      <p>
        Ideas given: {i.given_in_chat} in this chat, {i.given_for_business} for
        the business (up to {i.per_problem_cap} per problem and{" "}
        {i.per_business_cap} per business, {i.business_remaining} left).
      </p>
      {Object.keys(i.rounds_by_problem).length > 0 && (
        <ul className="text-muted-foreground">
          {Object.entries(i.rounds_by_problem).map(([k, v]) => (
            <li key={k}>
              {k}: {v} time{v === 1 ? "" : "s"}
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

function HandoverPanel({ d }: { d: ConversationReview }) {
  const h = d.handover;
  return (
    <Panel title="Why pi handed over">
      {h.handoff ? (
        <div className="space-y-1">
          <p>
            <Badge tone="warning">{humanize(h.handoff.status)}</Badge>{" "}
            <span className="font-medium">{h.handoff.origin_text}</span>{" "}
            <span className="text-muted-foreground">
              ({humanize(h.handoff.reason)},{" "}
              {relativeTime(h.handoff.created_at)})
            </span>
          </p>
          {h.handoff.summary && <p>{h.handoff.summary}</p>}
          {h.handoff.assigned_label && (
            <p className="text-muted-foreground">
              Assigned to {h.handoff.assigned_label}
            </p>
          )}
        </div>
      ) : (
        <p className="text-muted-foreground">
          pi has not handed this chat over.
        </p>
      )}
      {h.requests.map((r) => (
        <div key={r.id} className="rounded-lg bg-surface-muted px-3 py-2">
          <p>
            <span className="font-medium">{humanize(r.kind)}</span>{" "}
            <Badge tone={r.status === "open" ? "warning" : "neutral"}>
              {humanize(r.status)}
            </Badge>
          </p>
          <p>{r.question}</p>
        </div>
      ))}
    </Panel>
  );
}

function BoxPanel({ d }: { d: ConversationReview }) {
  const b = d.box;
  return (
    <Panel title="Solution Box and offers">
      {b.box ? (
        <p>
          <Badge tone="primary">{humanize(b.box.state)}</Badge> version{" "}
          {b.box.version}
          {b.box.reviewer
            ? ` · reviewer ${b.box.reviewer}`
            : " · no reviewer yet"}
          {b.box.owner_ranking.length > 0
            ? ` · owner ranking ${b.box.owner_ranking.map(String).join(", ")}`
            : ""}
        </p>
      ) : (
        <p className="text-muted-foreground">No Solution Box yet.</p>
      )}
      {b.offers.length > 0 && (
        <ul className="space-y-1">
          {b.offers.map((o, i) => (
            <li key={`${o.at}-${i}`}>
              <Badge tone={o.allowed ? "success" : "danger"}>
                {o.rule} {o.allowed ? "allowed" : "blocked"}
              </Badge>{" "}
              {o.blocked_reason ?? ""}{" "}
              <span className="text-muted-foreground">
                {relativeTime(o.at)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

function LabelsPanel({ d }: { d: ConversationReview }) {
  const l = d.labels;
  return (
    <Panel title="Labels">
      <div className="flex flex-wrap gap-1.5">
        {Object.entries(l.intents).map(([k, v]) => (
          <Badge key={k} tone="outline">
            {humanize(k)} × {v}
          </Badge>
        ))}
        {l.message_labels.map((m, i) => (
          <Badge key={`${m.at}-${i}`} tone="pi">
            PI · {m.label}
          </Badge>
        ))}
        {Object.keys(l.intents).length === 0 &&
          l.message_labels.length === 0 && (
            <span className="text-muted-foreground">Nothing labelled yet.</span>
          )}
      </div>
    </Panel>
  );
}

function NotesPanel({ id }: { id: string }) {
  const { can } = useSession();
  const [text, setText] = useState("");
  const allowed = can("pi.inbox.notes");
  const notes = useScopedQuery(
    ["pi", "notes", id],
    () => piReviewService.notes(id),
    {
      enabled: allowed,
    },
  );
  const add = useScopedMutation(
    () => piReviewService.addNote(id, text.trim()),
    {
      invalidate: [["pi", "notes", id]],
      success: "Note added",
      onSuccess: () => setText(""),
    },
  );
  if (!allowed) return null;
  return (
    <Panel title="Team notes">
      <ul className="space-y-1">
        {(notes.data ?? []).map((n) => (
          <li key={n.id}>
            {n.body}{" "}
            <span className="text-muted-foreground">
              {n.author ?? "Team"} · {relativeTime(n.created_at)}
            </span>
          </li>
        ))}
      </ul>
      <Textarea
        aria-label="Add a note"
        value={text}
        onChange={(e) => setText(e.target.value)}
        maxLength={4000}
      />
      <Button
        disabled={!text.trim() || add.isPending}
        onClick={() => add.mutate()}
      >
        Add note
      </Button>
    </Panel>
  );
}
