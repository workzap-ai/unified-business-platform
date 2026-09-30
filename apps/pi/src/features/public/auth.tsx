"use client";

import { useQueryClient } from "@tanstack/react-query";
import { BookOpenText, Eye, EyeOff, Hand, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";

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
      <aside className={s.authStory} aria-label="Meet Pi">
        <span className={s.exampleMark} aria-hidden>
          Pi
        </span>
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

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError(null);
    try {
      const session = await post<SessionView>("/auth/login", {
        email: String(form.get("email") ?? ""),
        password: String(form.get("password") ?? ""),
      });
      client.clear();
      client.setQueryData(["session"], session);
      router.replace(
        session.business ? safeNext(params.get("next")) : "/setup/new",
      );
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 401
          ? "That email and password don't match. Check them and try again."
          : errorText(err),
      );
      setBusy(false);
    }
  }

  return (
    <AuthCard
      title="Welcome back"
      subtitle="Sign in to see your conversations."
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
        <Field label="Password" htmlFor="password">
          <PasswordInput autoComplete="current-password" />
        </Field>
        <Button type="submit" className="w-full" loading={busy}>
          Sign in
        </Button>
      </form>
      <p className="mt-6 text-center text-sm text-muted-foreground">
        New to Pi?{" "}
        <Link
          href="/sign-up"
          className="font-medium text-accent hover:underline"
        >
          Create an account
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
      title="Set up Pi for your business"
      subtitle="It takes a few minutes. Pi won't message anyone until you launch it."
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
        Already using Pi?{" "}
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
