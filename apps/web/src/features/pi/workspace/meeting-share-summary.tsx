"use client";

import { useState } from "react";
import { Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/display";
import { Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/controls";
import { Notice } from "@/components/app/states";
import { useScopedMutation } from "@/hooks/use-scoped";
import { ApiError } from "@/services/api-client";
import {
  meetingIntelService,
  type MeetingDetail as Detail,
} from "../meeting-intel-service";

/**
 * Send the approved summary to the customer. pi never does this by itself: a person reads the
 * words, may change them, and presses send. The message goes through the inbox's own reply path,
 * so the conversation must be taken over by a person and the customer must have written in the
 * last 24 hours. A price cannot be sent here, and a summary is sent once.
 */
const REFUSED: Record<string, string> = {
  TAKEOVER_REQUIRED:
    "Take over the customer's conversation in the inbox first, then send.",
  MESSAGE_WINDOW_CLOSED:
    "The customer has not written in the last 24 hours, so WhatsApp does not allow a free message. Ask them to write first.",
  MEETING_PRICE_NOT_ALLOWED:
    "A price cannot be sent here. pi does not price; the quote does.",
  MEETING_NO_CONVERSATION: "This customer has no conversation to send to.",
  MEETING_SUMMARY_NOT_APPROVED: "Approve the summary on the Review tab first.",
};

export function MeetingShareSummary({ meeting }: { meeting: Detail }) {
  const approved = meeting.insights.find(
    (i) =>
      i.kind === "summary" &&
      (i.review_status === "approved" || i.review_status === "edited"),
  );
  const [text, setText] = useState("");
  const send = useScopedMutation(
    (words: string) => meetingIntelService.shareSummary(meeting.id, words),
    { toastErrors: false },
  );
  if (!approved || meeting.customer_id === null) return null;
  const shown = text || approved.text;
  const failure =
    send.error instanceof ApiError
      ? (REFUSED[send.error.code ?? ""] ?? "Could not send. Try again.")
      : send.error
        ? "Could not send. Try again."
        : "";
  return (
    <Card>
      <CardBody className="space-y-2">
        <h2 className="flex items-center gap-2 text-sm font-semibold">
          <Send className="size-4" aria-hidden /> Send the summary to the
          customer
        </h2>
        {send.data ? (
          <Notice tone="success">
            {send.data.again
              ? "This summary was already sent."
              : "Queued. It goes to the customer's WhatsApp now; the inbox shows if it was delivered."}
          </Notice>
        ) : (
          <>
            <div>
              <Label htmlFor="share-summary">What the customer will read</Label>
              <Textarea
                id="share-summary"
                rows={4}
                maxLength={900}
                value={shown}
                onChange={(e) => setText(e.target.value)}
              />
              <p className="mt-1 text-xs text-muted-foreground">
                Phone, card and ID numbers are taken out. Do not put a price
                here. Nothing is sent until you press the button.
              </p>
            </div>
            {failure && <Notice tone="warning">{failure}</Notice>}
            <Button
              loading={send.isPending}
              disabled={send.isPending || shown.trim().length === 0}
              onClick={() => send.mutate(shown.trim())}
            >
              <Send /> Send to customer
            </Button>
          </>
        )}
      </CardBody>
    </Card>
  );
}
