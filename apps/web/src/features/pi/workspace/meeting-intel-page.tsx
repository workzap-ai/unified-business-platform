"use client";

import { useState } from "react";
import {
  AudioLines,
  ChevronRight,
  Link2Off,
  ListChecks,
  Plus,
  Search,
} from "lucide-react";
import { relativeTime } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Badge, Card, CardBody } from "@/components/ui/display";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import { Checkbox, Label } from "@/components/ui/controls";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/overlays";
import {
  PageHeader,
  PageShell,
  RequirePermission,
} from "@/components/app/page";
import { EmptyState, ErrorState } from "@/components/app/states";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useUrlState } from "@/hooks/use-url-state";
import { useSession } from "@/features/auth/session-provider";
import { customersService } from "@/features/customers/service";
import {
  clock,
  isSwitchedOff,
  MEETING_STATUS_LABELS,
  meetingIntelService,
  type Meeting,
} from "../meeting-intel-service";
import { MeetingDetail } from "./meeting-intel-detail";
import {
  IconTile,
  SkeletonRows,
  StatTile,
  statusTone,
} from "./meeting-intel-parts";

export function MeetingIntelPage() {
  return (
    <RequirePermission permission="pi.meetings.read" area="pi">
      <MeetingIntelView />
    </RequirePermission>
  );
}

function MeetingIntelView() {
  const [url, setUrl] = useUrlState({ meeting: "" });
  if (url.meeting)
    return (
      <MeetingDetail id={url.meeting} onBack={() => setUrl({ meeting: "" })} />
    );
  return <MeetingList open={(id) => setUrl({ meeting: id })} />;
}

function MeetingList({ open }: { open: (id: string) => void }) {
  const { can } = useSession();
  const query = useScopedQuery(["pi", "meeting-intel"], () =>
    meetingIntelService.list(),
  );
  const [creating, setCreating] = useState(false);
  const [term, setTerm] = useState("");
  const [searched, setSearched] = useState("");
  const hits = useScopedQuery(
    ["pi", "meeting-intel", "search", searched],
    () => meetingIntelService.search(searched),
    { enabled: searched.length >= 2 },
  );
  const items = query.data?.items ?? [];
  const unlinked = items.filter((m) => !m.customer_id).length;
  return (
    <PageShell>
      <PageHeader
        title="Meeting intelligence"
        description="What was said in a meeting, what pi understood from it, and what you decide goes into the customer's memory. pi writes nothing to memory until you approve it."
        actions={
          can("pi.meetings.record") ? (
            <Button onClick={() => setCreating(true)}>
              <Plus /> New meeting
            </Button>
          ) : null
        }
      />
      <form
        className="mb-4 flex gap-2 sm:max-w-md"
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          setSearched(term.trim());
        }}
      >
        <Input
          aria-label="Search transcripts"
          placeholder="Search what was said…"
          value={term}
          maxLength={200}
          onChange={(e) => {
            setTerm(e.target.value);
            if (!e.target.value.trim()) setSearched("");
          }}
        />
        <Button type="submit" variant="secondary" aria-label="Search">
          <Search />
        </Button>
      </form>
      {searched.length >= 2 && (
        <section aria-label="Search results" className="mb-6">
          <h2 className="mb-2 text-[13px] font-semibold">
            Results for &ldquo;{searched}&rdquo;
          </h2>
          {hits.isError ? (
            <ErrorState
              error={hits.error}
              onRetry={() => void hits.refetch()}
            />
          ) : hits.isPending ? (
            <div className="h-16 animate-pulse rounded-xl bg-surface-sunken" />
          ) : hits.data.items.length === 0 ? (
            <p className="text-[13px] text-muted-foreground">
              Nothing matches.
            </p>
          ) : (
            <ul className="space-y-2">
              {hits.data.items.map((h) => (
                <li key={`${h.meeting_id}-${h.ordinal}`}>
                  <button
                    type="button"
                    onClick={() => open(h.meeting_id)}
                    className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-left hover:bg-surface-muted"
                  >
                    <span className="text-xs font-semibold">
                      {h.title || "Meeting"}
                      {clock(h.start_ms) && ` · ${clock(h.start_ms)}`}
                    </span>
                    <span className="mt-0.5 block text-[13px] break-words">
                      {h.text}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
      {query.isError ? (
        isSwitchedOff(query.error) ? (
          <EmptyState
            icon={AudioLines}
            title="Meeting intelligence is not switched on"
            description="Ask your Workzap contact to turn it on for this workspace. Nothing is recorded or analysed until then."
          />
        ) : (
          <ErrorState
            error={query.error}
            onRetry={() => void query.refetch()}
          />
        )
      ) : query.isPending ? (
        <SkeletonRows />
      ) : items.length === 0 ? (
        <EmptyState
          icon={AudioLines}
          title="No meetings yet"
          description="Add a meeting, then record it live, add a recorded video or audio file, or paste its transcript. pi writes the transcript and lists the problems, needs, decisions and next steps for you to review."
        />
      ) : (
        <>
          <div className="mb-4 grid gap-3 sm:grid-cols-3">
            <StatTile icon={AudioLines} label="Meetings" value={items.length} />
            <StatTile
              icon={ListChecks}
              tone="warning"
              label="Ready to review"
              value={items.filter((m) => m.status === "review").length}
            />
            <StatTile
              icon={Link2Off}
              tone={unlinked === 0 ? "neutral" : "danger"}
              label="Not linked to a customer"
              value={unlinked}
            />
          </div>
          <ul className="space-y-3">
            {items.map((m) => (
              <MeetingRow key={m.id} meeting={m} onOpen={open} />
            ))}
          </ul>
        </>
      )}
      <NewMeetingDialog
        open={creating}
        onClose={() => setCreating(false)}
        onCreated={(m) => {
          setCreating(false);
          open(m.id);
        }}
      />
    </PageShell>
  );
}

function MeetingRow({
  meeting: m,
  onOpen,
}: {
  meeting: Meeting;
  onOpen: (id: string) => void;
}) {
  return (
    <li>
      <Card className="transition-colors hover:border-border-strong hover:bg-surface-muted/50 motion-reduce:transition-none">
        <CardBody className="p-0">
          <button
            type="button"
            onClick={() => onOpen(m.id)}
            className="flex w-full items-center gap-3 rounded-xl p-4 text-left focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
          >
            <IconTile
              icon={AudioLines}
              tone={m.status === "failed" ? "danger" : "pi"}
            />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[14px] font-semibold">
                {m.title || "Meeting"}
              </span>
              <span className="text-xs text-muted-foreground">
                {m.created_at ? relativeTime(m.created_at) : ""}
                {m.customer_id ? "" : " · not linked to a customer"}
              </span>
            </span>
            <Badge tone={statusTone(m.status)}>
              {MEETING_STATUS_LABELS[m.status] ?? m.status}
            </Badge>
            <ChevronRight
              className="size-4 shrink-0 text-muted-foreground"
              aria-hidden="true"
            />
          </button>
        </CardBody>
      </Card>
    </li>
  );
}

function NewMeetingDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (m: Meeting) => void;
}) {
  const [title, setTitle] = useState("");
  const [consent, setConsent] = useState(false);
  const [note, setNote] = useState("");
  const [customer, setCustomer] = useState("");
  const customers = useScopedQuery(
    ["customers", "meeting-picker"],
    () => customersService.list({ pageSize: 100 }),
    { enabled: open },
  );
  const create = useScopedMutation(
    () =>
      meetingIntelService.create({
        title: title.trim(),
        consent_given: consent,
        consent_note: note.trim(),
        customer_id: customer || null,
      }),
    {
      invalidate: [["pi", "meeting-intel"]],
      success: "Meeting added",
      onSuccess: (m) => {
        setTitle("");
        setConsent(false);
        setNote("");
        setCustomer("");
        onCreated(m);
      },
    },
  );
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => !next && !create.isPending && onClose()}
    >
      <DialogContent size="md">
        <DialogHeader
          title="New meeting"
          description="Everyone in the meeting must agree to it being recorded and analysed before you add it."
        />
        <DialogBody className="space-y-3">
          <div>
            <Label htmlFor="meeting-title">Title</Label>
            <Input
              id="meeting-title"
              value={title}
              maxLength={200}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Kickoff call with the bakery"
            />
          </div>
          <div>
            <Label htmlFor="meeting-customer">Customer</Label>
            <NativeSelect
              id="meeting-customer"
              value={customer}
              onChange={(e) => setCustomer(e.target.value)}
            >
              <option value="">Link later</option>
              {(customers.data?.items ?? []).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </NativeSelect>
            <p className="mt-1 text-xs text-muted-foreground">
              A meeting must be linked to a customer before anything from it can
              be saved to their memory.
            </p>
          </div>
          <label className="flex items-start gap-2 text-[13px]">
            <Checkbox
              checked={consent}
              onCheckedChange={(v) => setConsent(v === true)}
            />
            <span>
              Everyone in this meeting agreed to it being recorded and analysed
            </span>
          </label>
          <div>
            <Label htmlFor="meeting-consent-note">
              How they agreed (optional)
            </Label>
            <Textarea
              id="meeting-consent-note"
              rows={2}
              maxLength={300}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="e.g. Said yes at the start of the call"
            />
          </div>
        </DialogBody>
        <DialogFooter>
          <Button
            variant="secondary"
            onClick={onClose}
            disabled={create.isPending}
          >
            Cancel
          </Button>
          <Button
            loading={create.isPending}
            disabled={!title.trim() || !consent || create.isPending}
            onClick={() => create.mutate(undefined)}
          >
            Add meeting
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
