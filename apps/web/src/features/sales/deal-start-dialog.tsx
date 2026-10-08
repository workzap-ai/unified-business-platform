"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/overlays";
import { FormField } from "@/components/app/forms";
import { Notice } from "@/components/app/states";
import { useScopedMutation } from "@/hooks/use-scoped";
import { ApiError } from "@/services/api-client";
import { dealErrorMessage, dealService } from "./deal-service";

const startSchema = z.object({
  phone: z
    .string()
    .trim()
    .refine((v) => {
      const digits = v.replace(/\D/g, "").length;
      return digits >= 8 && digits <= 15;
    }, "Enter the WhatsApp number with country code"),
  name: z.string().trim().max(160, "Keep the name under 160 characters"),
  want: z.string().trim().max(4000, "Keep this under 4,000 characters"),
});
type StartValues = z.infer<typeof startSchema>;

const EMPTY: StartValues = { phone: "", name: "", want: "" };

/** A deal with someone who hasn't messaged yet, from their WhatsApp number. */
export function DealStartDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const router = useRouter();
  const form = useForm<StartValues>({
    resolver: zodResolver(startSchema),
    defaultValues: EMPTY,
  });
  const errors = form.formState.errors;

  const start = useScopedMutation(
    (v: StartValues) => {
      const firstLine = v.want.split("\n")[0]?.trim() ?? "";
      return dealService.start({
        phone: v.phone,
        name: v.name,
        title: firstLine.slice(0, 200),
        notes: v.want,
      });
    },
    {
      invalidate: [["leads"], ["pipeline"], ["deals"], ["customers"]],
      toastErrors: false,
      success: "Deal started",
      onSuccess: (r) => {
        onOpenChange(false);
        router.push(`/sales/leads/${r.lead_id}`);
      },
    },
  );

  useEffect(() => {
    if (open) {
      form.reset(EMPTY);
      start.reset();
    }
    // Reset only when the dialog opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const onSubmit = form.handleSubmit((values) =>
    start.mutate(values, {
      onError: (e) => {
        if (e instanceof ApiError && e.code === "PHONE_INVALID") {
          form.setError("phone", {
            type: "server",
            message: dealErrorMessage(e),
          });
        }
      },
    }),
  );

  const saving = start.isPending;
  const serverError =
    start.error &&
    !(start.error instanceof ApiError && start.error.code === "PHONE_INVALID")
      ? dealErrorMessage(start.error, "The deal couldn't be started.")
      : null;

  return (
    <Dialog open={open} onOpenChange={(next) => !saving && onOpenChange(next)}>
      <DialogContent size="md">
        <form
          onSubmit={onSubmit}
          noValidate
          className="flex min-h-0 flex-1 flex-col"
        >
          <DialogHeader
            title="New deal from WhatsApp number"
            description="For someone who hasn't messaged you yet. We find or add the customer by their number and open a lead."
          />
          <DialogBody className="space-y-4">
            {serverError && <Notice tone="danger">{serverError}</Notice>}
            <FormField
              label="WhatsApp number"
              htmlFor="deal-phone"
              required
              error={errors.phone}
              help="With country code, e.g. +92 300 1234567"
            >
              <Input
                id="deal-phone"
                type="tel"
                inputMode="tel"
                autoComplete="off"
                placeholder="+92 300 1234567"
                autoFocus
                aria-invalid={!!errors.phone || undefined}
                aria-describedby={
                  errors.phone ? "deal-phone-error" : "deal-phone-help"
                }
                {...form.register("phone")}
              />
            </FormField>
            <FormField
              label="Name"
              htmlFor="deal-name"
              optional
              error={errors.name}
            >
              <Input
                id="deal-name"
                autoComplete="off"
                placeholder="e.g. Sara Khan"
                aria-invalid={!!errors.name || undefined}
                {...form.register("name")}
              />
            </FormField>
            <FormField
              label="What they want"
              htmlFor="deal-want"
              optional
              error={errors.want}
              help="The first line becomes the deal's title."
            >
              <Textarea
                id="deal-want"
                rows={4}
                placeholder="e.g. Logo and brand kit for a new café"
                aria-invalid={!!errors.want || undefined}
                aria-describedby={
                  errors.want ? "deal-want-error" : "deal-want-help"
                }
                {...form.register("want")}
              />
            </FormField>
          </DialogBody>
          <DialogFooter>
            <Button
              type="button"
              variant="secondary"
              onClick={() => onOpenChange(false)}
              disabled={saving}
            >
              Cancel
            </Button>
            <Button type="submit" loading={saving} disabled={saving}>
              Start deal
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
