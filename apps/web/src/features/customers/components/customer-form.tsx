"use client";

import { Controller, type UseFormReturn } from "react-hook-form";
import { z } from "zod";
import { Input } from "@/components/ui/input";
import { FormField, FormSection } from "@/components/app/forms";
import { ApiError, errorMessage } from "@/services/api-client";
import type { Customer, CustomerInput } from "@/features/business/types";
import { normalizePhone } from "../lib";
import { TagInput } from "./tag-input";

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const E164 = /^\+[1-9]\d{6,14}$/;

export const customerFormSchema = z.object({
  name: z
    .string()
    .trim()
    .min(1, "Enter the customer's name")
    .max(200, "Keep the name under 200 characters"),
  email: z
    .string()
    .trim()
    .max(254, "Email is too long")
    .refine((v) => !v || EMAIL.test(v), "Enter a valid email address"),
  phone: z
    .string()
    .trim()
    .refine(
      (v) => !v || E164.test(normalizePhone(v)),
      "Use international format, e.g. +92 300 1234567",
    ),
  company: z.string().trim().max(200, "Keep the company under 200 characters"),
  tags: z.array(z.string()).max(20, "Use at most 20 tags"),
});

export type CustomerFormValues = z.infer<typeof customerFormSchema>;

export const emptyCustomerForm: CustomerFormValues = {
  name: "",
  email: "",
  phone: "",
  company: "",
  tags: [],
};

export function customerToForm(c: Customer): CustomerFormValues {
  return {
    name: c.name,
    email: c.email ?? "",
    phone: c.phone ?? "",
    company: c.company ?? "",
    tags: c.tags,
  };
}

export function formToInput(values: CustomerFormValues): CustomerInput {
  return {
    name: values.name.trim(),
    email: values.email.trim() || null,
    phone: values.phone.trim() ? normalizePhone(values.phone) : null,
    company: values.company.trim() || null,
    tags: values.tags,
  };
}

/**
 * Maps server errors onto fields: duplicate phone (409) goes to the phone field, 422
 * field errors to their fields. Returns true if something was shown inline.
 */
export function applyCustomerServerError(
  form: UseFormReturn<CustomerFormValues>,
  error: unknown,
): boolean {
  if (!(error instanceof ApiError)) return false;
  let shown = false;
  if (error.status === 409) {
    form.setError("phone", {
      type: "server",
      message: errorMessage(
        error,
        "A customer with this phone number already exists",
      ),
    });
    form.setFocus("phone");
    return true;
  }
  for (const [field, message] of Object.entries(error.fields)) {
    if (field in emptyCustomerForm) {
      form.setError(field as keyof CustomerFormValues, {
        type: "server",
        message,
      });
      shown = true;
    }
  }
  return shown;
}

function ContactFields({
  form,
  idPrefix,
}: {
  form: UseFormReturn<CustomerFormValues>;
  idPrefix: string;
}) {
  const { register, formState } = form;
  const e = formState.errors;
  return (
    <>
      <FormField
        label="Full name"
        htmlFor={`${idPrefix}-name`}
        required
        error={e.name}
      >
        <Input
          id={`${idPrefix}-name`}
          autoComplete="off"
          aria-invalid={!!e.name || undefined}
          aria-describedby={e.name ? `${idPrefix}-name-error` : undefined}
          {...register("name")}
        />
      </FormField>
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField
          label="Email"
          htmlFor={`${idPrefix}-email`}
          optional
          error={e.email}
        >
          <Input
            id={`${idPrefix}-email`}
            type="email"
            autoComplete="off"
            aria-invalid={!!e.email || undefined}
            aria-describedby={e.email ? `${idPrefix}-email-error` : undefined}
            {...register("email")}
          />
        </FormField>
        <FormField
          label="Phone"
          htmlFor={`${idPrefix}-phone`}
          optional
          error={e.phone}
          help="International format with country code, e.g. +92 300 1234567. Used to match WhatsApp chats."
        >
          <Input
            id={`${idPrefix}-phone`}
            type="tel"
            inputMode="tel"
            placeholder="+92 300 1234567"
            autoComplete="off"
            aria-invalid={!!e.phone || undefined}
            aria-describedby={
              e.phone ? `${idPrefix}-phone-error` : `${idPrefix}-phone-help`
            }
            {...register("phone")}
          />
        </FormField>
      </div>
    </>
  );
}

function CompanyField({
  form,
  idPrefix,
}: {
  form: UseFormReturn<CustomerFormValues>;
  idPrefix: string;
}) {
  const e = form.formState.errors;
  return (
    <FormField
      label="Company"
      htmlFor={`${idPrefix}-company`}
      optional
      error={e.company}
    >
      <Input
        id={`${idPrefix}-company`}
        autoComplete="off"
        aria-invalid={!!e.company || undefined}
        {...form.register("company")}
      />
    </FormField>
  );
}

function TagsField({
  form,
  idPrefix,
}: {
  form: UseFormReturn<CustomerFormValues>;
  idPrefix: string;
}) {
  const e = form.formState.errors;
  return (
    <FormField
      label="Tags"
      htmlFor={`${idPrefix}-tags`}
      optional
      error={e.tags?.message}
      help="Press Enter to add. Tags power segments, e.g. vip or whatsapp."
    >
      <Controller
        control={form.control}
        name="tags"
        render={({ field }) => (
          <TagInput
            id={`${idPrefix}-tags`}
            value={field.value}
            onChange={field.onChange}
            invalid={!!e.tags}
            describedBy={`${idPrefix}-tags-help`}
          />
        )}
      />
    </FormField>
  );
}

/** Full-page layout: one FormSection per group. */
export function CustomerFormSections({
  form,
}: {
  form: UseFormReturn<CustomerFormValues>;
}) {
  return (
    <>
      <FormSection
        title="Contact"
        description="How your team and PI reach this customer."
      >
        <ContactFields form={form} idPrefix="customer" />
      </FormSection>
      <FormSection
        title="Organization"
        description="The business this customer buys for, if any."
      >
        <CompanyField form={form} idPrefix="customer" />
      </FormSection>
      <FormSection
        title="Tags"
        description="Group customers into segments and saved views."
      >
        <TagsField form={form} idPrefix="customer" />
      </FormSection>
    </>
  );
}

/** Compact stacked layout for dialogs. */
export function CustomerFormStack({
  form,
}: {
  form: UseFormReturn<CustomerFormValues>;
}) {
  return (
    <div className="space-y-4">
      <ContactFields form={form} idPrefix="edit-customer" />
      <CompanyField form={form} idPrefix="edit-customer" />
      <TagsField form={form} idPrefix="edit-customer" />
    </div>
  );
}
