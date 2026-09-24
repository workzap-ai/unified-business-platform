"use client";

import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { NativeSelect, Textarea } from "@/components/ui/input";
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader } from "@/components/ui/overlays";
import { ConfirmDialog, FormField } from "@/components/app/forms";
import { useScopedMutation } from "@/hooks/use-scoped";
import { piService } from "../service";
import type { HandoffReason } from "../types";
import { HANDOFF_REASONS, HANDOFF_REASON_LABELS, piKeys } from "./lib";

const INVALIDATE = [[...piKeys.all], ["navigation"]];

/** Conversation-level mutations shared by the thread header, composer and context panel. */
export function useConversationActions(id: string) {
  const takeover = useScopedMutation(() => piService.takeover(id), {
    invalidate: INVALIDATE,
    success: "You're handling this conversation. PI's automatic replies are paused.",
    error: "Couldn't take over the conversation. Please try again.",
  });
  const returnToAi = useScopedMutation(() => piService.returnToAi(id), {
    invalidate: INVALIDATE,
    success: "Returned to PI. Automatic replies resumed.",
    error: "Couldn't return the conversation to PI.",
  });
  const close = useScopedMutation(() => piService.closeConversation(id), {
    invalidate: INVALIDATE,
    success: "Conversation closed",
    error: "Couldn't close the conversation.",
  });
  return { takeover, returnToAi, close };
}

export function TakeoverDialog({
  open,
  onOpenChange,
  mode,
  customerName,
  loading,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mode: "takeover" | "return";
  customerName: string;
  loading: boolean;
  onConfirm: () => void;
}) {
  return mode === "takeover" ? (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Take over this conversation?"
      description={`You'll reply to ${customerName} yourself.`}
      consequences={[
        "PI stops sending automatic replies in this conversation.",
        "An open handoff for this conversation moves to In progress.",
        "Return the conversation to PI when you're done to resume automatic replies.",
      ]}
      confirmLabel="Take over"
      loading={loading}
      onConfirm={onConfirm}
    />
  ) : (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Return to PI?"
      description={`PI will resume answering ${customerName} automatically.`}
      consequences={[
        "PI replies to the customer's next message automatically.",
        "You can take over again at any time.",
        "Resolve any open handoff separately if the issue is settled.",
      ]}
      confirmLabel="Return to PI"
      loading={loading}
      onConfirm={onConfirm}
    />
  );
}

const handoffSchema = z.object({
  reason: z.enum(HANDOFF_REASONS as [HandoffReason, ...HandoffReason[]]),
  summary: z
    .string()
    .trim()
    .min(10, "Add a short summary (at least 10 characters) so the team knows what's needed.")
    .max(1000, "Keep the summary under 1,000 characters."),
});
type HandoffForm = z.infer<typeof handoffSchema>;

export function CreateHandoffDialog({
  conversationId,
  customerName,
  open,
  onOpenChange,
}: {
  conversationId: string;
  customerName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const form = useForm<HandoffForm>({ resolver: zodResolver(handoffSchema), defaultValues: { reason: "manual", summary: "" } });
  const create = useScopedMutation((input: HandoffForm) => piService.createHandoff(conversationId, input.reason, input.summary), {
    invalidate: INVALIDATE,
    success: "Handoff created. Your team can pick it up from the handoff queue.",
    error: "Couldn't create the handoff.",
    onSuccess: () => onOpenChange(false),
  });
  useEffect(() => {
    if (open) form.reset({ reason: "manual", summary: "" });
  }, [open, form]);
  const errors = form.formState.errors;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="md">
        <form onSubmit={form.handleSubmit((values) => create.mutate(values))} noValidate className="flex min-h-0 flex-col">
          <DialogHeader title="Create handoff" description={`Ask your team to follow up with ${customerName}.`} />
          <DialogBody className="space-y-4">
            <FormField label="Reason" htmlFor="handoff-reason" required error={errors.reason}>
              <NativeSelect id="handoff-reason" {...form.register("reason")} aria-invalid={Boolean(errors.reason)}>
                {HANDOFF_REASONS.map((r) => (
                  <option key={r} value={r}>
                    {HANDOFF_REASON_LABELS[r]}
                  </option>
                ))}
              </NativeSelect>
            </FormField>
            <FormField
              label="Summary"
              htmlFor="handoff-summary"
              required
              error={errors.summary}
              help="What the customer needs and anything the team should check first."
            >
              <Textarea
                id="handoff-summary"
                rows={4}
                maxLength={1000}
                placeholder="e.g. Customer wants wholesale pricing for 40 bags a month; needs approval."
                aria-invalid={Boolean(errors.summary)}
                aria-describedby={errors.summary ? "handoff-summary-error" : "handoff-summary-help"}
                {...form.register("summary")}
              />
            </FormField>
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="secondary" onClick={() => onOpenChange(false)} disabled={create.isPending}>
              Cancel
            </Button>
            <Button type="submit" loading={create.isPending}>
              Create handoff
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
