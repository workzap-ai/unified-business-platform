"use client";

import { useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  Check,
  Download,
  FileText,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Badge,
  Card,
  CardBody,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/display";
import { NativeSelect, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/controls";
import { PageHeader, PageShell } from "@/components/app/page";
import { EmptyState, ErrorState, Notice } from "@/components/app/states";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import { customersService } from "@/features/customers/service";
import {
  approvalEffect,
  BASIS_LABELS,
  clock,
  INSIGHT_LABELS,
  MEETING_STATUS_LABELS,
  meetingIntelService,
  type Insight,
  type MeetingDetail as Detail,
  type Segment,
} from "../meeting-intel-service";
import { MeetingRecorder } from "./meeting-recorder";
import {
  Accent,
  GroupHeading,
  ReviewProgress,
  SkeletonRows,
  SpeakerAvatar,
  statusTone,
} from "./meeting-intel-parts";

const KEY = (id: string) => ["pi", "meeting-intel", id];

export function MeetingDetail({
  id,
  onBack,
}: {
  id: string;
  onBack: () => void;
}) {
  const { can } = useSession();
  // while a recording is being transcribed, new lines and findings appear without a refresh
  const query = useScopedQuery(KEY(id), () => meetingIntelService.get(id), {
    refetchInterval: (q) =>
      q.state.data?.status === "transcribing" ? 15_000 : false,
  });
  const remove = useScopedMutation(() => meetingIntelService.remove(id), {
    invalidate: [["pi", "meeting-intel"]],
    success: "Meeting deleted",
    onSuccess: onBack,
  });
  const meeting = query.data;
  return (
    <PageShell>
      <PageHeader
        title={meeting?.title || "Meeting"}
        eyebrow={
          <button
            type="button"
            onClick={onBack}
            className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="size-3.5" aria-hidden="true" /> All meetings
          </button>
        }
        description={
          meeting && (
            <Badge tone={statusTone(meeting.status)}>
              {MEETING_STATUS_LABELS[meeting.status] ?? meeting.status}
            </Badge>
          )
        }
        actions={
          meeting && can("pi.meetings.delete") ? (
            <Button
              variant="secondary"
              loading={remove.isPending}
              onClick={() => {
                if (
                  window.confirm(
                    "Delete this meeting, its transcript and its insights? What you already saved to the customer's memory stays there.",
                  )
                )
                  remove.mutate(undefined);
              }}
            >
              <Trash2 /> Delete
            </Button>
          ) : null
        }
      />
      {query.isError ? (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      ) : !meeting ? (
        <SkeletonRows count={2} />
      ) : (
        <Body meeting={meeting} />
      )}
    </PageShell>
  );
}

const RECORDING_STATES = ["created", "uploaded", "transcribing"];

function Body({ meeting }: { meeting: Detail }) {
  const { can } = useSession();
  const hasTranscript = meeting.segments.length > 0;
  const canRecord = can("pi.meetings.record");
  const live = meeting.status === "transcribing";
  // The recorder stays on screen from the first word to the end of the meeting, so a recording in
  // progress is never torn down when the first lines of the transcript arrive.
  const recording =
    canRecord &&
    (RECORDING_STATES.includes(meeting.status) ||
      (meeting.status === "failed" && !hasTranscript));
  return (
    <div className="space-y-4">
      {meeting.customer_id === null && <LinkCustomer meeting={meeting} />}
      {meeting.status === "failed" && meeting.failure_reason && (
        <Notice tone="danger">{meeting.failure_reason}</Notice>
      )}
      {recording && <MeetingRecorder id={meeting.id} />}
      {!hasTranscript &&
        (canRecord ? (
          <TranscriptImport id={meeting.id} />
        ) : (
          <EmptyState
            icon={FileText}
            title="No transcript yet"
            description="Someone with permission to record meetings needs to add it."
          />
        ))}
      {hasTranscript && (
        <Tabs defaultValue="review">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <TabsList>
              <TabsTrigger value="review">
                Review
                {meeting.insights.some(
                  (i) => i.review_status === "pending",
                ) && (
                  <Badge tone="warning" className="ml-1.5">
                    {
                      meeting.insights.filter(
                        (i) => i.review_status === "pending",
                      ).length
                    }
                  </Badge>
                )}
              </TabsTrigger>
              <TabsTrigger value="transcript">Transcript</TabsTrigger>
            </TabsList>
            {/* the whole-meeting analysis waits until the recording is finished */}
            {canRecord && !live && <AnalyseButton meeting={meeting} />}
          </div>
          <TabsContent value="review" className="mt-4">
            <Insights meeting={meeting} />
          </TabsContent>
          <TabsContent value="transcript" className="mt-4">
            <Transcript
              key={`${meeting.id}-${meeting.segments_total}`}
              meeting={meeting}
            />
          </TabsContent>
        </Tabs>
      )}
    </div>
  );
}

function LinkCustomer({ meeting }: { meeting: Detail }) {
  const { can } = useSession();
  const [customer, setCustomer] = useState("");
  const customers = useScopedQuery(["customers", "meeting-picker"], () =>
    customersService.list({ pageSize: 100 }),
  );
  const link = useScopedMutation(
    () => meetingIntelService.linkCustomer(meeting.id, customer),
    {
      invalidate: [["pi", "meeting-intel"]],
      success: "Linked to the customer",
    },
  );
  return (
    <Card>
      <CardBody className="space-y-2">
        <p className="text-[13px]">
          This meeting is not linked to a customer yet, so nothing from it can
          be saved to anyone&apos;s memory.
        </p>
        {can("pi.meetings.record") && (
          <div className="flex flex-wrap items-end gap-2">
            <div className="min-w-48 flex-1 sm:max-w-xs">
              <Label htmlFor="link-customer">Customer</Label>
              <NativeSelect
                id="link-customer"
                value={customer}
                onChange={(e) => setCustomer(e.target.value)}
              >
                <option value="">Choose a customer</option>
                {(customers.data?.items ?? []).map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </NativeSelect>
            </div>
            <Button
              loading={link.isPending}
              disabled={!customer || link.isPending}
              onClick={() => link.mutate(undefined)}
            >
              Link
            </Button>
          </div>
        )}
      </CardBody>
    </Card>
  );
}

function TranscriptImport({ id }: { id: string }) {
  const [text, setText] = useState("");
  const send = useScopedMutation(
    () => meetingIntelService.importTranscript(id, text),
    {
      invalidate: [KEY(id), ["pi", "meeting-intel"]],
      success: (r) => `Transcript added: ${r.lines} lines`,
      onSuccess: () => setText(""),
    },
  );
  return (
    <Card>
      <CardBody className="space-y-3">
        <div>
          <Label htmlFor="transcript-text">
            Or paste a transcript you have
          </Label>
          <Textarea
            id="transcript-text"
            rows={12}
            maxLength={24000}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={
              "Customer: our stock keeps running out\nStaff: ok, we will send a list by Friday"
            }
          />
          <p className="mt-1 text-xs text-muted-foreground">
            One line per turn, written as &ldquo;Name: what they said&rdquo;. Up
            to 24,000 characters. Phone, card and ID numbers are removed before
            anything is stored.
          </p>
        </div>
        <Button
          loading={send.isPending}
          disabled={!text.trim() || send.isPending}
          onClick={() => send.mutate(undefined)}
        >
          Add transcript
        </Button>
      </CardBody>
    </Card>
  );
}

function AnalyseButton({ meeting }: { meeting: Detail }) {
  const run = useScopedMutation(() => meetingIntelService.analyse(meeting.id), {
    invalidate: [KEY(meeting.id), ["pi", "meeting-intel"]],
    success: (r) =>
      r.insights === 0
        ? "Analysed: nothing worth noting"
        : `Analysed: ${r.insights} to review`,
  });
  const again = meeting.insights.length > 0;
  return (
    <Button
      variant={again ? "secondary" : "default"}
      loading={run.isPending}
      onClick={() => run.mutate(undefined)}
    >
      <Sparkles /> {again ? "Analyse again" : "Analyse with pi"}
    </Button>
  );
}

function Insights({ meeting }: { meeting: Detail }) {
  if (meeting.insights.length === 0)
    return (
      <EmptyState
        icon={Sparkles}
        title="Nothing to review yet"
        description="Choose “Analyse with pi” to list the problems, decisions and next steps from this transcript. Analysing again replaces only what you have not reviewed."
      />
    );
  const bySegment = new Map(meeting.segments.map((s) => [s.ordinal, s]));
  const reviewed = meeting.insights.filter(
    (i) => i.review_status !== "pending",
  ).length;
  const groups = [
    {
      key: "said",
      title: "Said in the meeting",
      hint: "Quoted from the transcript, with its source lines.",
      tone: "success" as const,
      items: meeting.insights.filter((i) => i.basis === "stated"),
    },
    {
      key: "pi",
      title: "pi's conclusions",
      hint: "pi's own reading. Never saved as something the customer said.",
      tone: "pi" as const,
      items: meeting.insights.filter((i) => i.basis !== "stated"),
    },
  ].filter((g) => g.items.length > 0);
  return (
    <div className="space-y-5">
      <ReviewProgress done={reviewed} total={meeting.insights.length} />
      {groups.map((g) => (
        <section key={g.key} aria-label={g.title}>
          <GroupHeading title={g.title} hint={g.hint} count={g.items.length} />
          <ul className="space-y-3">
            {g.items.map((i) => (
              <li key={i.id}>
                <Accent tone={g.tone}>
                  <InsightCard
                    meeting={meeting}
                    insight={i}
                    sources={i.segment_refs.flatMap(
                      (r) => bySegment.get(r) ?? [],
                    )}
                  />
                </Accent>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

function InsightCard({
  meeting,
  insight: i,
  sources,
}: {
  meeting: Detail;
  insight: Insight;
  sources: Segment[];
}) {
  const { can } = useSession();
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(i.text);
  const invalidate = [KEY(meeting.id), ["pi", "meeting-intel"]];
  const approve = useScopedMutation(
    (edited: string) => meetingIntelService.approve(meeting.id, i.id, edited),
    {
      invalidate,
      success: (r) =>
        r.wrote ? "Approved and saved" : "Approved (reviewed only)",
      onSuccess: () => setEditing(false),
    },
  );
  const reject = useScopedMutation(
    () => meetingIntelService.reject(meeting.id, i.id),
    { invalidate, success: "Rejected" },
  );
  const pending = i.review_status === "pending";
  const needsLink = meeting.customer_id === null;
  return (
    <div>
      <Card>
        <CardBody className="space-y-2.5">
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge tone="outline">{INSIGHT_LABELS[i.kind]}</Badge>
            <Badge tone={i.basis === "stated" ? "success" : "pi"}>
              {BASIS_LABELS[i.basis]}
            </Badge>
            {i.confidence > 0 && (
              <span className="text-xs text-muted-foreground">
                {i.confidence}% sure
              </span>
            )}
            {!pending && (
              <Badge
                tone={i.review_status === "rejected" ? "neutral" : "success"}
              >
                {i.review_status === "rejected"
                  ? "Rejected"
                  : i.written_to_brain
                    ? "Saved to memory"
                    : "Reviewed"}
              </Badge>
            )}
          </div>
          {editing ? (
            <Textarea
              aria-label="Edit insight"
              rows={3}
              maxLength={600}
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
          ) : (
            <p className="text-[14px] leading-relaxed break-words">{i.text}</p>
          )}
          {(i.owner_label || i.due_text) && (
            <p className="text-xs text-muted-foreground">
              {i.owner_label && <>Who: {i.owner_label}. </>}
              {i.due_text && <>When: {i.due_text}.</>}
            </p>
          )}
          {sources.length > 0 && (
            <blockquote className="space-y-0.5 border-l-2 border-border pl-3 text-xs text-muted-foreground">
              {sources.map((s) => (
                <p key={s.ordinal} className="break-words">
                  <span className="font-medium">{s.speaker || "Speaker"}:</span>{" "}
                  {s.text}
                </p>
              ))}
            </blockquote>
          )}
          {pending && can("pi.meetings.approve") && (
            <>
              <p className="text-xs text-muted-foreground">
                {needsLink
                  ? "Link this meeting to a customer to approve."
                  : approvalEffect(i)}
              </p>
              <div className="flex flex-wrap gap-2">
                <Button
                  size="sm"
                  loading={approve.isPending}
                  disabled={needsLink || approve.isPending || !text.trim()}
                  onClick={() => approve.mutate(editing ? text.trim() : "")}
                >
                  <Check /> {editing ? "Save and approve" : "Approve"}
                </Button>
                {!editing ? (
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => setEditing(true)}
                  >
                    Edit
                  </Button>
                ) : (
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => {
                      setEditing(false);
                      setText(i.text);
                    }}
                  >
                    Cancel
                  </Button>
                )}
                <Button
                  size="sm"
                  variant="ghost"
                  loading={reject.isPending}
                  disabled={reject.isPending}
                  onClick={() => reject.mutate(undefined)}
                >
                  <X /> Reject
                </Button>
              </div>
            </>
          )}
        </CardBody>
      </Card>
    </div>
  );
}

function Transcript({ meeting }: { meeting: Detail }) {
  const live = meeting.status === "transcribing";
  const [more, setMore] = useState<Segment[]>([]);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const list = useRef<HTMLOListElement>(null);
  // while recording, `segments` holds the newest lines; otherwise the first page, and the rest is
  // read page by page until the last line has arrived
  const segments = live ? meeting.segments : [...meeting.segments, ...more];
  const rest = Math.max(0, meeting.segments_total - segments.length);

  useEffect(() => {
    if (live) list.current?.scrollTo({ top: list.current.scrollHeight });
  }, [live, segments.length]);

  async function loadRest() {
    setBusy(true);
    setFailed(false);
    try {
      let offset: number | null = meeting.segments.length + more.length;
      while (offset !== null) {
        const page = await meetingIntelService.transcriptPage(
          meeting.id,
          offset,
        );
        setMore((m) => [...m, ...page.segments]);
        offset = page.next_offset;
      }
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }

  // the same speaker keeps the same colour all the way down
  const order = [...new Set(segments.map((s) => s.speaker || "Speaker"))];
  return (
    <Card>
      <CardBody className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
          <span>
            {live
              ? `Recording: the latest ${segments.length} of ${meeting.segments_total} lines`
              : `${meeting.segments_total} line${meeting.segments_total === 1 ? "" : "s"}`}
          </span>
          <Button asChild variant="secondary">
            <a
              href={meetingIntelService.transcriptDownloadHref(meeting.id)}
              download
            >
              <Download /> Download the full transcript
            </a>
          </Button>
        </div>
        <ol ref={list} className="max-h-[32rem] space-y-3 overflow-y-auto pr-1">
          {segments.map((s) => {
            const name = s.speaker || "Speaker";
            return (
              <li key={s.ordinal} className="flex gap-2.5">
                <SpeakerAvatar name={name} index={order.indexOf(name)} />
                <div className="min-w-0 flex-1">
                  <p className="text-xs">
                    <span className="font-semibold">{name}</span>
                    {clock(s.start_ms) && (
                      <span className="ml-1.5 text-muted-foreground">
                        {clock(s.start_ms)}
                      </span>
                    )}
                  </p>
                  <p className="mt-0.5 rounded-xl rounded-tl-sm bg-surface-muted px-3 py-2 text-[13px] leading-relaxed break-words">
                    {s.text}
                  </p>
                </div>
              </li>
            );
          })}
        </ol>
        {!live && rest > 0 && (
          <div className="flex flex-wrap items-center gap-3">
            <Button
              variant="secondary"
              loading={busy}
              onClick={() => void loadRest()}
            >
              Show the other {rest} line{rest === 1 ? "" : "s"}
            </Button>
            {failed && (
              <span className="text-xs text-danger">
                Some lines could not be loaded. Try again.
              </span>
            )}
          </div>
        )}
      </CardBody>
    </Card>
  );
}
