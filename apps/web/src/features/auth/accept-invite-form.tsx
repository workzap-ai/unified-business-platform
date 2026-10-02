"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Eye, EyeOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FormField } from "@/components/app/forms";
import { InlineError, Notice } from "@/components/app/states";
import { ApiError, errorMessage } from "@/services/api-client";
import { SESSION_KEY } from "./session-provider";
import { authService } from "./service";

const schema = z
  .object({
    password: z
      .string()
      .min(12, "Use at least 12 characters")
      .max(128)
      .refine((v) => new Set(v).size >= 5, "Use a less repetitive password"),
    confirm: z.string().min(1, "Repeat the password"),
  })
  .refine((v) => v.password === v.confirm, {
    path: ["confirm"],
    message: "Passwords don't match",
  });
type Values = z.infer<typeof schema>;

export function AcceptInviteForm() {
  const router = useRouter();
  const client = useQueryClient();
  const params = useSearchParams();
  const token = params.get("token") ?? "";
  const [error, setError] = useState<string | null>(null);
  const [showPassword, setShowPassword] = useState(false);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { password: "", confirm: "" },
  });

  if (!token) {
    return (
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          Invalid invitation link
        </h1>
        <Notice tone="danger" className="mt-6">
          This link is missing its token. Ask whoever invited you to send a
          new one.
        </Notice>
        <p className="mt-6 text-center text-sm text-muted-foreground">
          <Link href="/login" className="font-medium text-primary hover:underline">
            Go to sign in
          </Link>
        </p>
      </div>
    );
  }

  async function onSubmit(values: Values) {
    setError(null);
    try {
      const session = await authService.acceptInvite(token, values.password);
      client.setQueryData(SESSION_KEY, session);
      router.replace("/");
    } catch (e) {
      if (e instanceof ApiError && e.code === "INVALID_INVITE_TOKEN") {
        setError(
          "This invitation is invalid, expired, or already used. Ask whoever invited you to send a new one.",
        );
        return;
      }
      setError(errorMessage(e, "Your account could not be set up."));
    }
  }

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">
        Choose your password
      </h1>
      <p className="mt-1.5 text-sm text-muted-foreground">
        You&rsquo;ve been invited to a workspace. Set a password to finish
        joining.
      </p>
      <form
        onSubmit={form.handleSubmit(onSubmit)}
        className="mt-6 space-y-4"
        noValidate
      >
        {error && <InlineError message={error} />}
        <FormField
          label="Password"
          htmlFor="password"
          error={form.formState.errors.password}
          help="At least 12 characters. A short sentence is easy to remember and hard to guess."
        >
          <div className="relative">
            <Input
              id="password"
              type={showPassword ? "text" : "password"}
              autoComplete="new-password"
              autoFocus
              className="pr-10"
              aria-invalid={Boolean(form.formState.errors.password)}
              {...form.register("password")}
            />
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              className="absolute top-1/2 right-2 -translate-y-1/2 rounded p-1 text-muted-foreground hover:text-foreground"
              aria-label={showPassword ? "Hide password" : "Show password"}
            >
              {showPassword ? (
                <EyeOff className="size-4" />
              ) : (
                <Eye className="size-4" />
              )}
            </button>
          </div>
        </FormField>
        <FormField
          label="Confirm password"
          htmlFor="confirm"
          error={form.formState.errors.confirm}
        >
          <Input
            id="confirm"
            type={showPassword ? "text" : "password"}
            autoComplete="new-password"
            aria-invalid={Boolean(form.formState.errors.confirm)}
            {...form.register("confirm")}
          />
        </FormField>
        <Button
          type="submit"
          className="w-full"
          size="lg"
          loading={form.formState.isSubmitting}
        >
          Join workspace
        </Button>
      </form>
    </div>
  );
}
