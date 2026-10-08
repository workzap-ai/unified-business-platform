"use client";

import { Eye, MessageCircle, ThumbsDown, ThumbsUp, User } from "lucide-react";
import { formatDate, formatDateTime } from "@/lib/format";
import { Badge, Card, CardBody, CardHeader } from "@/components/ui/display";
import { useScopedQuery } from "@/hooks/use-scoped";
import { ApiError } from "@/services/api-client";
import { dealService, type DealDocument } from "./deal-service";
import { deliveryLabel } from "./deal-delivery-dialog";

/** "Customer": every link sent for a proposal or invoice, and what the customer did. */
export function DealDocumentsCard({
  filter,
}: {
  filter: { quote_id: string } | { invoice_id: string };
}) {
  const query = useScopedQuery(
    ["deals", "documents", filter],
    () => dealService.documents(filter),
    {
      retry: (count, e) =>
        !(e instanceof ApiError && e.status < 500) && count < 2,
    },
  );
  const docs = query.data ?? [];
  // pi isn't enabled here (or no access): nothing to show.
  if (query.error instanceof ApiError && query.error.status === 403)
    return null;
  return (
    <Card>
      <CardHeader
        title="Customer"
        icon={<User />}
        description="What happened to the links sent on WhatsApp"
      />
      <CardBody>
        {query.isPending ? (
          <p className="text-[13px] text-muted-foreground">Loading…</p>
        ) : query.isError ? (
          <p className="text-[13px] text-muted-foreground">
            Couldn&apos;t load what the customer did.
          </p>
        ) : docs.length === 0 ? (
          <p className="text-[13px] text-muted-foreground">
            Nothing sent on WhatsApp yet.
          </p>
        ) : (
          <ul className="space-y-3">
            {docs.map((d) => (
              <DocumentRow key={d.id} doc={d} />
            ))}
          </ul>
        )}
      </CardBody>
    </Card>
  );
}

function DocumentRow({ doc }: { doc: DealDocument }) {
  return (
    <li className="space-y-1.5 border-b border-border pb-3 text-[13px] last:border-0 last:pb-0">
      <p className="flex items-center gap-1.5 text-muted-foreground">
        <MessageCircle className="size-3.5" aria-hidden="true" />
        <span title={formatDateTime(doc.created_at)}>
          {deliveryLabel(doc.delivery)} · {formatDate(doc.created_at, "d MMM")}
        </span>
      </p>
      <div className="flex flex-wrap gap-1.5">
        {doc.viewed_at ? (
          <Badge tone="info" title={formatDateTime(doc.viewed_at)}>
            <Eye aria-hidden="true" /> Opened{" "}
            {formatDate(doc.viewed_at, "d MMM")}
          </Badge>
        ) : (
          <Badge tone="neutral">Not opened yet</Badge>
        )}
        {doc.response === "accepted" && (
          <Badge tone="success">
            <ThumbsUp aria-hidden="true" /> Accepted
          </Badge>
        )}
        {doc.response === "rejected" && (
          <Badge tone="danger">
            <ThumbsDown aria-hidden="true" /> Declined
          </Badge>
        )}
        {doc.response === "changes" && (
          <Badge tone="warning">Asked for changes</Badge>
        )}
      </div>
      {doc.response === "changes" && doc.response_note && (
        <p className="rounded-md bg-warning-soft/60 px-2.5 py-1.5 whitespace-pre-line text-foreground-secondary">
          Asked for changes: {doc.response_note}
        </p>
      )}
      {doc.response !== "changes" && doc.response_note && (
        <p className="whitespace-pre-line text-foreground-secondary">
          “{doc.response_note}”
        </p>
      )}
    </li>
  );
}
