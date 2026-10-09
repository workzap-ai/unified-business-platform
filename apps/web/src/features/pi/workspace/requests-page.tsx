"use client";

import { useState } from "react";
import Link from "next/link";
import {
  Bot,
  CalendarClock,
  FileSearch,
  FileText,
  MessageCircleQuestion,
  MessageSquare,
  Receipt,
  Stamp,
  Target,
} from "lucide-react";
import { formatDateTime, relativeTime } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Badge, Card, CardBody } from "@/components/ui/display";
import { Textarea } from "@/components/ui/input";
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
import { customerFilesService } from "@/features/customers/files-service";
import {
  piRequestsService,
  REQUEST_KIND_LABELS,
  type PiRequest,
  type RequestKind,
} from "../requests-service";
import { inboxHref } from "./lib";

const KIND_ICONS: Record<RequestKind, typeof Bot> = {
  question: MessageCircleQuestion,
  price: Receipt,
  review_document: FileSearch,
  approve: Stamp,
  meeting: CalendarClock,
  other: Bot,
};

const TABS = [
  { key: "open", label: "Waiting for you" },
  { key: "done", label: "Answered" },
] as const;

export function RequestsPage() {
  return (
    <RequirePermission permission="pi.inbox.reply" area="pi">
      <RequestsView />
    </RequirePermission>
  );
}

function RequestsView() {
  const [url, setUrl] = useUrlState({ tab: "open" });
  const status = url.tab === "done" ? "done" : "open";
  const query = useScopedQuery(["pi", "requests", status], () =>
    piRequestsService.list(status),
  );
  const [answering, setAnswering] = useState<PiRequest | null>(null);
  const items = query.data?.items ?? [];
  return (
    <PageShell>
      <PageHeader
        title="Requests"
        description="What pi asked your team. Answer here and pi replies to the customer itself, in their language."
      />
      <div className="mb-4 flex gap-1 rounded-lg bg-surface-sunken p-1 sm:w-fit">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setUrl({ tab: t.key })}
            className={
              "flex-1 rounded-md px-3 py-1.5 text-[13px] font-medium sm:flex-none " +
              (status === t.key
                ? "bg-surface text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground")
            }
          >
            {t.label}
            {t.key === "open" && query.data?.open ? (
              <Badge tone="warning" className="ml-1.5">
                {query.data.open}
              </Badge>
            ) : null}
          </button>
        ))}
      </div>
      {query.isError ? (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      ) : query.isPending ? (
        <div className="h-40 animate-pulse rounded-xl bg-surface-sunken" />
      ) : items.length === 0 ? (
        <EmptyState
          icon={MessageCircleQuestion}
          title={status === "open" ? "Nothing waiting" : "No answers yet"}
          description={
            status === "open"
              ? "When pi needs a price, an approval, a document check or an answer it doesn't know, it asks here."
              : "Requests you answer appear here."
          }
        />
      ) : (
        <ul className="space-y-3">
          {items.map((r) => (
            <RequestCard key={r.id} request={r} onAnswer={setAnswering} />
          ))}
        </ul>
      )}
      <AnswerDialog request={answering} onClose={() => setAnswering(null)} />
    </PageShell>
  );
}

function RequestCard({
  request: r,
  onAnswer,
}: {
  request: PiRequest;
  onAnswer: (r: PiRequest) => void;
}) {
  const { can } = useSession();
  const Icon = KIND_ICONS[r.kind];
  const open = r.status === "open";
  const dismiss = useScopedMutation(() => piRequestsService.dismiss(r.id), {
    invalidate: [["pi", "requests"]],
    success: "Request dismissed",
  });
  return (
    <li>
      <Card>
        <CardBody className="space-y-3">
          <div className="flex items-start gap-3">
            <span className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg bg-pi-soft text-pi">
              <Icon className="size-4" aria-hidden="true" />
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-[14px] font-semibold">
                  {REQUEST_KIND_LABELS[r.kind]}
                </span>
                {r.priority === "high" && <Badge tone="danger">Urgent</Badge>}
                {!open && (
                  <Badge
                    tone={r.status === "dismissed" ? "neutral" : "success"}
                  >
                    {r.status === "resolved"
                      ? "Done"
                      : r.status === "dismissed"
                        ? "Dismissed"
                        : "Answered"}
                  </Badge>
                )}
              </div>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {r.customer_name ?? "Customer"} ·{" "}
                <span title={formatDateTime(r.created_at)}>
                  {relativeTime(r.created_at)}
                </span>
              </p>
            </div>
          </div>
          <p className="text-[13px] leading-relaxed break-words whitespace-pre-wrap">
            {r.question}
          </p>
          {r.answer && (
            <div className="rounded-lg bg-surface-muted px-3 py-2 text-[13px]">
              <p className="text-2xs font-semibold tracking-wide text-muted-foreground uppercase">
                Answer for pi
              </p>
              <p className="mt-0.5 break-words whitespace-pre-wrap">
                {r.answer}
              </p>
            </div>
          )}
          <div className="flex flex-wrap items-center gap-2">
            {open && can("pi.inbox.reply") && (
              <Button size="sm" onClick={() => onAnswer(r)}>
                Answer
              </Button>
            )}
            <Button size="sm" variant="secondary" asChild>
              <Link href={inboxHref(r.conversation_id)}>
                <MessageSquare /> Chat
              </Link>
            </Button>
            {r.quote_id && (
              <Button size="sm" variant="secondary" asChild>
                <Link
                  href={
                    r.kind === "price"
                      ? `/quotes/${r.quote_id}/edit`
                      : `/quotes/${r.quote_id}`
                  }
                >
                  <FileText /> {r.kind === "price" ? "Add prices" : "Proposal"}
                </Link>
              </Button>
            )}
            {r.lead_id && (
              <Button size="sm" variant="ghost" asChild>
                <Link href={`/sales/leads/${r.lead_id}`}>
                  <Target /> Deal
                </Link>
              </Button>
            )}
            {r.file_id && (
              <Button size="sm" variant="ghost" asChild>
                <a href={customerFilesService.downloadUrl(r.file_id)}>
                  <FileText /> File
                </a>
              </Button>
            )}
            {open && can("pi.inbox.reply") && (
              <Button
                size="sm"
                variant="ghost"
                className="ml-auto"
                loading={dismiss.isPending}
                onClick={() => dismiss.mutate(undefined)}
              >
                Dismiss
              </Button>
            )}
          </div>
          {open && (r.kind === "price" || r.kind === "approve") && (
            <p className="text-xs text-muted-foreground">
              This closes by itself when the proposal is sent.
            </p>
          )}
        </CardBody>
      </Card>
    </li>
  );
}

function AnswerDialog({
  request,
  onClose,
}: {
  request: PiRequest | null;
  onClose: () => void;
}) {
  const { can } = useSession();
  const [text, setText] = useState("");
  const [knowledge, setKnowledge] = useState(false);
  const answer = useScopedMutation(
    () => piRequestsService.answer(request!.id, text.trim(), knowledge),
    {
      invalidate: [["pi", "requests"], ["pi"]],
      success: "Answered. pi will reply to the customer.",
      onSuccess: () => {
        setText("");
        setKnowledge(false);
        onClose();
      },
    },
  );
  return (
    <Dialog
      open={request !== null}
      onOpenChange={(next) => !next && !answer.isPending && onClose()}
    >
      <DialogContent size="md">
        <DialogHeader
          title="Answer for pi"
          description="Write what pi should know. pi turns it into a reply for the customer, in their language. It isn't sent word for word."
        />
        <DialogBody className="space-y-3">
          {request && (
            <p className="rounded-lg bg-surface-muted px-3 py-2 text-[13px] whitespace-pre-wrap">
              {request.question}
            </p>
          )}
          <div>
            <Label htmlFor="request-answer">Your answer</Label>
            <Textarea
              id="request-answer"
              rows={5}
              maxLength={4000}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="e.g. Yes, we deliver to Karachi in 3 working days."
            />
          </div>
          {can("pi.knowledge.manage") && (
            <label className="flex items-start gap-2 text-[13px]">
              <Checkbox
                checked={knowledge}
                onCheckedChange={(v) => setKnowledge(v === true)}
              />
              <span>
                Also save it so pi can answer this itself next time
                <span className="block text-xs text-muted-foreground">
                  Added to pi&apos;s knowledge.
                </span>
              </span>
            </label>
          )}
        </DialogBody>
        <DialogFooter>
          <Button
            variant="secondary"
            onClick={onClose}
            disabled={answer.isPending}
          >
            Cancel
          </Button>
          <Button
            loading={answer.isPending}
            disabled={!text.trim() || answer.isPending}
            onClick={() => answer.mutate(undefined)}
          >
            Send to pi
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
