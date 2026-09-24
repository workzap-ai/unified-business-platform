"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Eye, EyeOff, FlaskConical } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FormField } from "@/components/app/forms";
import { InlineError, Notice } from "@/components/app/states";
import { ApiError, errorMessage } from "@/services/api-client";
import { isDemo } from "@/lib/data-mode";
import { useSession } from "./session-provider";

const schema = z.object({
  email: z
    .string()
    .trim()
    .min(1, "Enter your email")
    .email("Enter a valid email address"),
  password: z.string().min(1, "Enter your password"),
});
type Values = z.infer<typeof schema>;

function safeNext(value: string | null) {
  // Only same-site relative paths; never an open redirect.
  return value && value.startsWith("/") && !value.startsWith("//")
    ? value
    : "/";
}

export function LoginForm() {
  const { login, status } = useSession();
  const router = useRouter();
  const params = useSearchParams();
  const next = safeNext(params.get("next"));
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      email: isDemo ? "demo@example.com" : "",
      password: isDemo ? "sample-data-only" : "",
    },
  });

  useEffect(() => {
    if (status === "ready") router.replace(next);
  }, [status, router, next]);

  async function onSubmit(values: Values) {
    setError(null);
    try {
      await login(values);
      router.replace(next);
    } catch (e) {
      setError(
        e instanceof ApiError && e.status === 401
          ? "That email and password don't match an active account. Accounts lock briefly after repeated failures."
          : errorMessage(e, "Sign-in failed. Please try again."),
      );
    }
  }

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Sign in</h1>
      <p className="mt-1.5 text-sm text-muted-foreground">
        Welcome back. Sign in to your workspace.
      </p>
      {isDemo && (
        <Notice
          tone="pi"
          icon={FlaskConical}
          className="mt-6"
          title="Sample-data mode"
        >
          This build runs on fictional sample data. Any email and password sign
          you in; nothing is sent to a server.
        </Notice>
      )}
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
        <FormField
          label="Password"
          htmlFor="password"
          error={form.formState.errors.password}
        >
          <div className="relative">
            <Input
              id="password"
              type={showPassword ? "text" : "password"}
              autoComplete="current-password"
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
        <Button
          type="submit"
          className="w-full"
          size="lg"
          loading={form.formState.isSubmitting}
        >
          Sign in
        </Button>
      </form>
      <p className="mt-6 text-center text-sm text-muted-foreground">
        New here?{" "}
        <Link
          href="/register"
          className="font-medium text-primary hover:underline"
        >
          Create a workspace
        </Link>
      </p>
      <p className="mt-3 text-center text-xs text-muted-foreground">
        Forgot your password? Ask a workspace administrator to reset access.
      </p>
    </div>
  );
}
