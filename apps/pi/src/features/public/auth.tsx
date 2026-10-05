"use client";

import { useQueryClient } from "@tanstack/react-query";
import { BookOpenText, Eye, EyeOff, Hand, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";

import { PiFace } from "@/components/brand";
import {
  Button,
  Card,
  CardSection,
  Field,
  Input,
  Notice,
  Select,
} from "@/components/ui";
import { ApiError, errorText, post } from "@/lib/api";
import { SecondStepForm, type SecondStep } from "@/features/security";
import { useSession } from "@/lib/session";
import type { SessionView } from "@/lib/types";
import s from "./public.module.css";

function safeNext(value: string | null): string {
  // Only same-app relative paths; never an external or protocol-relative URL.
  return value && value.startsWith("/") && !value.startsWith("//")
    ? value
    : "/home";
}

function AuthCard({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
}) {
  return (
    <div className={s.authLayout}>
      <aside className={s.authStory} aria-label="Meet pi">
        <PiFace size={48} decorative />
        <h2>
          A little intelligence.
          <br />
          <em>A personal touch.</em>
        </h2>
        <p>
          A thoughtful assistant for the conversations that matter to your
          business.
        </p>
        <div className={s.authPromises}>
          <span>
            <BookOpenText size={17} aria-hidden />
            Answers from your approved knowledge
          </span>
          <span>
            <Hand size={17} aria-hidden />
            Your team stays in control
          </span>
          <span>
            <ShieldCheck size={17} aria-hidden />
            Launch only when you&apos;re ready
          </span>
        </div>
      </aside>
      <div className={s.authForm}>
        <Card>
          <CardSection>
            <span className={s.authLabel}>YOUR NEXT CHAPTER STARTS HERE</span>
            <h1>{title}</h1>
            <p className={s.authSubtitle}>{subtitle}</p>
            <div className="mt-6">{children}</div>
          </CardSection>
        </Card>
      </div>
    </div>
  );
}

function PasswordInput({
  autoComplete,
  minLength,
}: {
  autoComplete: string;
  minLength?: number;
}) {
  const [visible, setVisible] = React.useState(false);
  const Icon = visible ? EyeOff : Eye;
  return (
    <div className={s.password}>
      <Input
        id="password"
        name="password"
        type={visible ? "text" : "password"}
        autoComplete={autoComplete}
        minLength={minLength}
        required
        className="pe-12"
      />
      <button
        type="button"
        className={s.passwordToggle}
        aria-label={visible ? "Hide password" : "Show password"}
        aria-pressed={visible}
        onClick={() => setVisible(!visible)}
      >
        <Icon size={18} aria-hidden />
      </button>
    </div>
  );
}

export function SignInForm() {
  const router = useRouter();
  const params = useSearchParams();
  const client = useQueryClient();
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [step, setStep] = React.useState<SecondStep | null>(null);

  function signedIn(session: SessionView) {
    client.clear();
    client.setQueryData(["session"], session);
    router.replace(
      session.business ? safeNext(params.get("next")) : "/setup/new",
    );
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError(null);
    try {
      const answer = await post<SessionView | SecondStep>("/auth/login", {
        email: String(form.get("email") ?? ""),
        password: String(form.get("password") ?? ""),
      });
      if ("mfa_required" in answer) {
        setStep(answer); // the password was right; now the face or fingerprint
        setBusy(false);
        return;
      }
      signedIn(answer);
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 401
          ? "That email and password don't match. Check them and try again."
          : errorText(err),
      );
      setBusy(false);
    }
  }

  if (step)
    return (
      <AuthCard title="One more check" subtitle="Keep your business safe.">
        <SecondStepForm
          step={step}
          onBack={() => setStep(null)}
          onDone={signedIn}
        />
      </AuthCard>
    );

  return (
    <AuthCard
      title="Welcome back"
      subtitle="Sign in to see your conversations."
    >
      <form onSubmit={submit} className="space-y-4" noValidate>
        {error ? <Notice tone="danger">{error}</Notice> : null}
        {!error && params.get("reset") === "1" ? (
          <Notice tone="success">
            Your password was reset. Sign in with your new password.
          </Notice>
        ) : null}
        <Field label="Email" htmlFor="email">
          <Input
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            required
          />
        </Field>
        <Field label="Password" htmlFor="password">
          <PasswordInput autoComplete="current-password" />
        </Field>
        <Button type="submit" className="w-full" loading={busy}>
          Sign in
        </Button>
      </form>
      <p className="mt-6 text-center text-sm text-muted-foreground">
        New to pi?{" "}
        <Link
          href="/sign-up"
          className="font-medium text-accent hover:underline"
        >
          Create an account
        </Link>
      </p>
      <p className="mt-3 text-center text-sm text-muted-foreground">
        Forgot your password?{" "}
        <Link
          href="/forgot-password"
          className="font-medium text-accent hover:underline"
        >
          Reset it
        </Link>
      </p>
    </AuthCard>
  );
}

export function SignUpForm() {
  const router = useRouter();
  const client = useQueryClient();
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const password = String(form.get("password") ?? "");
    if (password.length < 12) {
      setError("Use at least 12 characters for your password.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const session = await post<SessionView>("/auth/register", {
        email: String(form.get("email") ?? ""),
        password,
        display_name: String(form.get("display_name") ?? ""),
        business_name: String(form.get("business_name") ?? ""),
        offer_type: String(form.get("offer_type") ?? "services"),
      });
      client.clear();
      client.setQueryData(["session"], session);
      router.replace("/setup");
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 422
          ? "Please check your details and try again."
          : errorText(err),
      );
      setBusy(false);
    }
  }

  return (
    <AuthCard
      title="Set up pi for your business"
      subtitle="It takes a few minutes. pi won't message anyone until you launch it."
    >
      <form onSubmit={submit} className="space-y-4" noValidate>
        {error ? <Notice tone="danger">{error}</Notice> : null}
        <Field label="Your name" htmlFor="display_name">
          <Input
            id="display_name"
            name="display_name"
            autoComplete="name"
            required
            maxLength={160}
          />
        </Field>
        <Field label="Business name" htmlFor="business_name">
          <Input
            id="business_name"
            name="business_name"
            autoComplete="organization"
            required
            maxLength={160}
          />
        </Field>
        <Field label="What do you offer?" htmlFor="offer_type">
          <Select id="offer_type" name="offer_type" defaultValue="services">
            <option value="services">
              Services (projects, appointments, consulting)
            </option>
            <option value="products">Products (shop, orders, delivery)</option>
            <option value="both">Both</option>
          </Select>
        </Field>
        <Field label="Work email" htmlFor="email">
          <Input
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            required
          />
        </Field>
        <Field
          label="Password"
          htmlFor="password"
          hint="At least 12 characters."
        >
          <PasswordInput autoComplete="new-password" minLength={12} />
        </Field>
        <Button type="submit" className="w-full" loading={busy}>
          Create account
        </Button>
      </form>
      <p className="mt-6 text-center text-sm text-muted-foreground">
        Already using pi?{" "}
        <Link
          href="/sign-in"
          className="font-medium text-accent hover:underline"
        >
          Sign in
        </Link>
      </p>
    </AuthCard>
  );
}

export function ForgotPasswordForm() {
  const [sentTo, setSentTo] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const email = String(form.get("email") ?? "");
    setBusy(true);
    setError(null);
    try {
      await post("/auth/forgot-password", { email });
      setSentTo(email);
    } catch (err) {
      setError(errorText(err));
      setBusy(false);
    }
  }

  if (sentTo) {
    return (
      <AuthCard title="Check your email" subtitle="">
        <Notice tone="success">
          If <b>{sentTo}</b> matches an account, we&rsquo;ve sent a link to
          reset the password. It expires in 30 minutes and works once.
        </Notice>
        <p className="mt-6 text-center text-sm text-muted-foreground">
          Didn&rsquo;t get it? Check spam, or{" "}
          <button
            type="button"
            className="font-medium text-accent hover:underline"
            onClick={() => setSentTo(null)}
          >
            try another address
          </button>
          .
        </p>
      </AuthCard>
    );
  }

  return (
    <AuthCard
      title="Reset your password"
      subtitle="Enter the email on your account and we'll send a link to choose a new password."
    >
      <form onSubmit={submit} className="space-y-4" noValidate>
        {error ? <Notice tone="danger">{error}</Notice> : null}
        <Field label="Email" htmlFor="email">
          <Input
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            required
          />
        </Field>
        <Button type="submit" className="w-full" loading={busy}>
          Send reset link
        </Button>
      </form>
      <p className="mt-6 text-center text-sm text-muted-foreground">
        <Link
          href="/sign-in"
          className="font-medium text-accent hover:underline"
        >
          Back to sign in
        </Link>
      </p>
    </AuthCard>
  );
}

export function ResetPasswordForm() {
  const router = useRouter();
  const params = useSearchParams();
  const token = params.get("token") ?? "";
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  if (!token) {
    return (
      <AuthCard title="Invalid reset link" subtitle="">
        <Notice tone="danger">
          This link is missing its token. Request a new one below.
        </Notice>
        <p className="mt-6 text-center text-sm text-muted-foreground">
          <Link
            href="/forgot-password"
            className="font-medium text-accent hover:underline"
          >
            Request a new reset link
          </Link>
        </p>
      </AuthCard>
    );
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const password = String(form.get("password") ?? "");
    const confirm = String(form.get("confirm") ?? "");
    if (password.length < 12) {
      setError("Use at least 12 characters for your password.");
      return;
    }
    if (password !== confirm) {
      setError("Passwords don't match.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await post("/auth/reset-password", { token, new_password: password });
      router.replace("/sign-in?reset=1");
    } catch (err) {
      setError(
        err instanceof ApiError && err.code === "INVALID_RESET_TOKEN"
          ? "This reset link is invalid, expired, or already used. Request a new one."
          : errorText(err),
      );
      setBusy(false);
    }
  }

  return (
    <AuthCard
      title="Choose a new password"
      subtitle="This signs you out everywhere else, as a precaution."
    >
      <form onSubmit={submit} className="space-y-4" noValidate>
        {error ? (
          <div className="space-y-2">
            <Notice tone="danger">{error}</Notice>
            <Link
              href="/forgot-password"
              className="block text-center text-sm font-medium text-accent hover:underline"
            >
              Request a new reset link
            </Link>
          </div>
        ) : null}
        <Field
          label="New password"
          htmlFor="password"
          hint="At least 12 characters."
        >
          <PasswordInput autoComplete="new-password" minLength={12} />
        </Field>
        <Field label="Confirm new password" htmlFor="confirm">
          <Input
            id="confirm"
            name="confirm"
            type="password"
            autoComplete="new-password"
            required
          />
        </Field>
        <Button type="submit" className="w-full" loading={busy}>
          Reset password
        </Button>
      </form>
    </AuthCard>
  );
}

export function AcceptInviteForm() {
  const router = useRouter();
  const client = useQueryClient();
  const params = useSearchParams();
  const token = params.get("token") ?? "";
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  if (!token) {
    return (
      <AuthCard title="Invalid invitation link" subtitle="">
        <Notice tone="danger">
          This link is missing its token. Ask whoever invited you to send a new
          one.
        </Notice>
        <p className="mt-6 text-center text-sm text-muted-foreground">
          <Link
            href="/sign-in"
            className="font-medium text-accent hover:underline"
          >
            Go to sign in
          </Link>
        </p>
      </AuthCard>
    );
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const password = String(form.get("password") ?? "");
    const confirm = String(form.get("confirm") ?? "");
    if (password.length < 12) {
      setError("Use at least 12 characters for your password.");
      return;
    }
    if (password !== confirm) {
      setError("Passwords don't match.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const session = await post<SessionView>("/auth/accept-invite", {
        token,
        new_password: password,
      });
      client.clear();
      client.setQueryData(["session"], session);
      router.replace(session.business ? "/home" : "/setup/new");
    } catch (err) {
      setError(
        err instanceof ApiError && err.code === "INVALID_INVITE_TOKEN"
          ? "This invitation is invalid, expired, or already used. Ask whoever invited you to send a new one."
          : errorText(err),
      );
      setBusy(false);
    }
  }

  return (
    <AuthCard
      title="Choose your password"
      subtitle="You've been invited to a pi workspace. Set a password to finish joining."
    >
      <form onSubmit={submit} className="space-y-4" noValidate>
        {error ? <Notice tone="danger">{error}</Notice> : null}
        <Field
          label="Password"
          htmlFor="password"
          hint="At least 12 characters."
        >
          <PasswordInput autoComplete="new-password" minLength={12} />
        </Field>
        <Field label="Confirm password" htmlFor="confirm">
          <Input
            id="confirm"
            name="confirm"
            type="password"
            autoComplete="new-password"
            required
          />
        </Field>
        <Button type="submit" className="w-full" loading={busy}>
          Join workspace
        </Button>
      </form>
    </AuthCard>
  );
}

export function VerifyEmailForm() {
  const params = useSearchParams();
  const token = params.get("token") ?? "";
  const client = useQueryClient();
  const session = useSession();
  const [state, setState] = React.useState<"checking" | "done" | "error">(
    token ? "checking" : "error",
  );
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!token) return;
    let active = true;
    post("/auth/verify-email", { token })
      .then(() => {
        if (!active) return;
        setState("done");
        void client.invalidateQueries({ queryKey: ["session"] });
      })
      .catch((err) => {
        if (!active) return;
        setState("error");
        setError(errorText(err));
      });
    return () => {
      active = false;
    };
    // Runs once for the token this page loaded with.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  return (
    <AuthCard title="Confirm your email" subtitle="">
      {state === "checking" ? (
        <Notice tone="info">Confirming your email address…</Notice>
      ) : null}
      {state === "done" ? (
        <Notice tone="success">Your email address is confirmed.</Notice>
      ) : null}
      {state === "error" ? (
        <Notice tone="danger">
          {error ?? "This link is missing its token."}
        </Notice>
      ) : null}
      <p className="mt-6 text-center text-sm text-muted-foreground">
        <Link
          href={session.data ? "/home" : "/sign-in"}
          className="font-medium text-accent hover:underline"
        >
          {session.data ? "Continue to pi" : "Go to sign in"}
        </Link>
      </p>
    </AuthCard>
  );
}
