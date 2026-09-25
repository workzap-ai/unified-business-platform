"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { CheckCircle2, Clock, Lock, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import { Label, RadioGroup, RadioGroupItem } from "@/components/ui/controls";
import { Skeleton } from "@/components/ui/display";
import { FormField } from "@/components/app/forms";
import { InlineError, Notice } from "@/components/app/states";
import { ApiError, errorMessage } from "@/services/api-client";
import {
  JOB_TYPES,
  onboardingService,
  type PublicForm,
  type SubmissionDetails,
} from "./onboarding-service";

const required = (label: string) => z.string().trim().min(1, `Enter ${label}`);
const phone = z
  .string()
  .trim()
  .min(1, "Enter a phone number")
  .regex(/^[+0-9][0-9 ()-]{6,20}$/, "Enter a valid phone number");

const schema = z.object({
  full_name: required("your full name as per CNIC").min(2).max(160),
  father_name: required("your father's name").min(2).max(160),
  cnic: z
    .string()
    .trim()
    .regex(/^\d{5}-?\d{7}-?\d$/, "Enter the 13-digit CNIC as 12345-1234567-1"),
  email: z.string().trim().email("Enter a valid email address"),
  designation: required("your designation").min(2).max(120),
  gender: z.enum(["male", "female"]).optional(),
  date_of_joining: required("your date of joining"),
  date_of_birth: required("your date of birth"),
  job_type: z.enum(["onsite", "hybrid", "remote", "freelancer"], {
    message: "Choose a job type",
  }),
  contact_number: phone,
  emergency_1_name: required("a name").max(160),
  emergency_1_phone: phone,
  emergency_2_name: required("a name").max(160),
  emergency_2_phone: phone,
  address: required("your current address")
    .min(5, "Add your full address with a nearby landmark")
    .max(500),
  account_title: z.string().trim().max(80).optional(),
  bank_name: z.string().trim().max(80).optional(),
  bank_account_number: z
    .string()
    .trim()
    .max(40)
    .regex(/^[A-Za-z0-9 -]*$/, "Use letters and digits only")
    .optional(),
  ntn: z.string().trim().max(24).optional(),
  professional_reference: z.string().trim().max(500).optional(),
  about: z.string().trim().max(2000).optional(),
});
type Values = z.infer<typeof schema>;

function toSubmission(v: Values): SubmissionDetails {
  const blank = (s?: string) => (s && s.trim() ? s.trim() : null);
  return {
    full_name: v.full_name,
    father_name: v.father_name,
    cnic: v.cnic,
    email: v.email,
    designation: v.designation,
    gender: v.gender ?? null,
    date_of_joining: v.date_of_joining,
    date_of_birth: v.date_of_birth,
    job_type: v.job_type,
    contact_number: v.contact_number,
    emergency_contact_1: {
      name: v.emergency_1_name,
      phone: v.emergency_1_phone,
    },
    emergency_contact_2: {
      name: v.emergency_2_name,
      phone: v.emergency_2_phone,
    },
    address: v.address,
    account_title: blank(v.account_title),
    bank_name: blank(v.bank_name),
    bank_account_number: blank(v.bank_account_number),
    ntn: blank(v.ntn),
    professional_reference: blank(v.professional_reference),
    about: blank(v.about),
  };
}

// Server field paths -> form fields (validation details name the failing field only).
const SERVER_FIELDS: Record<string, keyof Values> = {
  "emergency_contact_1.name": "emergency_1_name",
  "emergency_contact_1.phone": "emergency_1_phone",
  "emergency_contact_2.name": "emergency_2_name",
  "emergency_contact_2.phone": "emergency_2_phone",
};

export function OnboardingFormPage({ token }: { token: string }) {
  const query = useQuery({
    queryKey: ["public-onboarding", token],
    queryFn: () => onboardingService.publicForm(token),
    retry: false,
  });
  const [done, setDone] = useState<PublicForm | null>(null);

  if (query.isPending) {
    return (
      <Shell>
        <Skeleton className="h-7 w-64" />
        <Skeleton className="mt-3 h-4 w-96 max-w-full" />
        <Skeleton className="mt-8 h-[640px] rounded-xl" />
      </Shell>
    );
  }
  if (query.isError) {
    const notFound =
      query.error instanceof ApiError && query.error.status === 404;
    return (
      <Shell>
        <Notice
          tone={notFound ? "neutral" : "danger"}
          title={
            notFound ? "This link isn't valid" : "We couldn't load the form"
          }
        >
          {notFound
            ? "Check that you opened the complete link, or ask HR to send you a new one."
            : errorMessage(query.error)}
        </Notice>
      </Shell>
    );
  }
  const state = done ?? query.data;
  if (state.status !== "open") return <Closed state={state} />;
  return (
    <Shell organization={state.organization_name}>
      <Form token={token} form={state} onDone={setDone} />
    </Shell>
  );
}

function Shell({
  children,
  organization,
}: {
  children: React.ReactNode;
  organization?: string;
}) {
  return (
    <div className="min-h-dvh bg-background">
      <header className="border-b border-border bg-surface">
        <div className="mx-auto flex max-w-3xl items-center gap-2 px-4 py-4 sm:px-6">
          <ShieldCheck className="size-5 text-primary" aria-hidden="true" />
          <p className="text-sm font-semibold">
            {organization ? `${organization} · ` : ""}New employee details
          </p>
        </div>
      </header>
      <main className="mx-auto max-w-3xl px-4 py-6 sm:px-6 sm:py-10">
        {children}
      </main>
    </div>
  );
}

function Closed({ state }: { state: PublicForm }) {
  const content = {
    submitted: {
      icon: CheckCircle2,
      title: "Thank you, your details were received",
      body: "HR will review them and get in touch. You can close this page.",
    },
    expired: {
      icon: Clock,
      title: "This link has expired",
      body: "Ask HR to send you a new onboarding link.",
    },
    closed: {
      icon: Lock,
      title: "This link is no longer active",
      body: "Ask HR to send you a new onboarding link if you still need to submit your details.",
    },
    open: { icon: CheckCircle2, title: "", body: "" },
  }[state.status];
  const Icon = content.icon;
  return (
    <Shell organization={state.organization_name}>
      <div className="rounded-xl border border-border bg-surface p-8 text-center shadow-sm">
        <Icon className="mx-auto size-10 text-primary" aria-hidden="true" />
        <h1 className="mt-4 text-xl font-semibold tracking-tight">
          {content.title}
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">{content.body}</p>
      </div>
    </Shell>
  );
}

function Section({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <fieldset className="border-t border-border py-6 first:border-t-0 first:pt-0">
      <legend className="sr-only">{title}</legend>
      <h2 className="text-[15px] font-semibold" aria-hidden="true">
        {title}
      </h2>
      {description && (
        <p className="mt-0.5 text-[13px] text-muted-foreground">
          {description}
        </p>
      )}
      <div className="mt-4 grid gap-4 sm:grid-cols-2">{children}</div>
    </fieldset>
  );
}

function Form({
  token,
  form: state,
  onDone,
}: {
  token: string;
  form: PublicForm;
  onDone: (state: PublicForm) => void;
}) {
  const [serverError, setServerError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    mode: "onTouched",
    defaultValues: {
      full_name: state.prefill.full_name ?? "",
      father_name: "",
      cnic: "",
      email: state.prefill.email ?? "",
      designation: state.prefill.designation ?? "",
      date_of_joining: "",
      date_of_birth: "",
      contact_number: "",
      emergency_1_name: "",
      emergency_1_phone: "",
      emergency_2_name: "",
      emergency_2_phone: "",
      address: "",
      account_title: "",
      bank_name: "",
      bank_account_number: "",
      ntn: "",
      professional_reference: "",
      about: "",
    },
  });
  const { register, formState, control } = form;
  const e = formState.errors;

  const onSubmit = form.handleSubmit(async (values) => {
    setServerError(null);
    setSubmitting(true);
    try {
      onDone(await onboardingService.submit(token, toSubmission(values)));
      window.scrollTo({ top: 0 });
    } catch (error) {
      if (error instanceof ApiError && error.status === 422) {
        const fields = Object.keys(error.fields);
        for (const field of fields) {
          const target = SERVER_FIELDS[field] ?? (field as keyof Values);
          if (target in values)
            form.setError(target, { message: "Check this value" });
        }
        setServerError(
          fields.length
            ? "Some details need attention. Check the highlighted fields."
            : errorMessage(
                error,
                "Check your dates and details, then try again.",
              ),
        );
      } else {
        setServerError(
          errorMessage(error, "Your details couldn't be submitted. Try again."),
        );
      }
      window.scrollTo({ top: 0, behavior: "smooth" });
    } finally {
      setSubmitting(false);
    }
  });

  const text = (
    name: keyof Values,
    label: string,
    options: {
      required?: boolean;
      type?: string;
      autoComplete?: string;
      help?: string;
      placeholder?: string;
      inputMode?: React.HTMLAttributes<HTMLInputElement>["inputMode"];
      className?: string;
    } = {},
  ) => (
    <FormField
      label={label}
      htmlFor={name}
      required={options.required}
      optional={!options.required}
      error={e[name]}
      help={options.help}
      className={options.className}
    >
      <Input
        id={name}
        type={options.type ?? "text"}
        autoComplete={options.autoComplete ?? "off"}
        inputMode={options.inputMode}
        placeholder={options.placeholder}
        aria-invalid={Boolean(e[name])}
        disabled={submitting}
        {...register(name)}
      />
    </FormField>
  );

  return (
    <>
      <h1 className="text-2xl font-semibold tracking-tight">
        Welcome to {state.organization_name}
      </h1>
      <p className="mt-1.5 text-sm text-muted-foreground">
        Please fill in your details for your employee record. Fields marked with
        * are required. HR reviews everything before your record is created.
      </p>
      <Notice tone="neutral" icon={Lock} className="mt-4">
        Your CNIC, bank and contact details are encrypted and visible only to
        authorised HR staff.
      </Notice>
      <form
        onSubmit={onSubmit}
        noValidate
        className="mt-6 rounded-xl border border-border bg-surface p-4 shadow-sm sm:p-6"
      >
        {serverError && (
          <div className="mb-4">
            <InlineError message={serverError} />
          </div>
        )}
        <Section title="Personal details">
          {text("full_name", "Full name as per CNIC", {
            required: true,
            autoComplete: "name",
          })}
          {text("father_name", "Father name", { required: true })}
          {text("cnic", "CNIC number", {
            required: true,
            placeholder: "12345-1234567-1",
            inputMode: "numeric",
          })}
          <FormField label="Gender" optional error={e.gender}>
            <Controller
              control={control}
              name="gender"
              render={({ field }) => (
                <RadioGroup
                  value={field.value ?? ""}
                  onValueChange={field.onChange}
                  className="flex gap-6 pt-1.5"
                  aria-label="Gender"
                  disabled={submitting}
                >
                  {[
                    ["male", "Male"],
                    ["female", "Female"],
                  ].map(([value, label]) => (
                    <div key={value} className="flex items-center gap-2">
                      <RadioGroupItem value={value!} id={`gender-${value}`} />
                      <Label htmlFor={`gender-${value}`}>{label}</Label>
                    </div>
                  ))}
                </RadioGroup>
              )}
            />
          </FormField>
          {text("date_of_birth", "Date of birth", {
            required: true,
            type: "date",
            autoComplete: "bday",
          })}
        </Section>

        <Section title="Job">
          {text("designation", "Designation", { required: true })}
          {text("date_of_joining", "Date of joining", {
            required: true,
            type: "date",
          })}
          <FormField
            label="Job type"
            required
            error={e.job_type}
            className="sm:col-span-2"
          >
            <Controller
              control={control}
              name="job_type"
              render={({ field }) => (
                <RadioGroup
                  value={field.value ?? ""}
                  onValueChange={field.onChange}
                  className="grid grid-cols-2 gap-2 pt-1 sm:grid-cols-4"
                  aria-label="Job type"
                  disabled={submitting}
                >
                  {JOB_TYPES.map((j) => (
                    <div
                      key={j.value}
                      className="flex items-center gap-2 rounded-lg border border-border px-3 py-2"
                    >
                      <RadioGroupItem value={j.value} id={`job-${j.value}`} />
                      <Label htmlFor={`job-${j.value}`}>{j.label}</Label>
                    </div>
                  ))}
                </RadioGroup>
              )}
            />
          </FormField>
        </Section>

        <Section title="Contact">
          {text("email", "Email", {
            required: true,
            type: "email",
            autoComplete: "email",
          })}
          {text("contact_number", "Your contact number", {
            required: true,
            type: "tel",
            autoComplete: "tel",
            placeholder: "0300-1234567",
          })}
          <FormField
            label="Current address with nearby landmark"
            htmlFor="address"
            required
            error={e.address}
            className="sm:col-span-2"
          >
            <Textarea
              id="address"
              rows={3}
              autoComplete="street-address"
              aria-invalid={Boolean(e.address)}
              disabled={submitting}
              {...register("address")}
            />
          </FormField>
        </Section>

        <Section
          title="Emergency contacts"
          description="Two people we can reach in an emergency."
        >
          {text("emergency_1_name", "Emergency contact 1 — name", {
            required: true,
            placeholder: "Name (relation)",
          })}
          {text("emergency_1_phone", "Emergency contact 1 — number", {
            required: true,
            type: "tel",
          })}
          {text("emergency_2_name", "Emergency contact 2 — name", {
            required: true,
            placeholder: "Name (relation)",
          })}
          {text("emergency_2_phone", "Emergency contact 2 — number", {
            required: true,
            type: "tel",
          })}
        </Section>

        <Section title="Bank and tax" description="For salary payments.">
          {text("account_title", "Account title")}
          {text("bank_name", "Bank name")}
          {text("bank_account_number", "Bank account number or IBAN", {
            className: "sm:col-span-2",
          })}
          {text("ntn", "NTN number", { help: "If you have one." })}
        </Section>

        <Section title="About you">
          <FormField
            label="Professional reference"
            htmlFor="professional_reference"
            optional
            help="Name, email and phone number of someone we can contact."
            error={e.professional_reference}
            className="sm:col-span-2"
          >
            <Textarea
              id="professional_reference"
              rows={2}
              disabled={submitting}
              {...register("professional_reference")}
            />
          </FormField>
          <FormField
            label="Something about yourself for your announcement letter"
            htmlFor="about"
            optional
            help="Your work, hobbies or a passion you'd like the team to know about."
            error={e.about}
            className="sm:col-span-2"
          >
            <Textarea
              id="about"
              rows={4}
              disabled={submitting}
              {...register("about")}
            />
          </FormField>
        </Section>

        <div className="flex flex-col-reverse gap-3 border-t border-border pt-5 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs text-muted-foreground">
            You can submit this form once. Contact HR if you need to change
            something afterwards.
          </p>
          <Button type="submit" size="lg" loading={submitting}>
            Submit details
          </Button>
        </div>
      </form>
    </>
  );
}
