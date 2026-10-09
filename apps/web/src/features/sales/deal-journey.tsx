"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  ArrowRight,
  Bot,
  Check,
  Circle,
  Compass,
  Pencil,
  Route,
  Sparkles,
} from "lucide-react";
import { formatDate, formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge, Card, CardBody, CardHeader } from "@/components/ui/display";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import { ApiError } from "@/services/api-client";
import { SendOnWhatsAppButton } from "./deal-delivery-dialog";
import {
  dealErrorMessage,
  dealService,
  type DealJourney,
  type JourneyStep,
} from "./deal-service";

const INVALIDATE = [
  ["deals"],
  ["leads"],
  ["quotes"],
  ["invoices"],
  ["pipeline"],
];

/** One deal's journey and what to do next. Both cards share one query. */
export function useDealJourney(leadId: string, enabled = true) {
  return useScopedQuery(
    ["deals", "journey", leadId],
    () => dealService.journey(leadId),
    {
      enabled,
      retry: (count, e) =>
        !(e instanceof ApiError && e.status < 500) && count < 2,
    },
  );
}

/** "Next step": the one thing to do now, with the button that does it. */
export function NextStepCard({
  journey,
  onEdit,
}: {
  journey: DealJourney;
  onEdit: () => void;
}) {
  const { can } = useSession();
  const router = useRouter();
  const next = journey.next;
  const proposal = useScopedMutation(
    () => dealService.proposalFromLead(journey.lead_id),
    {
      invalidate: INVALIDATE,
      toastErrors: false,
      success: (r) => `Proposal ${r.number} created. Add the prices.`,
      onSuccess: (r) => router.push(`/quotes/${r.quote_id}/edit`),
    },
  );

  let button: React.ReactNode = null;
  if (next.action === "proposal_from_brief" && can("quotes.write")) {
    button = (
      <Button
        size="sm"
        variant={next.auto ? "secondary" : "default"}
        loading={proposal.isPending}
        disabled={proposal.isPending}
        onClick={() =>
          proposal.mutate(undefined, {
            onError: (e) =>
              toast.error(
                dealErrorMessage(e, "The proposal couldn't be created."),
              ),
          })
        }
      >
        <Sparkles /> {next.auto ? "Make it now" : "Proposal from brief"}
      </Button>
    );
  } else if (
    next.action === "send_proposal" &&
    journey.quote_id &&
    can("quotes.write")
  ) {
    const quoteId = journey.quote_id;
    button = (
      <SendOnWhatsAppButton
        noun="proposal"
        resend={next.auto}
        variant={next.auto ? "secondary" : "default"}
        send={() => dealService.sendQuote(quoteId)}
        invalidate={INVALIDATE}
      />
    );
  } else if (
    next.action === "send_invoice" &&
    journey.invoice_id &&
    can("billing.write")
  ) {
    const invoiceId = journey.invoice_id;
    button = (
      <SendOnWhatsAppButton
        noun="invoice"
        resend
        variant="secondary"
        send={() => dealService.sendInvoice(invoiceId)}
        invalidate={INVALIDATE}
      />
    );
  } else if (next.action === "edit" && can("sales.write")) {
    button = (
      <Button size="sm" onClick={onEdit}>
        <Pencil /> Edit lead
      </Button>
    );
  }

  return (
    <Card>
      <CardHeader
        title="Next step"
        icon={<Compass />}
        description="What this deal needs now"
      />
      <CardBody className="space-y-3">
        <div>
          <p className="flex items-center gap-1.5 text-[14px] font-semibold">
            {next.title}
            {next.auto && (
              <Badge tone="pi">
                <Bot aria-hidden="true" /> pi does this
              </Badge>
            )}
          </p>
          <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">
            {next.detail}
          </p>
        </div>
        {(button || next.href) && (
          <div className="flex flex-wrap gap-2">
            {button}
            {next.href && (
              <Button
                size="sm"
                variant={button ? "secondary" : "default"}
                asChild
              >
                <Link href={next.href}>
                  Open <ArrowRight />
                </Link>
              </Button>
            )}
          </div>
        )}
      </CardBody>
    </Card>
  );
}

const REMINDERS: Record<string, string> = {
  proposal_unopened: "proposal not opened yet",
  proposal_unanswered: "proposal opened, no answer yet",
  invoice_due: "invoice due tomorrow",
  invoice_overdue: "invoice overdue",
};

/** "Journey": every step from the enquiry to the payment, with when it happened. */
export function JourneyCard({ journey }: { journey: DealJourney }) {
  const current = journey.steps.findIndex((s) => !s.done);
  const lost = journey.stage === "lost";
  return (
    <Card>
      <CardHeader
        title="Journey"
        icon={<Route />}
        description="From the first message to the payment"
      />
      <CardBody>
        <ol className="space-y-0">
          {journey.steps.map((step, i) => (
            <JourneyRow
              key={step.key}
              step={step}
              current={!lost && i === current}
              last={i === journey.steps.length - 1}
            />
          ))}
        </ol>
        {journey.reminder && (
          <p className="mt-3 flex items-center gap-1.5 border-t border-border pt-3 text-xs text-muted-foreground">
            <Bot className="size-3.5 text-pi" aria-hidden="true" />
            Next reminder from pi:{" "}
            {REMINDERS[journey.reminder.kind] ?? "a follow-up"},{" "}
            {journey.reminder.at.length === 10
              ? formatDate(journey.reminder.at)
              : formatDateTime(journey.reminder.at)}
          </p>
        )}
      </CardBody>
    </Card>
  );
}

function JourneyRow({
  step,
  current,
  last,
}: {
  step: JourneyStep;
  current: boolean;
  last: boolean;
}) {
  return (
    <li className="relative flex gap-3 pb-3 last:pb-0">
      {!last && (
        <span
          aria-hidden="true"
          className={cn(
            "absolute top-6 left-[11px] h-[calc(100%-1.25rem)] w-px",
            step.done ? "bg-success/50" : "bg-border",
          )}
        />
      )}
      <span
        aria-hidden="true"
        className={cn(
          "relative z-10 mt-0.5 flex size-[22px] shrink-0 items-center justify-center rounded-full border",
          step.done
            ? "border-transparent bg-success-soft text-success"
            : current
              ? "border-primary bg-primary-soft text-primary"
              : "border-border bg-surface text-muted-foreground",
        )}
      >
        {step.done ? (
          <Check className="size-3.5" />
        ) : (
          <Circle className={cn("size-2", current && "fill-current")} />
        )}
      </span>
      <div className="min-w-0 flex-1">
        <p
          className={cn(
            "text-[13px]",
            step.done || current ? "font-medium" : "text-muted-foreground",
          )}
        >
          {step.label}
          <span className="sr-only">
            {step.done ? " (done)" : current ? " (now)" : " (later)"}
          </span>
        </p>
        {(step.detail || step.at) && (
          <p className="mt-0.5 text-xs break-words text-muted-foreground">
            {[step.detail, step.at ? formatDateTime(step.at) : ""]
              .filter(Boolean)
              .join(" · ")}
          </p>
        )}
      </div>
    </li>
  );
}
