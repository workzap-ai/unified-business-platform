"use client";

/**
 * The request desk: what pi asked the team (a price, an approval, a document to check,
 * a meeting to arrange, or an answer it doesn't know). The team answers here and pi
 * replies to the customer itself, in their language.
 * API: app/modules/pi_saas/requests.py (/pi/requests).
 */
import { useQuery } from "@tanstack/react-query";
import {
  CalendarClock,
  FileSearch,
  FileText,
  Handshake,
  MessageCircle,
  MessageCircleQuestion,
  Receipt,
  Stamp,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";

import { PiFace } from "@/components/brand";
import {
  Badge,
  Button,
  Card,
  CardSection,
  Dialog,
  DialogContent,
  EmptyState,
  ErrorState,
  Field,
  LoadingBlock,
  Notice,
  PageHeader,
  Textarea,
  cn,
} from "@/components/ui";
import { fileDownloadUrl } from "@/features/customer-files";
import { errorText, get, post } from "@/lib/api";
import { dateTime, timeAgo } from "@/lib/format";
import { useAction, useBusinessKey, useCan } from "@/lib/session";

export type RequestKind =
  "question" | "price" | "review_document" | "approve" | "meeting" | "other";

export interface PiRequest {
  id: string;
  kind: RequestKind;
  priority: "normal" | "high";
  status: string;
  question: string;
  context: string;
  answer: string | null;
  conversation_id: string;
  customer_id: string;
  customer_name: string | null;
  lead_id: string | null;
  quote_id: string | null;
  file_id: string | null;
  created_at: string;
  resolved_at: string | null;
}

export interface RequestList {
  items: PiRequest[];
  open: number;
}

const KINDS: Record<RequestKind, { label: string; icon: LucideIcon }> = {
  question: { label: "Question", icon: MessageCircleQuestion },
  price: { label: "Price a proposal", icon: Receipt },
  review_document: { label: "Review a document", icon: FileSearch },
  approve: { label: "Approve a proposal", icon: Stamp },
  meeting: { label: "Arrange a meeting", icon: CalendarClock },
  other: { label: "Other", icon: MessageCircleQuestion },
};

const DONE_LABEL: Record<string, string> = {
  answered: "Answered",
  published: "Answered",
  resolved: "Done",
  dismissed: "Dismissed",
};

/** Open requests, for the navigation badge. Shared cache with the desk's open tab. */
export function useOpenRequests(enabled = true) {
  const key = useBusinessKey();
  return useQuery({
    queryKey: key(["requests", "open"]),
    queryFn: () => get<RequestList>("/pi/requests", { status: "open" }),
    enabled,
    refetchInterval: 60_000,
  });
}

export function RequestsPage() {
  const can = useCan();
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const key = useBusinessKey();
  const status = params.get("tab") === "done" ? "done" : "open";
  const highlight = params.get("request");
  const allowed = can("pi.read");
  const list = useQuery({
    queryKey: key(["requests", status]),
    queryFn: () => get<RequestList>("/pi/requests", { status }),
    enabled: allowed,
  });
  const open = useOpenRequests(allowed && status !== "open");
  const openCount = status === "open" ? list.data?.open : open.data?.open;
  const [answering, setAnswering] = React.useState<PiRequest | null>(null);

  // A link to one request (from a deal or a notification) scrolls to it.
  React.useEffect(() => {
    if (!highlight || !list.data) return;
    document
      .getElementById(`request-${highlight}`)
      ?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [highlight, list.data]);

  function setTab(tab: "open" | "done") {
    const next = new URLSearchParams(params.toString());
    if (tab === "open") next.delete("tab");
    else next.set("tab", tab);
    const query = next.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, {
      scroll: false,
    });
  }

  if (!allowed) {
    return (
      <div>
        <PageHeader title="Requests" />
        <Notice tone="info" title="No access to requests">
          Your role doesn&apos;t include pi&apos;s conversations. Ask your
          business owner if you need it.
        </Notice>
      </div>
    );
  }

  const items = list.data?.items ?? [];
  const highlighted = highlight ? items.some((r) => r.id === highlight) : true;
  return (
    <div>
      <PageHeader
        title="Requests"
        description="What pi asked your team. Answer here and pi replies to the customer itself, in their language. Your answer isn't sent word for word."
      />
      <div
        className="mb-4 flex w-full gap-1 rounded-lg border border-border bg-surface p-1 sm:w-fit"
        role="tablist"
        aria-label="Requests"
      >
        {(
          [
            { key: "open", label: "Waiting for you" },
            { key: "done", label: "Answered" },
          ] as const
        ).map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={status === t.key}
            onClick={() => setTab(t.key)}
            className={cn(
              "flex h-9 flex-1 items-center justify-center gap-1.5 whitespace-nowrap rounded-md px-3 text-sm font-medium text-foreground-secondary hover:text-foreground sm:flex-none",
              status === t.key && "bg-accent-soft text-accent-soft-foreground",
            )}
          >
            {t.label}
            {t.key === "open" && openCount ? (
              <Badge tone="warning">{openCount}</Badge>
            ) : null}
          </button>
        ))}
      </div>
      {list.isPending ? (
        <LoadingBlock rows={3} label="Loading requests" />
      ) : list.isError ? (
        <ErrorState
          message={errorText(list.error)}
          onRetry={() => list.refetch()}
        />
      ) : items.length === 0 ? (
        <EmptyState
          icon={<MessageCircleQuestion className="size-6" aria-hidden />}
          title={status === "open" ? "Nothing waiting" : "No answers yet"}
        >
          {status === "open"
            ? "When pi needs a price, an approval, a document check, a meeting time or an answer it doesn't know, it asks here."
            : "Requests you answer appear here."}
        </EmptyState>
      ) : (
        <>
          {!highlighted ? (
            <div className="mb-4">
              <Notice tone="info">
                That request isn&apos;t in this list.{" "}
                {status === "open"
                  ? "It may already be answered: look under Answered."
                  : "It may still be waiting for you."}
              </Notice>
            </div>
          ) : null}
          <ul className="space-y-3">
            {items.map((r) => (
              <RequestCard
                key={r.id}
                request={r}
                highlight={r.id === highlight}
                onAnswer={setAnswering}
              />
            ))}
          </ul>
        </>
      )}
      <AnswerDialog request={answering} onClose={() => setAnswering(null)} />
    </div>
  );
}

function RequestCard({
  request: r,
  highlight,
  onAnswer,
}: {
  request: PiRequest;
  highlight: boolean;
  onAnswer: (r: PiRequest) => void;
}) {
  const can = useCan();
  const kind = KINDS[r.kind] ?? KINDS.other;
  const Icon = kind.icon;
  const open = r.status === "open";
  const reply = can("pi.inbox.reply");
  const deals = can("sales.read");
  const dismiss = useAction(() => post(`/pi/requests/${r.id}/dismiss`), {
    success: "Request dismissed",
    invalidate: [["requests"], ["questions"]],
  });
  return (
    <li id={`request-${r.id}`} className="scroll-mt-24">
      <Card className={cn(highlight && "border-accent ring-2 ring-accent/30")}>
        <CardSection className="space-y-3">
          <div className="flex items-start gap-3">
            <span className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent-soft-foreground">
              <Icon className="size-4" aria-hidden />
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="font-semibold">{kind.label}</span>
                {r.priority === "high" ? (
                  <Badge tone="danger">Urgent</Badge>
                ) : null}
                {!open ? (
                  <Badge
                    tone={r.status === "dismissed" ? "neutral" : "success"}
                  >
                    {DONE_LABEL[r.status] ?? "Done"}
                  </Badge>
                ) : null}
              </div>
              <p className="mt-0.5 truncate text-xs text-muted-foreground">
                {r.customer_name ?? "Customer"} ·{" "}
                <span title={dateTime(r.created_at)}>
                  {timeAgo(r.created_at)}
                </span>
              </p>
            </div>
          </div>
          <p
            className="whitespace-pre-wrap break-words text-sm leading-relaxed"
            data-user-text
          >
            {r.question}
          </p>
          {r.context ? (
            <p
              className="whitespace-pre-wrap break-words text-xs text-muted-foreground"
              data-user-text
            >
              {r.context}
            </p>
          ) : null}
          {r.answer ? (
            <div className="rounded-lg bg-surface-muted px-3 py-2 text-sm">
              <p className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground">
                <PiFace size={14} decorative /> Your answer for pi
              </p>
              <p
                className="mt-0.5 whitespace-pre-wrap break-words"
                data-user-text
              >
                {r.answer}
              </p>
            </div>
          ) : null}
          <div className="flex flex-wrap items-center gap-2">
            {open && reply ? (
              <Button size="sm" onClick={() => onAnswer(r)}>
                Answer
              </Button>
            ) : null}
            <Button asChild size="sm" variant="secondary">
              <Link href={`/inbox?conversation=${r.conversation_id}`}>
                <MessageCircle className="size-4" aria-hidden /> Chat
              </Link>
            </Button>
            {r.quote_id && r.lead_id && deals ? (
              <Button asChild size="sm" variant="secondary">
                <Link href={`/deals/${r.lead_id}`}>
                  <FileText className="size-4" aria-hidden />
                  {r.kind === "price" ? "Add prices" : "Proposal"}
                </Link>
              </Button>
            ) : null}
            {r.lead_id && deals ? (
              <Button asChild size="sm" variant="ghost">
                <Link href={`/deals/${r.lead_id}`}>
                  <Handshake className="size-4" aria-hidden /> Deal
                </Link>
              </Button>
            ) : null}
            {r.file_id ? (
              <Button asChild size="sm" variant="ghost">
                <a href={fileDownloadUrl(r.file_id)}>
                  <FileText className="size-4" aria-hidden /> File
                </a>
              </Button>
            ) : null}
            {open && reply ? (
              <Button
                size="sm"
                variant="ghost"
                className="ms-auto"
                loading={dismiss.isPending}
                onClick={() => dismiss.mutate(undefined)}
              >
                Dismiss
              </Button>
            ) : null}
          </div>
          {open && (r.kind === "price" || r.kind === "approve") ? (
            <p className="text-xs text-muted-foreground">
              This closes by itself when the proposal is sent.
            </p>
          ) : null}
          {open && r.kind === "meeting" ? (
            <p className="text-xs text-muted-foreground">
              Answer with a time (and a link or place). pi confirms it to the
              customer on WhatsApp.
            </p>
          ) : null}
        </CardSection>
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
  const can = useCan();
  const [text, setText] = React.useState("");
  const [knowledge, setKnowledge] = React.useState(false);
  const answer = useAction(
    () =>
      post(`/pi/requests/${request?.id}/answer`, {
        answer: text.trim(),
        save_as_knowledge: knowledge,
      }),
    {
      success: "Answered. pi will reply to the customer.",
      invalidate: [["requests"], ["questions"], ["conversations"], ["home"]],
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
      onOpenChange={(next) => (!next && !answer.isPending ? onClose() : null)}
    >
      <DialogContent
        title="Answer for pi"
        description="Write what pi should know. pi turns it into a reply for the customer, in their language."
      >
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (text.trim()) answer.mutate(undefined);
          }}
        >
          {request ? (
            <p
              className="whitespace-pre-wrap break-words rounded-lg bg-surface-muted px-3 py-2 text-sm"
              data-user-text
            >
              {request.question}
            </p>
          ) : null}
          <Field
            label="Your answer"
            htmlFor="request-answer"
            hint={
              request?.kind === "meeting"
                ? "e.g. Tuesday 3 pm on Google Meet: https://meet.google.com/…"
                : "e.g. Yes, we deliver to Karachi in 3 working days."
            }
          >
            <Textarea
              id="request-answer"
              rows={5}
              maxLength={4000}
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
          </Field>
          {can("pi.knowledge.manage") ? (
            <label className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                className="mt-1 size-4 accent-[var(--color-accent)]"
                checked={knowledge}
                onChange={(e) => setKnowledge(e.target.checked)}
              />
              <span>
                Also save it so pi can answer this itself next time
                <span className="block text-xs text-muted-foreground">
                  Added to pi&apos;s knowledge.
                </span>
              </span>
            </label>
          ) : null}
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <Button
              type="button"
              variant="ghost"
              disabled={answer.isPending}
              onClick={onClose}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              loading={answer.isPending}
              disabled={!text.trim()}
            >
              Send to pi
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
