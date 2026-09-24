"use client";

import { useState } from "react";
import { ConfirmDialog } from "@/components/app/forms";
import { useScopedMutation } from "@/hooks/use-scoped";
import type { Lead, LeadStage } from "@/features/business/types";
import { salesService } from "../service";
import { STAGE_LABELS } from "../lib";

/**
 * Stage moves with one confirmation rule: "won" is terminal (no further transitions),
 * so it asks first. Other moves apply immediately and are reversible.
 */
export function useMoveLead(
  options: { onMoved?: (lead: Lead) => void; onSettled?: () => void } = {},
) {
  const [pending, setPending] = useState<{
    lead: Lead;
    stage: LeadStage;
  } | null>(null);
  const mutation = useScopedMutation(
    ({ lead, stage }: { lead: Lead; stage: LeadStage }) =>
      salesService.move(lead.id, stage),
    {
      invalidate: [["leads"], ["pipeline"]],
      success: (l) => `“${l.title}” moved to ${STAGE_LABELS[l.stage]}`,
      error: "The lead couldn't be moved. Refresh and try again.",
      onSuccess: (l) => {
        setPending(null);
        options.onMoved?.(l);
      },
    },
  );

  function move(lead: Lead, stage: LeadStage) {
    if (!lead.next_stages.includes(stage)) return;
    if (stage === "won") {
      setPending({ lead, stage });
      return;
    }
    mutation.mutate({ lead, stage }, { onSettled: options.onSettled });
  }

  const dialog = (
    <ConfirmDialog
      open={pending !== null}
      onOpenChange={(open) => {
        if (!open && !mutation.isPending) {
          setPending(null);
          options.onSettled?.();
        }
      }}
      title={pending ? `Mark “${pending.lead.title}” as won?` : "Mark as won?"}
      description="Winning closes the lead."
      consequences={[
        "Won is a final stage: the lead can't be moved again afterwards.",
        "Its value counts toward your win rate and closed revenue.",
      ]}
      confirmLabel="Mark as won"
      loading={mutation.isPending}
      onConfirm={() =>
        pending && mutation.mutate(pending, { onSettled: options.onSettled })
      }
    />
  );

  return {
    move,
    dialog,
    isPending: mutation.isPending,
    variables: mutation.variables,
  };
}
