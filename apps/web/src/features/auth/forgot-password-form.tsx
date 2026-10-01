"use client";

import { useState } from "react";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { ArrowLeft, MailCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FormField } from "@/components/app/forms";
import { InlineError, Notice } from "@/components/app/states";
import { errorMessage } from "@/services/api-client";
import { authService } from "./service";

const schema = z.object({
  email: z
    .string()
    .trim()
    .min(1, "Enter your email")
    .email("Enter a valid email address"),
});
type Values = z.infer<typeof schema>;

export function ForgotPasswordForm() {
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { email: "" },
  });

  async function onSubmit(values: Values) {
    setError(null);
    try {
      await authService.forgotPassword(values.email);
      setSentTo(values.email);
    } catch (e) {
      setError(errorMessage(e, "That couldn't be sent. Please try again."));
    }
  }

  if (sentTo) {
    return (
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          Check your email
        </h1>
        <Notice tone="success" icon={MailCheck} className="mt-6">
          If <b>{sentTo}</b> matches an account, we&rsquo;ve sent a link to
          reset the password. It expires in 30 minutes and works once.
        </Notice>
        <p className="mt-6 text-center text-sm text-muted-foreground">
          Didn&rsquo;t get it? Check spam, or{" "}
          <button
            type="button"
            className="font-medium text-primary hover:underline"
            onClick={() => setSentTo(null)}
          >
            try another address
          </button>
          .
        </p>
      </div>
    );
  }

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">
        Reset your password
      </h1>
      <p className="mt-1.5 text-sm text-muted-foreground">
        Enter the email on your account and we&rsquo;ll send a link to choose
        a new password.
      </p>
      <form
        onSubmit={form.handleSubmit(onSubmit)}
        className="mt-6 space-y-4"
        noValidate
      >
        {error && <InlineError message={error} />}
        <FormField
          label="Email"
          htmlFor="email"
          error={form.formState.errors.email}
        >
          <Input
            id="email"
            type="email"
            autoComplete="email"
            autoFocus
            aria-invalid={Boolean(form.formState.errors.email)}
            {...form.register("email")}
          />
        </FormField>
        <Button
          type="submit"
          className="w-full"
          size="lg"
          loading={form.formState.isSubmitting}
        >
          Send reset link
        </Button>
      </form>
      <p className="mt-6 flex items-center justify-center gap-1.5 text-center text-sm text-muted-foreground">
        <ArrowLeft className="size-3.5" aria-hidden="true" />
        <Link href="/login" className="font-medium text-primary hover:underline">
          Back to sign in
        </Link>
      </p>
    </div>
  );
}
