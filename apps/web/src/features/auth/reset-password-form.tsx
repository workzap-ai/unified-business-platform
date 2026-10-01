"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Eye, EyeOff, LinkIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FormField } from "@/components/app/forms";
import { InlineError, Notice } from "@/components/app/states";
import { ApiError, errorMessage } from "@/services/api-client";
import { authService } from "./service";

const schema = z
  .object({
    password: z
      .string()
      .min(12, "Use at least 12 characters")
      .max(128)
      .refine((v) => new Set(v).size >= 5, "Use a less repetitive password"),
    confirm: z.string().min(1, "Repeat the new password"),
  })
  .refine((v) => v.password === v.confirm, {
    path: ["confirm"],
    message: "Passwords don't match",
  });
type Values = z.infer<typeof schema>;

export function ResetPasswordForm() {
  const router = useRouter();
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
          Invalid reset link
        </h1>
        <Notice tone="danger" icon={LinkIcon} className="mt-6">
          This link is missing its token. Request a new one below.
        </Notice>
        <p className="mt-6 text-center text-sm text-muted-foreground">
          <Link
            href="/forgot-password"
            className="font-medium text-primary hover:underline"
          >
            Request a new reset link
          </Link>
        </p>
      </div>
    );
  }

  async function onSubmit(values: Values) {
    setError(null);
    try {
      await authService.resetPassword(token, values.password);
      router.replace("/login?reset=1");
    } catch (e) {
      if (e instanceof ApiError && e.code === "INVALID_RESET_TOKEN") {
        setError(
          "This reset link is invalid, expired, or already used. Request a new one.",
        );
        return;
      }
      setError(errorMessage(e, "Your password could not be reset."));
    }
  }

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">
        Choose a new password
      </h1>
      <p className="mt-1.5 text-sm text-muted-foreground">
        This signs you out everywhere else, as a precaution.
      </p>
      <form
        onSubmit={form.handleSubmit(onSubmit)}
        className="mt-6 space-y-4"
        noValidate
      >
        {error && (
          <div className="space-y-2">
            <InlineError message={error} />
            <Link
              href="/forgot-password"
              className="block text-center text-sm font-medium text-primary hover:underline"
            >
              Request a new reset link
            </Link>
          </div>
        )}
        <FormField
          label="New password"
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
          label="Confirm new password"
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
          Reset password
        </Button>
      </form>
    </div>
  );
}
