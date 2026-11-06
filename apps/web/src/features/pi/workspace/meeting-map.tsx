"use client";

import { useMemo, useState } from "react";
import { Network } from "lucide-react";
import { Badge, Card, CardBody } from "@/components/ui/display";
import { EmptyState } from "@/components/app/states";
import { cn } from "@/lib/utils";
import {
  BASIS_LABELS,
  clock,
  INSIGHT_LABELS,
  type Insight,
  type InsightKind,
  type MeetingDetail,
} from "../meeting-intel-service";

/**
 * The requirement map of a meeting: what is wrong, what it costs, what is needed, what was decided
 * and what is still open, as five lanes. Two findings are connected when they come from the same
 * part of the conversation (their source lines are the same or within two lines of each other), so
 * choosing one lights up what belongs with it. It only arranges what pi found; nothing here is
 * written to the customer's memory (that happens when a finding is approved on the Review tab).
 */

const LANES: {
  key: string;
  title: string;
  hint: string;
  kinds: InsightKind[];
}[] = [
  {
    key: "wrong",
    title: "What is wrong",
    hint: "Problems and their causes",
    kinds: ["problem", "root_cause"],
  },
  {
    key: "cost",
    title: "What it costs",
    hint: "Impact and risks",
    kinds: ["impact", "risk"],
  },
  {
    key: "need",
    title: "What is needed",
    hint: "Asked for, and likely needs",
    kinds: ["requirement_explicit", "requirement_implicit"],
  },
  {
    key: "next",
    title: "Decided and next",
    hint: "Decisions, promises and steps",
    kinds: ["decision", "commitment", "action", "next_step"],
  },
  {
    key: "open",
    title: "Still open",
    hint: "Questions nobody answered",
    kinds: ["question"],
  },
];

/** The same part of the conversation: a shared source line, or lines at most two apart. */
function related(a: Insight, b: Insight): boolean {
  if (a.id === b.id) return false;
  return a.segment_refs.some((x) =>
    b.segment_refs.some((y) => Math.abs(x - y) <= 2),
  );
}

export function MeetingMap({ meeting }: { meeting: MeetingDetail }) {
  const [selected, setSelected] = useState<string | null>(null);
  const live = meeting.status === "transcribing";
  const shown = useMemo(
    () => meeting.insights.filter((i) => i.review_status !== "rejected"),
    [meeting.insights],
  );
  const summaries = shown.filter((i) => i.kind === "summary");
  const chosen = shown.find((i) => i.id === selected) ?? null;
  const connected = useMemo(
    () =>
      new Set(
        chosen ? shown.filter((i) => related(chosen, i)).map((i) => i.id) : [],
      ),
    [chosen, shown],
  );
  const heardAt = useMemo(() => {
    const start = new Map(meeting.segments.map((s) => [s.ordinal, s.start_ms]));
    return (i: Insight) => {
      const first = [...i.segment_refs].sort((a, b) => a - b)[0];
      return first === undefined ? "" : clock(start.get(first) ?? 0);
    };
  }, [meeting.segments]);

  const mapped = shown.filter((i) => i.kind !== "summary");
  if (mapped.length === 0 && summaries.length === 0) {
    return (
      <EmptyState
        icon={Network}
        title="The map is empty"
        description={
          live
            ? "It fills in as pi hears the meeting, a few minutes behind the conversation."
            : "Choose “Analyse with pi” and the problems, needs and next steps appear here."
        }
      />
    );
  }

  return (
    <div className="space-y-4">
      {summaries.length > 0 && (
        <Card>
          <CardBody className="space-y-1.5">
            <h2 className="text-sm font-semibold">Summary</h2>
            {summaries.map((s) => (
              <p key={s.id} className="text-[13px] leading-relaxed">
                {s.text}
              </p>
            ))}
            <p className="text-xs text-muted-foreground">
              Written by pi from the transcript. It is a summary, not a quote.
            </p>
          </CardBody>
        </Card>
      )}

      <p className="text-xs text-muted-foreground">
        {chosen
          ? `${connected.size} connected finding${connected.size === 1 ? "" : "s"} from the same part of the conversation. Choose it again to clear.`
          : "Choose a finding to see what it connects to."}
      </p>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        {LANES.map((lane) => {
          const items = mapped.filter((i) => lane.kinds.includes(i.kind));
          return (
            <section
              key={lane.key}
              aria-label={lane.title}
              className="rounded-xl border border-border bg-surface-muted p-2.5"
            >
              <header className="mb-2 px-1">
                <h3 className="text-xs font-semibold">
                  {lane.title}{" "}
                  <span className="font-normal text-muted-foreground">
                    {items.length}
                  </span>
                </h3>
                <p className="text-[11px] text-muted-foreground">{lane.hint}</p>
              </header>
              <ul className="space-y-2">
                {items.length === 0 && (
                  <li className="px-1 py-2 text-xs text-muted-foreground">
                    Nothing yet
                  </li>
                )}
                {items.map((i) => {
                  const isChosen = i.id === selected;
                  const isLinked = connected.has(i.id);
                  const dimmed = chosen !== null && !isChosen && !isLinked;
                  return (
                    <li key={i.id}>
                      <button
                        type="button"
                        aria-pressed={isChosen}
                        onClick={() => setSelected(isChosen ? null : i.id)}
                        className={cn(
                          "w-full rounded-lg border bg-surface p-2.5 text-left text-[13px] leading-snug shadow-sm transition-opacity",
                          isChosen
                            ? "border-primary ring-2 ring-primary/40"
                            : isLinked
                              ? "border-primary/60 ring-1 ring-primary/30"
                              : "border-border hover:border-border-strong",
                          dimmed && "opacity-45",
                        )}
                      >
                        <span className="mb-1 flex flex-wrap items-center gap-1.5">
                          <Badge tone="neutral">{INSIGHT_LABELS[i.kind]}</Badge>
                          <span className="text-[11px] text-muted-foreground">
                            {BASIS_LABELS[i.basis]}
                          </span>
                          {i.review_status === "approved" && (
                            <Badge tone="success">Approved</Badge>
                          )}
                        </span>
                        <span className="block break-words">{i.text}</span>
                        {heardAt(i) && (
                          <span className="mt-1 block text-[11px] text-muted-foreground">
                            Heard at {heardAt(i)}
                          </span>
                        )}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </section>
          );
        })}
      </div>
    </div>
  );
}
