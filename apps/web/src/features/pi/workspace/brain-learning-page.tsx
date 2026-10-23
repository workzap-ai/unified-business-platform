"use client";

import { useState } from "react";
import { BrainCircuit, Play } from "lucide-react";
import { relativeTime } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Badge, Card, CardBody } from "@/components/ui/display";
import { Input, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/controls";
import {
  PageHeader,
  PageShell,
  RequirePermission,
} from "@/components/app/page";
import { EmptyState, ErrorState } from "@/components/app/states";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useUrlState } from "@/hooks/use-url-state";
import {
  brainLearningService,
  type LearnedPack,
  type Lesson,
  type NotedProblem,
} from "../brain-learning-service";

const TABS = [
  { key: "overview", label: "Overview" },
  { key: "examples", label: "Examples" },
  { key: "questions", label: "Questions" },
  { key: "problems", label: "Problems" },
  { key: "lessons", label: "Teach pi" },
  { key: "packs", label: "Industry packs" },
  { key: "changes", label: "Changes" },
] as const;

const KEY = ["pi", "brain-learning"];

function percent(value: number | undefined) {
  return value === undefined ? "–" : `${(value * 100).toFixed(1)}%`;
}

function Pending() {
  return <div className="h-40 animate-pulse rounded-xl bg-surface-sunken" />;
}

export function BrainLearningPage() {
  return (
    <RequirePermission permission="pi.settings.manage" area="pi">
      <BrainLearningView />
    </RequirePermission>
  );
}

function BrainLearningView() {
  const [url, setUrl] = useUrlState({ tab: "overview" });
  const tab = TABS.some((t) => t.key === url.tab) ? url.tab : "overview";
  return (
    <PageShell>
      <PageHeader
        title="pi brain"
        description="What pi has learned, what it is trying, and what is waiting for a person. Learning only ever changes examples, wordings and tips: pi's rules never move."
      />
      <div className="mb-4 flex flex-wrap gap-1 rounded-lg bg-surface-sunken p-1 sm:w-fit">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setUrl({ tab: t.key })}
            className={
              "rounded-md px-3 py-1.5 text-[13px] font-medium " +
              (tab === t.key
                ? "bg-surface text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground")
            }
          >
            {t.label}
          </button>
        ))}
      </div>
      {tab === "overview" && <Overview />}
      {tab === "examples" && <Examples />}
      {tab === "questions" && <Questions />}
      {tab === "problems" && <Problems />}
      {tab === "lessons" && <Lessons />}
      {tab === "packs" && <Packs />}
      {tab === "changes" && <Changes />}
    </PageShell>
  );
}

function Overview() {
  const health = useScopedQuery([...KEY, "health"], () =>
    brainLearningService.health(7),
  );
  const runs = useScopedQuery([...KEY, "runs"], () =>
    brainLearningService.runs(),
  );
  const run = useScopedMutation(() => brainLearningService.runNow(), {
    invalidate: [KEY],
    success: (r) => (r.frozen ? "Learning is frozen: nothing changed" : "Done"),
  });
  if (health.isError)
    return (
      <ErrorState error={health.error} onRetry={() => void health.refetch()} />
    );
  if (health.isPending) return <Pending />;
  const h = health.data;
  const m = h.metrics;
  return (
    <div className="space-y-4">
      <Card>
        <CardBody className="space-y-3">
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge tone={h.pi_mode === "brain" ? "success" : "neutral"}>
              {h.pi_mode === "brain" ? "Brain mode on" : "Standard mode"}
            </Badge>
            <Badge tone={h.learning_frozen ? "warning" : "success"}>
              {h.learning_frozen ? "Learning frozen" : "Learning on"}
            </Badge>
          </div>
          <p className="text-[13px] text-muted-foreground">
            Last 7 days: {m.scored} replies scored
            {m.average_reward !== undefined && (
              <> · average reward {m.average_reward}</>
            )}
            {" · "}confusion {percent(m.confusion_rate)} · corrections{" "}
            {percent(m.correction_rate)} · opt-outs {percent(m.opt_out_rate)}
          </p>
          <Button
            size="sm"
            variant="secondary"
            loading={run.isPending}
            onClick={() => run.mutate(undefined)}
          >
            <Play /> Run the nightly learning now
          </Button>
        </CardBody>
      </Card>
      <h2 className="text-[13px] font-semibold">Nightly digests</h2>
      {runs.isPending ? (
        <Pending />
      ) : (runs.data?.items ?? []).length === 0 ? (
        <EmptyState
          icon={BrainCircuit}
          title="No runs yet"
          description="The first digest appears after the first nightly run."
        />
      ) : (
        <ul className="space-y-2">
          {runs.data!.items.map((r) => (
            <li key={r.id}>
              <Card>
                <CardBody className="space-y-1">
                  <p className="text-[13px] font-medium">
                    {relativeTime(r.started_at)}
                    {r.frozen && (
                      <Badge tone="warning" className="ml-1.5">
                        frozen
                      </Badge>
                    )}
                  </p>
                  <pre className="overflow-x-auto text-xs text-muted-foreground">
                    {JSON.stringify(r.digest, null, 1)}
                  </pre>
                </CardBody>
              </Card>
            </li>
          ))}
        </ul>
      )}
      <h2 className="text-[13px] font-semibold">Tunable numbers</h2>
      <Card>
        <CardBody>
          <ul className="grid gap-1 text-[13px] sm:grid-cols-2">
            {Object.entries(h.settings).map(([key, s]) => (
              <li key={key} className="flex justify-between gap-3">
                <span className="text-muted-foreground">
                  {key.replaceAll("_", " ")}
                </span>
                <span>
                  {s.value}{" "}
                  <span className="text-xs text-muted-foreground">
                    ({s.low} to {s.high})
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </CardBody>
      </Card>
    </div>
  );
}

function Examples() {
  const examples = useScopedQuery([...KEY, "examples"], () =>
    brainLearningService.examples(),
  );
  const retire = useScopedMutation(
    (id: string) => brainLearningService.retireExample(id, "retired by staff"),
    { invalidate: [KEY], success: "Retired" },
  );
  if (examples.isError)
    return (
      <ErrorState
        error={examples.error}
        onRetry={() => void examples.refetch()}
      />
    );
  if (examples.isPending) return <Pending />;
  const list = examples.data.items;
  if (list.length === 0)
    return (
      <EmptyState
        icon={BrainCircuit}
        title="No examples yet"
        description="Good conversations become redacted examples after a day, are tried on a small share of chats first, and are retired automatically if they do worse."
      />
    );
  return (
    <ul className="space-y-3">
      {list.map((e) => (
        <li key={e.id}>
          <Card>
            <CardBody className="space-y-2">
              <div className="flex flex-wrap items-center gap-1.5">
                <Badge
                  tone={
                    e.status === "active"
                      ? "success"
                      : e.status === "canary"
                        ? "info"
                        : e.status === "retired"
                          ? "neutral"
                          : "warning"
                  }
                >
                  {e.status}
                </Badge>
                <Badge tone="neutral">{e.language}</Badge>
                <span className="text-xs text-muted-foreground">
                  reward {e.reward} · shown {e.uses}×
                </span>
              </div>
              <p className="text-[13px]">
                <span className="text-muted-foreground">Customer:</span>{" "}
                {e.person}
              </p>
              <p className="text-[13px]">
                <span className="text-muted-foreground">pi:</span> {e.reply}
              </p>
              {e.retired_reason && (
                <p className="text-xs text-muted-foreground">
                  Retired: {e.retired_reason}
                </p>
              )}
              {e.status !== "retired" && (
                <Button
                  size="sm"
                  variant="secondary"
                  loading={retire.isPending}
                  onClick={() => retire.mutate(e.id)}
                >
                  Stop using this
                </Button>
              )}
            </CardBody>
          </Card>
        </li>
      ))}
    </ul>
  );
}

function Questions() {
  const arms = useScopedQuery([...KEY, "arms"], () =>
    brainLearningService.arms(),
  );
  const [slot, setSlot] = useState("scope");
  const [text, setText] = useState("");
  const add = useScopedMutation(
    () => brainLearningService.addArm(slot, "en", text),
    {
      invalidate: [KEY],
      success: "Added: it is tried on 10% of chats first",
      onSuccess: () => setText(""),
    },
  );
  const retire = useScopedMutation(
    (id: string) => brainLearningService.retireArm(id),
    { invalidate: [KEY], success: "Retired" },
  );
  if (arms.isError)
    return (
      <ErrorState error={arms.error} onRetry={() => void arms.refetch()} />
    );
  if (arms.isPending) return <Pending />;
  return (
    <div className="space-y-4">
      <Card>
        <CardBody className="space-y-2">
          <Label>A better way to ask</Label>
          <div className="flex flex-col gap-2 sm:flex-row">
            <select
              value={slot}
              onChange={(e) => setSlot(e.target.value)}
              className="h-9 rounded-md border border-border bg-surface px-2 text-[13px]"
            >
              {["scope", "frequency", "impact", "since", "workaround"].map(
                (s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ),
              )}
            </select>
            <Input
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="One short question, no prices or personal details"
            />
            <Button
              size="sm"
              loading={add.isPending}
              disabled={text.trim().length < 8}
              onClick={() => add.mutate(undefined)}
            >
              Add
            </Button>
          </div>
        </CardBody>
      </Card>
      <ul className="space-y-2">
        {arms.data.items.map((a) => (
          <li key={a.id}>
            <Card>
              <CardBody className="flex flex-wrap items-center justify-between gap-2">
                <div className="space-y-0.5">
                  <p className="text-[13px]">{a.text}</p>
                  <p className="text-xs text-muted-foreground">
                    {a.slot} · {a.language} · asked {a.uses}× · success{" "}
                    {percent(a.success_rate)} · {a.created_by}
                    {a.traffic_cap < 1 && " · trial"}
                  </p>
                </div>
                <div className="flex items-center gap-1.5">
                  <Badge tone={a.status === "retired" ? "neutral" : "success"}>
                    {a.status}
                  </Badge>
                  {a.status !== "retired" && (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => retire.mutate(a.id)}
                    >
                      Retire
                    </Button>
                  )}
                </div>
              </CardBody>
            </Card>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Lessons() {
  const lessons = useScopedQuery([...KEY, "lessons"], () =>
    brainLearningService.lessons(),
  );
  const [text, setText] = useState("");
  const [state, setState] = useState("");
  const teach = useScopedMutation(
    () => brainLearningService.teach(text, state, ""),
    {
      invalidate: [KEY],
      success: (l) =>
        l.status === "live"
          ? "pi will use it from the next message"
          : "Waiting for a second person to approve it",
      onSuccess: () => setText(""),
    },
  );
  if (lessons.isError)
    return (
      <ErrorState
        error={lessons.error}
        onRetry={() => void lessons.refetch()}
      />
    );
  if (lessons.isPending) return <Pending />;
  return (
    <div className="space-y-4">
      <Card>
        <CardBody className="space-y-2">
          <Label>Teach pi something in plain words</Label>
          <Textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={3}
            placeholder="When someone mentions late deliveries, ask which route first."
          />
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={state}
              onChange={(e) => setState(e.target.value)}
              className="h-9 rounded-md border border-border bg-surface px-2 text-[13px]"
            >
              <option value="">Any stage</option>
              <option value="S1_LISTENING">Listening</option>
              <option value="S2_CLARIFYING">Clarifying</option>
              <option value="S3_NOTED">After noting a problem</option>
            </select>
            <Button
              size="sm"
              loading={teach.isPending}
              disabled={text.trim().length < 12}
              onClick={() => teach.mutate(undefined)}
            >
              Teach
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            Tips about wording and order go live at once. Anything about money,
            privacy, offers, follow-ups, approvals or advice waits for a
            different person to approve it.
          </p>
        </CardBody>
      </Card>
      {lessons.data.items.length === 0 ? (
        <EmptyState
          icon={BrainCircuit}
          title="No lessons yet"
          description="Lessons you add show up here."
        />
      ) : (
        <ul className="space-y-2">
          {lessons.data.items.map((l) => (
            <LessonRow key={l.id} lesson={l} />
          ))}
        </ul>
      )}
    </div>
  );
}

function LessonRow({ lesson: l }: { lesson: Lesson }) {
  const opts = { invalidate: [KEY] };
  const approve = useScopedMutation(
    () => brainLearningService.approveLesson(l.id),
    { ...opts, success: "Approved" },
  );
  const reject = useScopedMutation(
    () => brainLearningService.rejectLesson(l.id),
    { ...opts, success: "Rejected" },
  );
  const retire = useScopedMutation(
    () => brainLearningService.retireLesson(l.id),
    { ...opts, success: "Retired" },
  );
  return (
    <li>
      <Card>
        <CardBody className="space-y-2">
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge
              tone={
                l.status === "live"
                  ? "success"
                  : l.status === "review"
                    ? "warning"
                    : "neutral"
              }
            >
              {l.status === "review" ? "needs a second person" : l.status}
            </Badge>
            <Badge tone={l.risk === "LOW" ? "neutral" : "danger"}>
              {l.risk.toLowerCase()} risk
            </Badge>
            <span className="text-xs text-muted-foreground">
              used {l.uses}× · {relativeTime(l.created_at)}
            </span>
          </div>
          <p className="text-[13px]">{l.text}</p>
          <div className="flex gap-2">
            {l.status === "review" && (
              <>
                <Button
                  size="sm"
                  loading={approve.isPending}
                  onClick={() => approve.mutate(undefined)}
                >
                  Approve
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  loading={reject.isPending}
                  onClick={() => reject.mutate(undefined)}
                >
                  Reject
                </Button>
              </>
            )}
            {l.status === "live" && (
              <Button
                size="sm"
                variant="secondary"
                loading={retire.isPending}
                onClick={() => retire.mutate(undefined)}
              >
                Retire
              </Button>
            )}
          </div>
        </CardBody>
      </Card>
    </li>
  );
}

function Packs() {
  const packs = useScopedQuery([...KEY, "packs"], () =>
    brainLearningService.packs(),
  );
  if (packs.isError)
    return (
      <ErrorState error={packs.error} onRetry={() => void packs.refetch()} />
    );
  if (packs.isPending) return <Pending />;
  if (packs.data.items.length === 0)
    return (
      <EmptyState
        icon={BrainCircuit}
        title="No drafted packs"
        description="When five different businesses fit none of the industry packs, pi drafts one here for you to review. It never goes live without your approval of what it must refuse and protect."
      />
    );
  return (
    <ul className="space-y-3">
      {packs.data.items.map((p) => (
        <PackCard key={p.id} pack={p} />
      ))}
    </ul>
  );
}

function PackCard({ pack: p }: { pack: LearnedPack }) {
  const [care, setCare] = useState(
    Array.isArray(p.content.care)
      ? (p.content.care as string[]).join("\n")
      : "",
  );
  const [rule, setRule] = useState(
    typeof p.content.scope_rule === "string" ? p.content.scope_rule : "",
  );
  const opts = { invalidate: [KEY] };
  const listening = useScopedMutation(
    () => brainLearningService.approveListening(p.id),
    { ...opts, success: "Running in shadow: counted, never shown" },
  );
  const careOk = useScopedMutation(
    () =>
      brainLearningService.approveCare(
        p.id,
        care
          .split("\n")
          .map((x) => x.trim())
          .filter(Boolean),
        rule,
      ),
    { ...opts, success: "Care sections approved" },
  );
  const reject = useScopedMutation(
    () => brainLearningService.rejectPack(p.id),
    { ...opts, success: "Rejected" },
  );
  const retire = useScopedMutation(
    () => brainLearningService.retirePack(p.id),
    { ...opts, success: "Retired" },
  );
  const open = p.status !== "rejected" && p.status !== "retired";
  const signals = Array.isArray(p.content.signals)
    ? (p.content.signals as string[]).join(", ")
    : "";
  return (
    <li>
      <Card>
        <CardBody className="space-y-3">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-[14px] font-semibold">{p.title}</span>
            <Badge
              tone={
                p.status === "live"
                  ? "success"
                  : p.status === "shadow"
                    ? "info"
                    : p.status === "draft"
                      ? "warning"
                      : "neutral"
              }
            >
              {p.status}
            </Badge>
            <Badge tone={p.care_approved ? "success" : "warning"}>
              {p.care_approved ? "care approved" : "care not approved"}
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground">
            From {p.businesses} businesses · seen in {p.shadow_conversations} of
            20 shadow conversations · {p.descriptions.slice(0, 4).join("; ")}
          </p>
          <p className="text-[13px]">
            <span className="text-muted-foreground">Signals:</span> {signals}
          </p>
          {open && (
            <div className="space-y-2">
              <Label>What pi must refuse or protect in this trade</Label>
              <Textarea
                value={care}
                onChange={(e) => setCare(e.target.value)}
                rows={3}
                placeholder="One point per line"
              />
              <Input
                value={rule}
                onChange={(e) => setRule(e.target.value)}
                placeholder="Scope rule: what pi notes and what it refuses"
              />
            </div>
          )}
          {open && (
            <div className="flex flex-wrap gap-2">
              {p.status === "draft" && (
                <Button
                  size="sm"
                  loading={listening.isPending}
                  onClick={() => listening.mutate(undefined)}
                >
                  Approve listening sections
                </Button>
              )}
              <Button
                size="sm"
                variant="secondary"
                loading={careOk.isPending}
                disabled={!care.trim() || !rule.trim()}
                onClick={() => careOk.mutate(undefined)}
              >
                Approve care sections
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() =>
                  p.status === "live"
                    ? retire.mutate(undefined)
                    : reject.mutate(undefined)
                }
              >
                {p.status === "live" ? "Retire" : "Reject"}
              </Button>
            </div>
          )}
        </CardBody>
      </Card>
    </li>
  );
}

function Problems() {
  const noted = useScopedQuery([...KEY, "problems"], () =>
    brainLearningService.problems(),
  );
  const links = useScopedQuery([...KEY, "links"], () =>
    brainLearningService.links(),
  );
  const decide = useScopedMutation(
    (v: { id: string; decision: "confirm" | "reject" }) =>
      brainLearningService.decideLink(v.id, v.decision),
    { invalidate: [KEY], success: "Saved" },
  );
  if (noted.isError)
    return (
      <ErrorState error={noted.error} onRetry={() => void noted.refetch()} />
    );
  if (noted.isPending) return <Pending />;
  const { categories, items } = noted.data;
  return (
    <div className="space-y-6">
      <section className="space-y-2">
        <h2 className="text-sm font-semibold">Suggested links</h2>
        <p className="text-xs text-muted-foreground">
          pi thinks these problems may share a root. Confirming or rejecting
          teaches it how readily to suggest links for each kind of business.
        </p>
        {links.data && links.data.items.length === 0 && (
          <p className="text-[13px] text-muted-foreground">Nothing waiting.</p>
        )}
        <ul className="space-y-1.5">
          {(links.data?.items ?? []).map((l) => (
            <li
              key={l.id}
              className="flex flex-wrap items-center gap-2 rounded-lg bg-surface-muted px-3 py-2 text-[13px]"
            >
              <Badge tone="neutral">{l.type.replaceAll("_", " ")}</Badge>
              <span>{l.from}</span>
              <span className="text-xs text-muted-foreground">
                {Math.round(l.confidence * 100)}% sure
              </span>
              <span className="ml-auto flex gap-1.5">
                <Button
                  size="sm"
                  variant="secondary"
                  loading={decide.isPending}
                  onClick={() =>
                    decide.mutate({ id: l.id, decision: "confirm" })
                  }
                >
                  Confirm
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  loading={decide.isPending}
                  onClick={() =>
                    decide.mutate({ id: l.id, decision: "reject" })
                  }
                >
                  Reject
                </Button>
              </span>
            </li>
          ))}
        </ul>
      </section>
      <section className="space-y-2">
        <h2 className="text-sm font-semibold">Noted problems</h2>
        <p className="text-xs text-muted-foreground">
          Fix a title or an area. A correction counts five times a
          customer&apos;s word when pi learns vocabulary.
        </p>
        {items.length === 0 ? (
          <EmptyState
            icon={BrainCircuit}
            title="No problems noted yet"
            description="Problems pi notes in brain mode show up here."
          />
        ) : (
          <ul className="space-y-3">
            {items.map((p) => (
              <ProblemRow key={p.id} problem={p} categories={categories} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function ProblemRow({
  problem: p,
  categories,
}: {
  problem: NotedProblem;
  categories: { key: string; label: string }[];
}) {
  const [title, setTitle] = useState(p.title);
  const [category, setCategory] = useState(p.category);
  const save = useScopedMutation(
    () =>
      brainLearningService.correctProblem(p.id, {
        ...(title.trim() !== p.title ? { title: title.trim() } : {}),
        ...(category !== p.category ? { category } : {}),
      }),
    { invalidate: [KEY], success: "Corrected" },
  );
  const changed = title.trim() !== p.title || category !== p.category;
  return (
    <li>
      <Card>
        <CardBody className="space-y-2">
          {p.words[0] && (
            <p className="text-xs text-muted-foreground">
              They said: “{p.words[0]}”
            </p>
          )}
          <div className="grid gap-2 sm:grid-cols-[1fr_14rem_auto]">
            <Input
              aria-label="Problem title"
              value={title}
              maxLength={120}
              onChange={(e) => setTitle(e.target.value)}
            />
            <select
              aria-label="Area"
              className="h-9 rounded-md border border-border bg-surface px-2 text-[13px]"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            >
              {categories.map((c) => (
                <option key={c.key} value={c.key}>
                  {c.label}
                </option>
              ))}
            </select>
            <Button
              size="sm"
              disabled={!changed || !title.trim()}
              loading={save.isPending}
              onClick={() => save.mutate(undefined)}
            >
              Save
            </Button>
          </div>
        </CardBody>
      </Card>
    </li>
  );
}

function Changes() {
  const changes = useScopedQuery([...KEY, "changes"], () =>
    brainLearningService.changes(),
  );
  if (changes.isError)
    return (
      <ErrorState
        error={changes.error}
        onRetry={() => void changes.refetch()}
      />
    );
  if (changes.isPending) return <Pending />;
  if (changes.data.items.length === 0)
    return (
      <EmptyState
        icon={BrainCircuit}
        title="No changes yet"
        description="Every change learning makes is logged here with its reason."
      />
    );
  return (
    <ul className="space-y-1.5">
      {changes.data.items.map((c) => (
        <li
          key={c.id}
          className="flex flex-wrap items-center gap-2 rounded-lg bg-surface-muted px-3 py-2 text-[13px]"
        >
          <Badge tone={c.status === "rolled_back" ? "danger" : "neutral"}>
            {c.status}
          </Badge>
          <span className="font-medium">{c.kind.replaceAll("_", " ")}</span>
          <span className="text-muted-foreground">{c.reason}</span>
          <span className="ml-auto text-xs text-muted-foreground">
            {relativeTime(c.created_at)}
          </span>
        </li>
      ))}
    </ul>
  );
}
