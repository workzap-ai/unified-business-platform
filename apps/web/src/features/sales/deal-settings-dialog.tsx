"use client";

import { useEffect } from "react";
import { Controller, useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/display";
import { Label, Switch } from "@/components/ui/controls";
import { Input, NativeSelect } from "@/components/ui/input";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/overlays";
import { FormField } from "@/components/app/forms";
import { ErrorState, Notice } from "@/components/app/states";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import {
  DEAL_PAYMENT_METHOD_LABELS,
  DEAL_PAYMENT_METHODS,
  dealErrorMessage,
  dealService,
  type DealSettings,
  type DealSettingsInput,
} from "./deal-service";

const settingsSchema = z
  .object({
    auto_proposal: z.boolean(),
    auto_followups: z.boolean(),
    auto_order: z.boolean(),
    auto_invoice: z.boolean(),
    auto_payment_request: z.boolean(),
    thank_you_on_paid: z.boolean(),
    payment_method: z.enum(DEAL_PAYMENT_METHODS),
    template_name: z
      .string()
      .trim()
      .max(512, "Keep the name under 512 characters")
      .regex(
        /^[a-z0-9_]*$/,
        "Use the template's exact name: lowercase letters, numbers and _",
      ),
    template_language: z
      .string()
      .trim()
      .regex(
        /^([a-z]{2,3}(_[A-Z]{2})?)?$/,
        "Use a language code like en or en_US",
      ),
  })
  .superRefine((v, ctx) => {
    if (v.template_name && !v.template_language)
      ctx.addIssue({
        code: "custom",
        path: ["template_language"],
        message: "Give the template's language too",
      });
    if (v.template_language && !v.template_name)
      ctx.addIssue({
        code: "custom",
        path: ["template_name"],
        message: "Give the template's name too",
      });
  });
type SettingsValues = z.infer<typeof settingsSchema>;

const TOGGLES: {
  key:
    | "auto_proposal"
    | "auto_followups"
    | "auto_order"
    | "auto_invoice"
    | "auto_payment_request"
    | "thank_you_on_paid";
  label: string;
  help: string;
  /** Only runs when this earlier step is on. */
  after?: "auto_order";
}[] = [
  {
    key: "auto_proposal",
    label: "Make the proposal when the customer confirms the brief",
    help: "pi makes it with your catalog prices and sends it on WhatsApp. Lines without a catalog price wait for you.",
  },
  {
    key: "auto_followups",
    label: "Remind the customer when a deal goes quiet",
    help: "Proposal unopened after 2 days or unanswered after 3; invoice due tomorrow or 3 days overdue. Once each, on WhatsApp.",
  },
  {
    key: "auto_order",
    label: "Confirm the order when the customer accepts",
    help: "Accepting the proposal on WhatsApp creates and confirms the order.",
  },
  {
    key: "auto_invoice",
    label: "Issue the invoice",
    help: "The confirmed order is invoiced straight away.",
    after: "auto_order",
  },
  {
    key: "auto_payment_request",
    label: "Send the payment link on WhatsApp",
    help: "The customer gets the invoice and a way to pay.",
    after: "auto_order",
  },
  {
    key: "thank_you_on_paid",
    label: "Thank them when paid",
    help: "A short thank-you when the invoice is paid in full.",
  },
];

function toForm(s: DealSettings): SettingsValues {
  return {
    auto_proposal: s.auto_proposal,
    auto_followups: s.auto_followups,
    auto_order: s.auto_order,
    auto_invoice: s.auto_invoice,
    auto_payment_request: s.auto_payment_request,
    thank_you_on_paid: s.thank_you_on_paid,
    payment_method: s.payment_method,
    template_name: s.template_name,
    template_language: s.template_language,
  };
}

/** The workspace's deal automation: what happens after a customer accepts or pays. */
export function DealSettingsDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { can } = useSession();
  const canWrite = can("sales.write");
  const query = useScopedQuery(
    ["deals", "settings"],
    () => dealService.settings(),
    { enabled: open },
  );
  const form = useForm<SettingsValues>({
    resolver: zodResolver(settingsSchema),
    defaultValues: {
      auto_proposal: true,
      auto_followups: true,
      auto_order: true,
      auto_invoice: true,
      auto_payment_request: true,
      thank_you_on_paid: true,
      payment_method: "auto",
      template_name: "",
      template_language: "",
    },
  });
  const errors = form.formState.errors;

  useEffect(() => {
    if (open && query.data) form.reset(toForm(query.data));
    // Load the saved settings each time the dialog opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, query.data]);

  const save = useScopedMutation(
    (v: SettingsValues) => dealService.saveSettings(v as DealSettingsInput),
    {
      invalidate: [["deals", "settings"]],
      toastErrors: false,
      success: "Deal automation saved",
      onSuccess: () => onOpenChange(false),
    },
  );
  useEffect(() => {
    if (open) save.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const onSubmit = form.handleSubmit((v) => save.mutate(v));
  const autoOrder = useWatch({ control: form.control, name: "auto_order" });
  const saving = save.isPending;

  return (
    <Dialog open={open} onOpenChange={(next) => !saving && onOpenChange(next)}>
      <DialogContent size="md">
        <form
          onSubmit={onSubmit}
          noValidate
          className="flex min-h-0 flex-1 flex-col"
        >
          <DialogHeader
            title="Deal automation"
            description="What pi does on WhatsApp once a customer answers your proposal."
          />
          <DialogBody className="space-y-5">
            {query.isError ? (
              <ErrorState
                error={query.error}
                onRetry={() => void query.refetch()}
              />
            ) : !query.data ? (
              <div className="space-y-3" aria-busy="true">
                <Skeleton className="h-12 rounded-lg" />
                <Skeleton className="h-12 rounded-lg" />
                <Skeleton className="h-12 rounded-lg" />
              </div>
            ) : (
              <>
                {save.error ? (
                  <Notice tone="danger">
                    {dealErrorMessage(
                      save.error,
                      "The settings couldn't be saved.",
                    )}
                  </Notice>
                ) : null}
                <fieldset className="space-y-3" disabled={!canWrite}>
                  <legend className="sr-only">Automatic steps</legend>
                  {TOGGLES.map((t) => {
                    const blocked = t.after ? !autoOrder : false;
                    const id = `deal-${t.key}`;
                    return (
                      <div
                        key={t.key}
                        className={
                          t.after
                            ? "flex items-start justify-between gap-4 border-l-2 border-border pl-3"
                            : "flex items-start justify-between gap-4"
                        }
                      >
                        <div className="min-w-0">
                          <Label htmlFor={id}>{t.label}</Label>
                          <p
                            id={`${id}-help`}
                            className="mt-0.5 text-xs text-muted-foreground"
                          >
                            {blocked
                              ? "Runs only when the order is confirmed automatically."
                              : t.help}
                          </p>
                        </div>
                        <Controller
                          control={form.control}
                          name={t.key}
                          render={({ field }) => (
                            <Switch
                              id={id}
                              checked={field.value}
                              onCheckedChange={field.onChange}
                              disabled={!canWrite || blocked}
                              aria-describedby={`${id}-help`}
                            />
                          )}
                        />
                      </div>
                    );
                  })}
                </fieldset>

                <FormField
                  label="Payment method"
                  htmlFor="deal-payment-method"
                  error={errors.payment_method}
                  help="Which way to pay goes in the payment link."
                >
                  <NativeSelect
                    id="deal-payment-method"
                    disabled={!canWrite}
                    aria-describedby="deal-payment-method-help"
                    {...form.register("payment_method")}
                  >
                    {DEAL_PAYMENT_METHODS.map((m) => (
                      <option key={m} value={m}>
                        {DEAL_PAYMENT_METHOD_LABELS[m]}
                      </option>
                    ))}
                  </NativeSelect>
                </FormField>

                <fieldset className="space-y-3" disabled={!canWrite}>
                  <legend className="text-[13px] font-medium">
                    WhatsApp template for customers outside 24 hours{" "}
                    <span className="font-normal text-muted-foreground">
                      (optional)
                    </span>
                  </legend>
                  <p className="text-xs text-muted-foreground">
                    WhatsApp only lets you message first with an approved
                    template. It must be an approved template with no variables,
                    e.g. &ldquo;Your document is ready, reply to this message to
                    see it&rdquo;. Without one, you share the link yourself.
                  </p>
                  <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_140px]">
                    <FormField
                      label="Template name"
                      htmlFor="deal-template-name"
                      error={errors.template_name}
                    >
                      <Input
                        id="deal-template-name"
                        autoComplete="off"
                        spellCheck={false}
                        placeholder="document_ready"
                        aria-invalid={!!errors.template_name || undefined}
                        {...form.register("template_name")}
                      />
                    </FormField>
                    <FormField
                      label="Language"
                      htmlFor="deal-template-language"
                      error={errors.template_language}
                    >
                      <Input
                        id="deal-template-language"
                        autoComplete="off"
                        spellCheck={false}
                        placeholder="en_US"
                        aria-invalid={!!errors.template_language || undefined}
                        {...form.register("template_language")}
                      />
                    </FormField>
                  </div>
                </fieldset>
              </>
            )}
          </DialogBody>
          <DialogFooter>
            <Button
              type="button"
              variant="secondary"
              onClick={() => onOpenChange(false)}
              disabled={saving}
            >
              {canWrite ? "Cancel" : "Close"}
            </Button>
            {canWrite && (
              <Button
                type="submit"
                loading={saving}
                disabled={saving || !query.data || !form.formState.isDirty}
              >
                Save
              </Button>
            )}
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
