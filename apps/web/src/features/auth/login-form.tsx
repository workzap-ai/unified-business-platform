"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Eye, EyeOff, FlaskConical, ScanFace } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FormField } from "@/components/app/forms";
import { InlineError, Notice } from "@/components/app/states";
import { ApiError, errorMessage } from "@/services/api-client";
import { isDemo } from "@/lib/data-mode";
import { useSession } from "./session-provider";
import { passkeyError, passkeysAvailable, unlockName } from "./passkey";

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
  const { login, loginWithPasskey, status } = useSession();
  const [passkey, setPasskey] = useState<{ ok: boolean; name: string }>({
    ok: false,
    name: "Face ID",
  });
  const [usingPasskey, setUsingPasskey] = useState(false);
  const router = useRouter();
  const params = useSearchParams();
  const next = safeNext(params.get("next"));
  const justReset = params.get("reset") === "1";
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

  useEffect(() => {
    // Read the browser's capabilities after mount so server and client HTML match.
    // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time capability probe
    setPasskey({ ok: !isDemo && passkeysAvailable(), name: unlockName() });
  }, []);

  async function signInWithPasskey() {
    setError(null);
    setUsingPasskey(true);
    try {
      await loginWithPasskey();
      router.replace(next);
    } catch (e) {
      if (e instanceof ApiError) {
        setError(
          e.status === 401
            ? "That passkey isn't linked to an active account. Sign in with your password, then add it in Account & security."
            : errorMessage(e, "Sign-in failed. Please try again."),
        );
      } else {
        const message = passkeyError(e);
        if (message) setError(message);
      }
    } finally {
      setUsingPasskey(false);
    }
  }

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
      {justReset && !isDemo && (
        <Notice tone="success" className="mt-6">
          Your password was reset. Sign in with your new password.
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
      {passkey.ok && (
        <>
          <div className="my-5 flex items-center gap-3 text-xs text-muted-foreground">
            <span className="h-px flex-1 bg-border" />
            or
            <span className="h-px flex-1 bg-border" />
          </div>
          <Button
            type="button"
            variant="secondary"
            size="lg"
            className="w-full"
            loading={usingPasskey}
            onClick={() => void signInWithPasskey()}
          >
            <ScanFace aria-hidden /> Sign in with {passkey.name}
          </Button>
          <p className="mt-2 text-center text-xs text-muted-foreground">
            Uses a passkey on this device. Your face or fingerprint never leaves
            it.
          </p>
        </>
      )}
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
        Forgot your password?{" "}
        <Link
          href="/forgot-password"
          className="font-medium text-primary hover:underline"
        >
          Reset it
        </Link>
        .
      </p>
    </div>
  );
}
