"use client";

import { useState } from "react";
import { BrainCircuit } from "lucide-react";
import { relativeTime } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Badge, Card, CardBody } from "@/components/ui/display";
import { Input } from "@/components/ui/input";
import { ConfirmDialog } from "@/components/app/forms";
import { EmptyState, ErrorState } from "@/components/app/states";
import { errorMessage } from "@/services/api-client";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import {
  brainSolutionsService,
  IDEA_STATUSES,
  isRollbackable,
  rejectReasonOk,
  type CatalogueProposal,
  type SolutionIdea,
  type SolutionVersion,
} from "../brain-solutions-service";

const KEY = ["pi", "solutions"];

function Pending() {
  return <div className="h-40 animate-pulse rounded-xl bg-surface-sunken" />;
}

function statusTone(status: string) {
  if (status === "live" || status === "active") return "success" as const;
  if (status === "shadow" || status === "testing") return "info" as const;
  if (status === "review") return "warning" as const;
  if (status === "rolled_back") return "danger" as const;
  return "neutral" as const;
}

function label(value: string) {
  return value.replaceAll("_", " ");
}

function evidenceText(evidence: Record<string, unknown>) {
  const parts = Object.entries(evidence).map(
    ([k, v]) =>
      `${label(k)}: ${typeof v === "object" ? JSON.stringify(v) : String(v)}`,
  );
  return parts.length ? parts.join(" · ") : "No evidence recorded";
}

export function SolutionsTab() {
  const [selected, setSelected] = useState<string | null>(null);
  return (
    <div className="space-y-6">
      <ReviewQueue />
      <Industries selected={selected} onSelect={setSelected} />
      {selected && (
        <>
          <IndustryDetail industry={selected} />
          <Ideas industry={selected} />
        </>
      )}
    </div>
  );
}

function Industries({
  selected,
  onSelect,
}: {
  selected: string | null;
  onSelect: (industry: string) => void;
}) {
  const overview = useScopedQuery([...KEY, "overview"], () =>
    brainSolutionsService.overview(),
  );
  return (
    <section className="space-y-2">
      <h2 className="text-[13px] font-semibold">
        Industries that have learned
      </h2>
      {overview.isError ? (
        <ErrorState
          error={overview.error}
          onRetry={() => void overview.refetch()}
        />
      ) : overview.isPending ? (
        <Pending />
      ) : overview.data.industries.length === 0 ? (
        <EmptyState
          icon={BrainCircuit}
          title="Nothing learned yet"
          description="When pi learns a better solution for an industry it appears here as a new version. Every industry starts at version 1.0 and nothing changes until learning makes a change."
        />
      ) : (
        <ul className="space-y-1.5">
          {overview.data.industries.map((i) => (
            <li key={i.industry}>
              <button
                type="button"
                aria-pressed={selected === i.industry}
                onClick={() => onSelect(i.industry)}
                className={
                  "flex w-full flex-wrap items-center gap-2 rounded-lg px-3 py-2 text-left text-[13px] " +
                  (selected === i.industry
                    ? "bg-surface-sunken ring-1 ring-border"
                    : "bg-surface-muted hover:bg-surface-sunken")
                }
              >
                <span className="font-medium">{label(i.industry)}</span>
                <Badge tone="neutral">@{i.latest.version}</Badge>
                <Badge tone={statusTone(i.latest.status)}>
                  {label(i.latest.status)}
                </Badge>
                <span className="ml-auto text-xs text-muted-foreground">
                  {i.versions} {i.versions === 1 ? "version" : "versions"}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function IndustryDetail({ industry }: { industry: string }) {
  const detail = useScopedQuery([...KEY, "detail", industry], () =>
    brainSolutionsService.detail(industry),
  );
  const [confirming, setConfirming] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const rollback = useScopedMutation(
    () => brainSolutionsService.rollback(industry),
    {
      invalidate: [KEY],
      success: (r) => `Rolled back @${r.rolled_back}`,
      toastErrors: false,
      onSuccess: () => {
        setFailure(null);
        setConfirming(false);
      },
    },
  );
  if (detail.isError)
    return (
      <ErrorState error={detail.error} onRetry={() => void detail.refetch()} />
    );
  if (detail.isPending) return <Pending />;
  const d = detail.data;
  const canRollBack = d.versions.some(isRollbackable);
  return (
    <section className="space-y-3">
      <h2 className="text-[13px] font-semibold">{label(industry)}</h2>
      <Card>
        <CardBody className="space-y-2">
          <p className="text-xs font-medium text-muted-foreground">
            Sample reply in force
          </p>
          {d.sample_reply ? (
            <>
              <p className="text-[13px]">
                <span className="text-muted-foreground">Customer:</span>{" "}
                {d.sample_reply.person}
              </p>
              <p className="text-[13px]">
                <span className="text-muted-foreground">pi:</span>{" "}
                {d.sample_reply.pi}
              </p>
            </>
          ) : (
            <p className="text-[13px] text-muted-foreground">
              No sample reply for this industry.
            </p>
          )}
        </CardBody>
      </Card>
      <div className="flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          variant="secondary"
          disabled={!canRollBack}
          onClick={() => {
            setFailure(null);
            setConfirming(true);
          }}
        >
          Roll back latest learned version
        </Button>
        {!canRollBack && (
          <span className="text-xs text-muted-foreground">
            Nothing to roll back: this industry is on its starting version.
          </span>
        )}
      </div>
      <ConfirmDialog
        open={confirming}
        onOpenChange={(open) => {
          setConfirming(open);
          if (!open) setFailure(null);
        }}
        title="Roll back the latest learned version?"
        description={
          <>
            This undoes the latest learned version of{" "}
            <strong>{label(industry)}</strong> only.
          </>
        }
        consequences={[
          "Only this industry is affected. Other industries keep what they have learned.",
          "The starting version @1.0 never rolls back.",
          ...(failure ? [failure] : []),
        ]}
        confirmLabel="Roll back"
        destructive
        loading={rollback.isPending}
        onConfirm={() =>
          rollback.mutate(undefined, {
            onError: (e) =>
              setFailure(
                errorMessage(e, "That didn't work. Please try again."),
              ),
          })
        }
      />
      <ul className="space-y-2">
        {d.versions.map((v) => (
          <VersionRow key={v.version} version={v} />
        ))}
      </ul>
    </section>
  );
}

function VersionRow({ version: v }: { version: SolutionVersion }) {
  return (
    <li>
      <Card>
        <CardBody className="space-y-1.5">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-[13px] font-semibold">@{v.version}</span>
            <Badge tone={statusTone(v.status)}>{label(v.status)}</Badge>
            {v.created_at && (
              <span className="text-xs text-muted-foreground">
                {relativeTime(v.created_at)}
              </span>
            )}
            {v.rolled_back_at && (
              <span className="text-xs text-muted-foreground">
                rolled back {relativeTime(v.rolled_back_at)}
              </span>
            )}
          </div>
          <p className="text-[13px]">
            <span className="text-muted-foreground">Changed:</span>{" "}
            {v.changes.length ? v.changes.map(label).join(", ") : "nothing"}
          </p>
          <p className="text-xs text-muted-foreground">
            Evidence: {evidenceText(v.evidence)}
          </p>
        </CardBody>
      </Card>
    </li>
  );
}

function ReviewQueue() {
  const review = useScopedQuery([...KEY, "review"], () =>
    brainSolutionsService.review(),
  );
  return (
    <section className="space-y-2">
      <h2 className="text-[13px] font-semibold">Waiting for a person</h2>
      {review.isError ? (
        <ErrorState
          error={review.error}
          onRetry={() => void review.refetch()}
        />
      ) : review.isPending ? (
        <Pending />
      ) : review.data.ideas.length === 0 &&
        review.data.proposals.length === 0 ? (
        <EmptyState
          icon={BrainCircuit}
          title="Nothing to review"
          description="Ideas that touch money or a regulated topic, and gaps in the catalogue, wait here for you."
        />
      ) : (
        <>
          <ul className="space-y-2">
            {review.data.ideas.map((i) => (
              <ReviewIdea key={i.id} idea={i} />
            ))}
          </ul>
          {review.data.proposals.length > 0 && (
            <>
              <h3 className="pt-2 text-xs font-semibold text-muted-foreground">
                Catalogue proposals
              </h3>
              <ul className="space-y-2">
                {review.data.proposals.map((p) => (
                  <ReviewProposal key={p.id} proposal={p} />
                ))}
              </ul>
            </>
          )}
        </>
      )}
    </section>
  );
}

function DecisionButtons({
  pending,
  onDecide,
  subject,
}: {
  pending: boolean;
  onDecide: (approve: boolean, reason: string) => void;
  subject: string;
}) {
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <Button
          size="sm"
          loading={pending}
          onClick={() => onDecide(true, "")}
          aria-label={`Approve ${subject}`}
        >
          Approve
        </Button>
        {!rejecting && (
          <Button
            size="sm"
            variant="secondary"
            onClick={() => setRejecting(true)}
            aria-label={`Reject ${subject}`}
          >
            Reject
          </Button>
        )}
      </div>
      {rejecting && (
        <div className="flex flex-col gap-2 sm:flex-row">
          <Input
            aria-label={`Reason for rejecting ${subject}`}
            value={reason}
            maxLength={200}
            placeholder="A short reason, no personal details"
            onChange={(e) => setReason(e.target.value)}
          />
          <Button
            size="sm"
            variant="secondary"
            loading={pending}
            disabled={!rejectReasonOk(reason)}
            onClick={() => onDecide(false, reason.trim())}
          >
            Confirm reject
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              setRejecting(false);
              setReason("");
            }}
          >
            Cancel
          </Button>
        </div>
      )}
    </div>
  );
}

function ReviewIdea({ idea: i }: { idea: SolutionIdea }) {
  const decide = useScopedMutation(
    (v: { approve: boolean; reason: string }) =>
      brainSolutionsService.decideIdea(i.id, v.approve, v.reason),
    { invalidate: [KEY], success: "Saved" },
  );
  return (
    <li>
      <Card>
        <CardBody className="space-y-2">
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge tone="neutral">{label(i.industry)}</Badge>
            <Badge tone="neutral">{i.language}</Badge>
            {i.kind && <Badge tone="info">{label(i.kind)}</Badge>}
            {i.source && (
              <span className="text-xs text-muted-foreground">
                source: {label(i.source)}
              </span>
            )}
          </div>
          <p className="text-xs text-muted-foreground">
            Problem: {label(i.problem)}
          </p>
          <p className="text-[13px]">{i.text}</p>
          <DecisionButtons
            pending={decide.isPending}
            subject="this idea"
            onDecide={(approve, reason) => decide.mutate({ approve, reason })}
          />
        </CardBody>
      </Card>
    </li>
  );
}

function ReviewProposal({ proposal: p }: { proposal: CatalogueProposal }) {
  const decide = useScopedMutation(
    (v: { approve: boolean; reason: string }) =>
      brainSolutionsService.decideProposal(p.id, v.approve, v.reason),
    { invalidate: [KEY], success: "Saved" },
  );
  return (
    <li>
      <Card>
        <CardBody className="space-y-2">
          <p className="text-[13px]">{p.need}</p>
          <p className="text-xs text-muted-foreground">
            {p.industries.map(label).join(", ") || "No industry"} · seen{" "}
            {p.count}×
          </p>
          <DecisionButtons
            pending={decide.isPending}
            subject="this proposal"
            onDecide={(approve, reason) => decide.mutate({ approve, reason })}
          />
        </CardBody>
      </Card>
    </li>
  );
}

function Ideas({ industry }: { industry: string }) {
  const [status, setStatus] = useState("");
  const arms = useScopedQuery([...KEY, "arms", industry, status], () =>
    brainSolutionsService.arms(industry, status || undefined),
  );
  return (
    <section className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-[13px] font-semibold">
          Ideas for {label(industry)}
        </h2>
        <select
          aria-label="Filter ideas by status"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="h-9 rounded-md border border-border bg-surface px-2 text-[13px]"
        >
          <option value="">All statuses</option>
          {IDEA_STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>
      {arms.isError ? (
        <ErrorState error={arms.error} onRetry={() => void arms.refetch()} />
      ) : arms.isPending ? (
        <Pending />
      ) : arms.data.items.length === 0 ? (
        <EmptyState
          icon={BrainCircuit}
          title="No ideas"
          description="No ideas match this filter for this industry."
        />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-left text-[13px]">
            <caption className="sr-only">Ideas for {label(industry)}</caption>
            <thead className="bg-surface-muted text-xs text-muted-foreground">
              <tr>
                <th className="px-3 py-2 font-medium">Idea</th>
                <th className="px-3 py-2 font-medium">Status</th>
                <th className="px-3 py-2 font-medium">Uses</th>
                <th className="px-3 py-2 font-medium">Feedback</th>
                <th className="px-3 py-2 font-medium">Source</th>
                <th className="px-3 py-2 font-medium">Retired because</th>
              </tr>
            </thead>
            <tbody>
              {arms.data.items.map((a) => (
                <tr key={a.id} className="border-t border-border align-top">
                  <td className="px-3 py-2">
                    {a.text}
                    <div className="text-xs text-muted-foreground">
                      {label(a.problem)} · {a.language}
                    </div>
                  </td>
                  <td className="px-3 py-2">
                    <Badge tone={statusTone(a.status)}>{a.status}</Badge>
                  </td>
                  <td className="px-3 py-2">{a.uses}</td>
                  <td className="px-3 py-2">{a.feedback}</td>
                  <td className="px-3 py-2">{label(a.source)}</td>
                  <td className="px-3 py-2 text-muted-foreground">
                    {a.retired_reason || "–"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
