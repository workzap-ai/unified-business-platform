"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  ArrowLeft,
  Eye,
  EyeOff,
  FlaskConical,
  Fingerprint,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FormField } from "@/components/app/forms";
import { InlineError, Notice } from "@/components/app/states";
import { ApiError, errorMessage } from "@/services/api-client";
import { isDemo } from "@/lib/data-mode";
import { useSession } from "./session-provider";
import { authService } from "./service";
import { FaceCamera } from "./face-camera";
import { passkeyError, passkeysAvailable, unlockName } from "./passkey";
import type { SecondStep } from "./types";

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
  const { login, finishSignIn, status } = useSession();
  const [step, setStep] = useState<SecondStep | null>(null);
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

  async function onSubmit(values: Values) {
    setError(null);
    try {
      const result = await login(values);
      if ("mfa_required" in result) {
        setStep(result); // password was right; now the face or fingerprint
        return;
      }
      router.replace(next);
    } catch (e) {
      setError(
        e instanceof ApiError && e.status === 401
          ? "That email and password don't match an active account. Accounts lock briefly after repeated failures."
          : errorMessage(e, "Sign-in failed. Please try again."),
      );
    }
  }

  if (step)
    return (
      <SecondStepForm
        step={step}
        onBack={() => {
          setStep(null);
          form.setValue("password", "");
        }}
        onDone={async (session) => {
          await finishSignIn(session);
          router.replace(next);
        }}
      />
    );

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

/** Step two: the person's face on the camera, or their fingerprint if they prefer. */
function SecondStepForm({
  step,
  onBack,
  onDone,
}: {
  step: SecondStep;
  onBack: () => void;
  onDone: (
    session: Awaited<ReturnType<typeof authService.signInWithFace>>,
  ) => Promise<void>;
}) {
  const hasFace = step.methods.includes("face");
  const hasFingerprint = step.methods.includes("fingerprint");
  const [mode, setMode] = useState<"face" | "fingerprint">(
    hasFace ? "face" : "fingerprint",
  );
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [unlock, setUnlock] = useState("fingerprint");

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time capability probe
    setUnlock(passkeysAvailable() ? unlockName() : "fingerprint");
  }, []);

  function explain(e: unknown, fallback: string): string {
    if (e instanceof ApiError && e.code === "SIGN_IN_EXPIRED") {
      onBack();
      return "";
    }
    return errorMessage(e, fallback);
  }

  async function withFingerprint() {
    setError(null);
    setBusy(true);
    try {
      await onDone(await authService.signInWithFingerprint(step.ticket));
    } catch (e) {
      const message =
        e instanceof ApiError
          ? explain(e, "That fingerprint didn't work.")
          : passkeyError(e);
      if (message) setError(message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <button
        type="button"
        onClick={onBack}
        className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" aria-hidden /> Back
      </button>
      <h1 className="text-2xl font-semibold tracking-tight">
        {mode === "face" ? "Show your face" : `Use your ${unlock}`}
      </h1>
      <p className="mt-1.5 text-sm text-muted-foreground">
        Hi {step.name}. Your password was right; one more check keeps your
        account safe.
      </p>
      <div className="mt-6">
        {mode === "face" ? (
          <FaceCamera
            autoStart
            action="Check my face"
            onFrames={async (frames) => {
              try {
                await onDone(
                  await authService.signInWithFace(step.ticket, frames),
                );
              } catch (e) {
                const message = explain(e, "We couldn't check your face.");
                throw new Error(message || "Enter your password again.");
              }
            }}
          />
        ) : (
          <div className="space-y-3 text-center">
            <div className="mx-auto flex size-20 items-center justify-center rounded-full bg-primary-soft text-primary">
              <Fingerprint className="size-10" aria-hidden />
            </div>
            {error ? <InlineError message={error} /> : null}
            <Button
              size="lg"
              className="w-full"
              loading={busy}
              onClick={() => void withFingerprint()}
            >
              <Fingerprint aria-hidden /> Use {unlock}
            </Button>
          </div>
        )}
      </div>
      {hasFace && hasFingerprint ? (
        <p className="mt-5 text-center text-sm">
          <button
            type="button"
            className="font-medium text-primary hover:underline"
            onClick={() => {
              setError(null);
              setMode(mode === "face" ? "fingerprint" : "face");
            }}
          >
            {mode === "face" ? `Use ${unlock} instead` : "Use my face instead"}
          </button>
        </p>
      ) : null}
    </div>
  );
}
