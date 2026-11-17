"use client";

import {
  Download,
  FileText,
  Presentation,
  Trash2,
  CheckCheck,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge, Card, CardBody } from "@/components/ui/display";
import { Notice } from "@/components/app/states";
import { relativeTime } from "@/lib/format";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import { ApiError } from "@/services/api-client";
import {
  DOCUMENT_LABELS,
  meetingIntelService,
  type DocumentKind,
  type MeetingDetail as Detail,
  type MeetingDocument,
} from "../meeting-intel-service";

/**
 * Designed documents after the meeting: a summary PDF and an editable PowerPoint deck. pi draws them
 * from the findings a person approved on this tab (never from pending ideas or the raw transcript),
 * so what is in a document is what the team chose to keep. A price, phone, card or ID number cannot
 * appear in one. A new document is a draft; a person with the approve permission approves it, and
 * only then is it ready to share with the customer. Asking again for the same content returns the
 * same draft.
 */
const REFUSED: Record<string, string> = {
  MEETING_NOTHING_APPROVED:
    "Approve at least one finding below first. A document is made only from approved findings.",
  MEETING_DOCUMENT_LIMIT:
    "This meeting has enough documents. Delete a draft you do not need first.",
  MEETING_DOCUMENT_FONT_MISSING:
    "The server could not draw this language, so no document was made. Ask the platform owner.",
  MEETING_DOCUMENT_TOO_LARGE: "This document is too large to keep.",
};

function sizeText(bytes: number): string {
  return bytes >= 1_000_000
    ? `${(bytes / 1_000_000).toFixed(1)} MB`
    : `${Math.max(1, Math.round(bytes / 1000))} KB`;
}

export function MeetingDocuments({ meeting }: { meeting: Detail }) {
  const { can } = useSession();
  const key = ["pi", "meeting-intel", meeting.id, "documents"];
  const list = useScopedQuery(key, () =>
    meetingIntelService.documents(meeting.id),
  );
  const approvedCount = meeting.insights.filter(
    (i) => i.review_status === "approved" || i.review_status === "edited",
  ).length;
  const make = useScopedMutation(
    (kind: DocumentKind) => meetingIntelService.makeDocument(meeting.id, kind),
    { invalidate: [key], toastErrors: false },
  );
  const approve = useScopedMutation(
    (docId: string) => meetingIntelService.approveDocument(meeting.id, docId),
    { invalidate: [key], toastErrors: false },
  );
  const remove = useScopedMutation(
    (docId: string) => meetingIntelService.deleteDocument(meeting.id, docId),
    { invalidate: [key], toastErrors: false, success: "Draft deleted" },
  );
  const canMake = can("pi.meetings.record");
  const items = list.data?.items ?? [];
  const error = [make.error, approve.error, remove.error].find(Boolean);
  const failure =
    error instanceof ApiError
      ? (REFUSED[error.code ?? ""] ?? "Could not do that. Try again.")
      : error
        ? "Could not do that. Try again."
        : "";
  const pending = make.isPending ? make.variables : undefined;
  return (
    <Card>
      <CardBody className="space-y-3">
        <div>
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <FileText className="size-4" aria-hidden /> Documents
          </h2>
          <p className="mt-1 text-xs text-muted-foreground">
            A designed summary PDF and an editable PowerPoint deck, made from
            the findings you approved. They carry no prices or personal numbers.
          </p>
        </div>
        {approvedCount === 0 && (
          <Notice tone="info">
            Approve at least one finding below, then make a document.
          </Notice>
        )}
        {canMake && (
          <div className="flex flex-wrap gap-2">
            {(["summary_pdf", "deck_pptx"] as const).map((kind) => (
              <Button
                key={kind}
                variant="secondary"
                loading={pending === kind}
                disabled={approvedCount === 0 || make.isPending}
                onClick={() => make.mutate(kind)}
              >
                {kind === "summary_pdf" ? <FileText /> : <Presentation />}
                Make {DOCUMENT_LABELS[kind].toLowerCase()}
              </Button>
            ))}
          </div>
        )}
        {failure && <Notice tone="warning">{failure}</Notice>}
        {list.isError ? (
          <Notice tone="warning">Could not load the documents.</Notice>
        ) : list.isPending ? (
          <div className="h-12 animate-pulse rounded-lg bg-surface-sunken" />
        ) : items.length === 0 ? (
          <p className="text-xs text-muted-foreground">No documents yet.</p>
        ) : (
          <ul className="space-y-2">
            {items.map((d) => (
              <DocumentRow
                key={d.id}
                doc={d}
                meetingId={meeting.id}
                canApprove={can("pi.meetings.approve")}
                canDelete={canMake}
                busy={approve.isPending || remove.isPending}
                onApprove={() => approve.mutate(d.id)}
                onDelete={() => remove.mutate(d.id)}
              />
            ))}
          </ul>
        )}
      </CardBody>
    </Card>
  );
}

function DocumentRow({
  doc,
  meetingId,
  canApprove,
  canDelete,
  busy,
  onApprove,
  onDelete,
}: {
  doc: MeetingDocument;
  meetingId: string;
  canApprove: boolean;
  canDelete: boolean;
  busy: boolean;
  onApprove: () => void;
  onDelete: () => void;
}) {
  const Icon = doc.kind === "deck_pptx" ? Presentation : FileText;
  const approved = doc.status === "approved";
  return (
    <li className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-surface px-3 py-2">
      <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="truncate text-[13px] font-medium">
          {DOCUMENT_LABELS[doc.kind]}
        </p>
        <p className="text-xs text-muted-foreground">
          {sizeText(doc.size_bytes)}
          {doc.created_at ? ` · ${relativeTime(doc.created_at)}` : ""}
          {doc.lines_left_out > 0
            ? ` · ${doc.lines_left_out} line${doc.lines_left_out === 1 ? "" : "s"} left out (price)`
            : ""}
        </p>
      </div>
      <Badge tone={approved ? "success" : "neutral"}>
        {approved ? "Approved" : "Draft"}
      </Badge>
      <Button
        variant="secondary"
        size="sm"
        asChild
        aria-label={`Download ${DOCUMENT_LABELS[doc.kind]}`}
      >
        <a
          href={meetingIntelService.documentHref(meetingId, doc.id)}
          download
          rel="noopener"
        >
          <Download /> Download
        </a>
      </Button>
      {!approved && canApprove && (
        <Button size="sm" disabled={busy} onClick={onApprove}>
          <CheckCheck /> Approve
        </Button>
      )}
      {!approved && canDelete && (
        <Button
          variant="ghost"
          size="sm"
          disabled={busy}
          onClick={onDelete}
          aria-label={`Delete draft ${DOCUMENT_LABELS[doc.kind]}`}
        >
          <Trash2 />
        </Button>
      )}
    </li>
  );
}
