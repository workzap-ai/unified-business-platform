"use client";

import { useState } from "react";
import { toast } from "sonner";
import {
  CheckCircle2,
  Clock,
  Copy,
  ExternalLink,
  MessageCircle,
  Share2,
  type LucideIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/overlays";
import { Notice } from "@/components/app/states";
import { useScopedMutation } from "@/hooks/use-scoped";
import {
  dealErrorMessage,
  type DeliveryResult,
  type DeliveryState,
} from "./deal-service";

const DELIVERY_COPY: Record<
  DeliveryState,
  {
    tone: "success" | "info" | "warning";
    icon: LucideIcon;
    title: string;
    body: string;
  }
> = {
  sent: {
    tone: "success",
    icon: CheckCircle2,
    title: "Sent on WhatsApp",
    body: "The customer has the message and the link.",
  },
  waiting: {
    tone: "info",
    icon: Clock,
    title: "Waiting for the customer",
    body: "The customer was asked to reply on WhatsApp; the link goes out when they do.",
  },
  manual: {
    tone: "warning",
    icon: Share2,
    title: "Share the link yourself",
    body: "We couldn't message them first. Share the link yourself.",
  },
};

/** Short label for a document's delivery state, e.g. on a list row. */
export function deliveryLabel(delivery: string) {
  return delivery in DELIVERY_COPY
    ? DELIVERY_COPY[delivery as DeliveryState].title
    : delivery;
}

function copy(text: string) {
  void navigator.clipboard
    .writeText(text)
    .then(() => toast.success("Link copied"))
    .catch(() => toast.error("Couldn't copy. Select the link and copy it."));
}

/** What happened after "Send on WhatsApp": the delivery in plain words, plus the link. */
export function DealDeliveryDialog({
  result,
  noun,
  onOpenChange,
}: {
  result: DeliveryResult | null;
  /** "proposal" or "invoice". */
  noun: string;
  onOpenChange: (open: boolean) => void;
}) {
  const spec = result ? DELIVERY_COPY[result.delivery] : null;
  return (
    <Dialog open={result !== null} onOpenChange={onOpenChange}>
      <DialogContent size="md">
        <DialogHeader
          title={`Your ${noun} is on its way`}
          description={`The customer opens the ${noun} from this link.`}
        />
        {result && spec && (
          <DialogBody className="space-y-4">
            <Notice tone={spec.tone} icon={spec.icon} title={spec.title}>
              {spec.body}
            </Notice>
            <div className="space-y-1.5">
              <p className="text-[13px] font-medium">Link</p>
              <div className="flex items-center gap-2">
                <code className="min-w-0 flex-1 truncate rounded-md border border-border bg-surface-muted px-2.5 py-1.5 text-xs">
                  {result.link}
                </code>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => copy(result.link)}
                >
                  <Copy aria-hidden="true" /> Copy link
                </Button>
              </div>
            </div>
            {result.message && (
              <div className="space-y-1.5">
                <p className="text-[13px] font-medium">Message</p>
                <p className="rounded-md border border-border bg-surface-muted px-2.5 py-2 text-[13px] whitespace-pre-line text-foreground-secondary">
                  {result.message}
                </p>
              </div>
            )}
          </DialogBody>
        )}
        <DialogFooter>
          {result?.share && (
            <Button variant="secondary" asChild>
              <a href={result.share} target="_blank" rel="noopener noreferrer">
                <ExternalLink aria-hidden="true" /> Open in WhatsApp
              </a>
            </Button>
          )}
          <Button onClick={() => onOpenChange(false)}>Done</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/**
 * "Send on WhatsApp" for a proposal or invoice: runs the send, maps deal errors to plain
 * words, and shows the result dialog.
 */
export function SendOnWhatsAppButton({
  send,
  noun,
  resend = false,
  invalidate,
  size = "sm",
  variant = "default",
}: {
  send: () => Promise<DeliveryResult>;
  noun: string;
  resend?: boolean;
  invalidate: unknown[][];
  size?: "sm" | "default";
  variant?: "default" | "secondary";
}) {
  const [result, setResult] = useState<DeliveryResult | null>(null);
  const mutation = useScopedMutation(() => send(), {
    invalidate,
    toastErrors: false,
    onSuccess: (r) => setResult(r),
  });
  return (
    <>
      <Button
        size={size}
        variant={variant}
        loading={mutation.isPending}
        disabled={mutation.isPending}
        onClick={() =>
          mutation.mutate(undefined, {
            onError: (e) =>
              toast.error(
                dealErrorMessage(
                  e,
                  `The ${noun} couldn't be sent. Please try again.`,
                ),
              ),
          })
        }
      >
        <MessageCircle /> {resend ? "Resend on WhatsApp" : "Send on WhatsApp"}
      </Button>
      <DealDeliveryDialog
        result={result}
        noun={noun}
        onOpenChange={(open) => !open && setResult(null)}
      />
    </>
  );
}
