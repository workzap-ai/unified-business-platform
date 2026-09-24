"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FormField } from "@/components/app/forms";
import { InlineError } from "@/components/app/states";
import { ApiError, errorMessage } from "@/services/api-client";
import { useSession } from "./session-provider";

const schema = z.object({
  display_name: z.string().trim().min(1, "Enter your name").max(160),
  organization_name: z.string().trim().min(2, "Enter your business name").max(160),
  email: z.string().trim().email("Enter a valid email address"),
  password: z
    .string()
    .min(12, "Use at least 12 characters")
    .max(128)
    .refine((v) => new Set(v).size >= 5, "Use a less repetitive password"),
});
type Values = z.infer<typeof schema>;

export function RegisterForm() {
  const { register: registerAccount } = useSession();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { display_name: "", organization_name: "", email: "", password: "" },
  });
  const errors = form.formState.errors;

  async function onSubmit(values: Values) {
    setError(null);
    try {
      await registerAccount(values);
      router.replace("/");
    } catch (e) {
      if (e instanceof ApiError && e.status === 422 && Object.keys(e.fields).length) {
        for (const field of Object.keys(e.fields)) {
          if (field in values) form.setError(field as keyof Values, { message: "Check this value" });
        }
      }
      setError(errorMessage(e, "Registration could not be completed."));
    }
  }

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Create your workspace</h1>
      <p className="mt-1.5 text-sm text-muted-foreground">
        You'll be the owner. You can invite your team and install PI afterwards.
      </p>
      <form onSubmit={form.handleSubmit(onSubmit)} className="mt-6 space-y-4" noValidate>
        {error && <InlineError message={error} />}
        <FormField label="Your name" htmlFor="display_name" error={errors.display_name}>
          <Input id="display_name" autoComplete="name" {...form.register("display_name")} aria-invalid={Boolean(errors.display_name)} />
        </FormField>
        <FormField label="Business name" htmlFor="organization_name" error={errors.organization_name}>
          <Input id="organization_name" autoComplete="organization" {...form.register("organization_name")} aria-invalid={Boolean(errors.organization_name)} />
        </FormField>
        <FormField label="Work email" htmlFor="email" error={errors.email}>
          <Input id="email" type="email" autoComplete="email" {...form.register("email")} aria-invalid={Boolean(errors.email)} />
        </FormField>
        <FormField label="Password" htmlFor="password" error={errors.password} help="At least 12 characters. A passphrase works well.">
          <Input id="password" type="password" autoComplete="new-password" {...form.register("password")} aria-invalid={Boolean(errors.password)} />
        </FormField>
        <Button type="submit" className="w-full" size="lg" loading={form.formState.isSubmitting}>
          Create workspace
        </Button>
      </form>
      <p className="mt-6 text-center text-sm text-muted-foreground">
        Already have an account?{" "}
        <Link href="/login" className="font-medium text-primary hover:underline">
          Sign in
        </Link>
      </p>
    </div>
  );
}
