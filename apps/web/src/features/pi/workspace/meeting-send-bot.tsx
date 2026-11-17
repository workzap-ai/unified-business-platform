"use client";

import { useState } from "react";
import { Bot } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox, Label } from "@/components/ui/controls";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/overlays";
import { Notice } from "@/components/app/states";
import { useScopedMutation } from "@/hooks/use-scoped";
import { ApiError } from "@/services/api-client";
import { meetingIntelService } from "../meeting-intel-service";

/**
 * Send pi to a Zoom, Google Meet or Teams call: paste the link, confirm that everyone will be told,
 * press the button. pi joins as "pi (AI) - Workzap notetaker" and listens. The link is sent to the
 * bot service and is not kept; only its host is.
 */
const REFUSED: Record<string, string> = {
  MEETING_BOT_OFF:
    "Sending pi to a call is not switched on for this workspace yet.",
  MEETING_BOT_UNCONFIGURED:
    "The meeting bot service is not set up yet. Ask the platform owner to finish its setup.",
  MEETING_LINK_INVALID: "Paste a Zoom, Google Meet or Teams meeting link.",
  MEETING_BOT_ALREADY_IN: "pi is already in, or on its way to, this call.",
  MEETING_CONSENT_REQUIRED:
    "Confirm that everyone in the call will be told first.",
  BOT_PROVIDER_KEY_REJECTED:
    "The meeting bot service did not accept our key. Ask the platform owner to check it.",
  BOT_PROVIDER_BUSY: "The meeting bot service is busy. Try again shortly.",
  BOT_PROVIDER_UNREACHABLE:
    "The meeting bot service could not be reached. Try again in a moment.",
};

export function SendBotDialog({
  open,
  onClose,
  onSent,
}: {
  open: boolean;
  onClose: () => void;
  onSent: (meetingId: string) => void;
}) {
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [agreed, setAgreed] = useState(false);
  const send = useScopedMutation(meetingIntelService.sendBot, {
    invalidate: [["pi", "meeting-intel"]],
    toastErrors: false,
    onSuccess: (out) => {
      setUrl("");
      setTitle("");
      setAgreed(false);
      onSent(out.meeting.id);
    },
  });
  const failure =
    send.error instanceof ApiError
      ? (REFUSED[send.error.code ?? ""] ?? "Could not send pi. Try again.")
      : send.error
        ? "Could not send pi. Try again."
        : "";
  const ready = url.trim().length >= 10 && agreed && !send.isPending;
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent size="md">
        <DialogHeader
          title="Send pi to a call"
          description="pi joins your Zoom, Google Meet or Teams call as an AI notetaker, listens, and writes the transcript."
        />
        <DialogBody className="space-y-3">
          <div>
            <Label htmlFor="bot-url">Meeting link</Label>
            <Input
              id="bot-url"
              inputMode="url"
              autoComplete="off"
              value={url}
              maxLength={600}
              disabled={send.isPending}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://zoom.us/j/… or https://meet.google.com/…"
            />
          </div>
          <div>
            <Label htmlFor="bot-title">Title (optional)</Label>
            <Input
              id="bot-title"
              value={title}
              maxLength={200}
              disabled={send.isPending}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="So you can find it later"
            />
          </div>
          <div className="space-y-1.5 rounded-lg border border-border bg-surface-muted p-3 text-xs text-muted-foreground">
            <p className="flex items-center gap-1.5 font-medium text-foreground">
              <Bot className="size-3.5" aria-hidden /> What everyone in the call
              will see
            </p>
            <p>
              A participant named &ldquo;pi (AI) - Workzap notetaker&rdquo;. In
              Zoom and Teams the host may need to let it in from the waiting
              room. The host can remove it at any time.
            </p>
          </div>
          <label className="flex items-start gap-2 text-sm">
            <Checkbox
              checked={agreed}
              disabled={send.isPending}
              onCheckedChange={(v) => setAgreed(v === true)}
            />
            <span>
              Everyone in this call knows an AI notetaker is joining and that
              the call is transcribed.
            </span>
          </label>
          {failure && <Notice tone="danger">{failure}</Notice>}
        </DialogBody>
        <DialogFooter>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={!ready}
            loading={send.isPending}
            onClick={() =>
              send.mutate({
                meeting_url: url.trim(),
                title: title.trim(),
                consent: agreed,
              })
            }
          >
            <Bot /> Send pi
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
