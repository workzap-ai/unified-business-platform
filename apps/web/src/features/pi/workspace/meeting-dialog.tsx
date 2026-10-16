"use client";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/overlays";
import { useScopedMutation } from "@/hooks/use-scoped";
import { piRequestsService, type PiRequest } from "../requests-service";
import { MeetingFields, useMeetingForm } from "./meeting-fields";

/** "Arrange meeting": pick a time and how to meet; pi sends it to the customer. */
export function MeetingDialog({
  request,
  googleMeet,
  onClose,
  initialStartsAt,
}: {
  request: Pick<PiRequest, "id" | "question"> | null;
  googleMeet: boolean;
  onClose: () => void;
  /** Prefill the date and time ("YYYY-MM-DDTHH:MM", business time). */
  initialStartsAt?: string | null;
}) {
  const form = useMeetingForm({ googleMeet, initialStartsAt });
  const arrange = useScopedMutation(
    () => piRequestsService.arrangeMeeting(request!.id, form.values),
    {
      invalidate: [["pi", "requests"], ["pi", "meetings"], ["pi"]],
      success:
        "Meeting arranged. pi is sending the time and link to the customer.",
      onSuccess: () => onClose(),
    },
  );
  const ready = form.ready;
  return (
    <Dialog
      open={request !== null}
      onOpenChange={(next) => !next && !arrange.isPending && onClose()}
    >
      <DialogContent size="md">
        <DialogHeader
          title="Arrange the meeting"
          description="Pick a time and how you'll meet. pi sends it to the customer on WhatsApp, in their language."
        />
        <DialogBody className="space-y-3">
          {request && (
            <p className="rounded-lg bg-surface-muted px-3 py-2 text-[13px] whitespace-pre-wrap">
              {request.question}
            </p>
          )}
          <MeetingFields form={form} googleMeet={googleMeet} />
        </DialogBody>
        <DialogFooter>
          <Button
            variant="secondary"
            onClick={onClose}
            disabled={arrange.isPending}
          >
            Cancel
          </Button>
          <Button
            loading={arrange.isPending}
            disabled={!ready || arrange.isPending}
            onClick={() => arrange.mutate(undefined)}
          >
            Arrange and tell the customer
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
