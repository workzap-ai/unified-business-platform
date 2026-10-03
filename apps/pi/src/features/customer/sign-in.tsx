"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Check,
  ListChecks,
  MessagesSquare,
  ShieldCheck,
} from "lucide-react";

import { errorText } from "@/lib/api";
import { customerPost, type CustomerMe } from "@/lib/customer-api";
import { cn } from "@/lib/cn";
import { Button, Card, CardSection, Notice } from "@/components/ui";
import { ME } from "./shared";

const COUNTRIES = [
  { code: "92", label: "Pakistan", flag: "🇵🇰" },
  { code: "971", label: "UAE", flag: "🇦🇪" },
  { code: "966", label: "Saudi Arabia", flag: "🇸🇦" },
  { code: "91", label: "India", flag: "🇮🇳" },
  { code: "44", label: "United Kingdom", flag: "🇬🇧" },
  { code: "1", label: "USA / Canada", flag: "🇺🇸" },
];

/** "+92 300 1234567" from the picker and the typed number; a typed "+" wins. */
function fullNumber(country: string, typed: string) {
  const trimmed = typed.trim();
  if (trimmed.startsWith("+") || trimmed.startsWith("00")) return trimmed;
  return `+${country} ${trimmed.replace(/^0+/, "")}`;
}

export function SignIn() {
  const client = useQueryClient();
  const [country, setCountry] = useState("92");
  const [typed, setTyped] = useState("");
  const [step, setStep] = useState<"phone" | "code">("phone");
  const [wait, setWait] = useState(0);
  const phone = fullNumber(country, typed);

  useEffect(() => {
    if (wait <= 0) return;
    const timer = setTimeout(() => setWait((w) => w - 1), 1000);
    return () => clearTimeout(timer);
  }, [wait]);

  const send = useMutation({
    mutationFn: () => customerPost("/code", { phone }),
    onSuccess: () => {
      setStep("code");
      setWait(60);
    },
  });
  const verify = useMutation({
    mutationFn: (code: string) =>
      customerPost<CustomerMe>("/verify", { phone, code }),
    onSuccess: (me) => client.setQueryData(ME, me),
  });

  return (
    <div className="mx-auto grid w-full max-w-5xl grid-cols-1 items-stretch gap-6 lg:grid-cols-[1.05fr_1fr]">
      <aside className="relative hidden min-h-[560px] overflow-hidden rounded-3xl bg-accent p-10 text-accent-foreground lg:flex lg:flex-col lg:justify-between lg:gap-10">
        <div
          aria-hidden
          className="pointer-events-none absolute -right-24 -top-24 size-80 rounded-full bg-accent-foreground/10"
        />
        <div
          aria-hidden
          className="pointer-events-none absolute -bottom-32 -left-20 size-96 rounded-full bg-accent-foreground/5"
        />
        <div className="relative">
          <p className="text-sm font-medium opacity-80">pi Customer</p>
          <h1 className="mt-3 text-[2.5rem] font-semibold leading-[1.15] tracking-tight">
            All your WhatsApp chats with businesses, in one place.
          </h1>
        </div>
        <ul className="relative space-y-5">
          {[
            {
              icon: MessagesSquare,
              title: "Every conversation",
              text: "Read your full chats, play your voice notes and see your photos.",
            },
            {
              icon: ListChecks,
              title: "Every request, tracked",
              text: "pi lists what you asked for and whether it's sorted or with the team.",
            },
            {
              icon: ShieldCheck,
              title: "Private by design",
              text: "Only you can open it, with a code sent to your WhatsApp.",
            },
          ].map(({ icon: Icon, title, text }) => (
            <li key={title} className="flex gap-4">
              <span className="flex size-11 shrink-0 items-center justify-center rounded-2xl bg-accent-foreground/15">
                <Icon className="size-5" aria-hidden />
              </span>
              <span>
                <span className="block font-semibold">{title}</span>
                <span className="block text-sm opacity-80">{text}</span>
              </span>
            </li>
          ))}
        </ul>
      </aside>

      <Card className="flex flex-col justify-center">
        <CardSection className="space-y-6 p-5 sm:p-10">
          <div className="lg:hidden">
            <p className="text-sm font-medium text-accent">pi Customer</p>
            <h1 className="mt-1 text-2xl font-semibold tracking-tight">
              Your chats with businesses, in one place
            </h1>
          </div>
          <Steps step={step} />

          {step === "phone" ? (
            <form
              className="space-y-5"
              onSubmit={(e) => {
                e.preventDefault();
                send.mutate();
              }}
            >
              <div>
                <h2 className="text-xl font-semibold">Sign in with WhatsApp</h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Use the number you chat with businesses from.
                </p>
              </div>
              <div className="space-y-1.5">
                <label htmlFor="pc-phone" className="block text-sm font-medium">
                  Your WhatsApp number
                </label>
                <div className="flex gap-2">
                  <select
                    aria-label="Country code"
                    value={country}
                    onChange={(e) => setCountry(e.target.value)}
                    className="h-12 shrink-0 rounded-xl border border-border-strong bg-surface px-2.5 text-base focus-visible:outline-2 focus-visible:outline-ring sm:text-[15px]"
                  >
                    {COUNTRIES.map((c) => (
                      <option key={c.code} value={c.code}>
                        {c.flag} +{c.code}
                      </option>
                    ))}
                  </select>
                  <input
                    id="pc-phone"
                    type="tel"
                    inputMode="tel"
                    autoComplete="tel-national"
                    placeholder="300 1234567"
                    value={typed}
                    onChange={(e) => setTyped(e.target.value)}
                    className="h-12 min-w-0 flex-1 rounded-xl border border-border-strong bg-surface px-3.5 text-base placeholder:text-muted-foreground/70 focus-visible:outline-2 focus-visible:outline-ring sm:text-[15px]"
                    required
                  />
                </div>
                {send.isError ? (
                  <p className="text-[13px] text-danger" role="alert">
                    {errorText(send.error)}
                  </p>
                ) : (
                  <p className="text-[13px] text-muted-foreground">
                    Another country? Type the full number starting with +.
                  </p>
                )}
              </div>
              <Button
                type="submit"
                size="lg"
                className="w-full"
                loading={send.isPending}
                disabled={typed.replace(/\D/g, "").length < 6}
              >
                Send code on WhatsApp
              </Button>
            </form>
          ) : (
            <div className="space-y-5">
              <button
                type="button"
                onClick={() => {
                  setStep("phone");
                  verify.reset();
                }}
                className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
              >
                <ArrowLeft className="size-4" aria-hidden />
                {phone}
              </button>
              <div>
                <h2 className="text-xl font-semibold">Enter your code</h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  We sent a 6-digit code to your WhatsApp, from a business you
                  chatted with.
                </p>
              </div>
              <CodeInput
                // A wrong code starts the boxes again, focused on the first.
                key={verify.isError ? `retry-${verify.submittedAt}` : "code"}
                disabled={verify.isPending}
                error={verify.isError}
                onComplete={(code) => verify.mutate(code)}
              />
              {verify.isError && (
                <p className="text-[13px] text-danger" role="alert">
                  {errorText(verify.error)}
                </p>
              )}
              {verify.isPending && (
                <p className="text-sm text-muted-foreground">Checking…</p>
              )}
              <Notice tone="info" title="No code?">
                Codes come from a business you messaged on WhatsApp in the last
                24 hours. Send that business any message, then ask for a new
                code.
              </Notice>
              <Button
                variant="secondary"
                className="w-full"
                disabled={wait > 0}
                loading={send.isPending}
                onClick={() => send.mutate()}
              >
                {wait > 0 ? `Send a new code in ${wait}s` : "Send a new code"}
              </Button>
            </div>
          )}
          <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <ShieldCheck className="size-3.5 shrink-0" aria-hidden />
            Only you can see your conversations. Never share your code.
          </p>
        </CardSection>
      </Card>
    </div>
  );
}

function Steps({ step }: { step: "phone" | "code" }) {
  const items = [
    { key: "phone", label: "Your number" },
    { key: "code", label: "WhatsApp code" },
  ] as const;
  const at = items.findIndex((i) => i.key === step);
  return (
    <ol className="flex items-center gap-3" aria-label="Sign-in steps">
      {items.map((item, i) => (
        <li key={item.key} className="flex min-w-0 flex-1 items-center gap-2">
          <span
            className={cn(
              "flex size-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold",
              i < at
                ? "bg-success text-white"
                : i === at
                  ? "bg-accent text-accent-foreground"
                  : "bg-surface-muted text-muted-foreground",
            )}
            aria-current={i === at ? "step" : undefined}
          >
            {i < at ? <Check className="size-3.5" aria-hidden /> : i + 1}
          </span>
          <span
            className={cn(
              "truncate text-[13px] sm:text-sm",
              i === at ? "font-medium" : "text-muted-foreground",
            )}
          >
            {item.label}
          </span>
          {i < items.length - 1 && (
            <span className="h-px min-w-3 flex-1 bg-border" aria-hidden />
          )}
        </li>
      ))}
    </ol>
  );
}

/** Six boxes: typing moves forward, backspace moves back, a pasted code fills all. */
function CodeInput({
  onComplete,
  disabled,
  error,
}: {
  onComplete: (code: string) => void;
  disabled?: boolean;
  error?: boolean;
}) {
  const [digits, setDigits] = useState<string[]>(Array(6).fill(""));
  const boxes = useRef<(HTMLInputElement | null)[]>([]);
  useEffect(() => boxes.current[0]?.focus(), []);

  function fill(start: number, value: string) {
    const clean = value.replace(/\D/g, "");
    const next = [...digits];
    if (!clean) {
      next[start] = "";
      setDigits(next);
      return;
    }
    for (let i = 0; i < clean.length && start + i < 6; i++)
      next[start + i] = clean[i];
    setDigits(next);
    const end = Math.min(start + clean.length, 5);
    boxes.current[end]?.focus();
    if (next.every(Boolean)) onComplete(next.join(""));
  }

  return (
    <div
      className="flex justify-between gap-2"
      role="group"
      aria-label="6-digit code"
    >
      {digits.map((d, i) => (
        <input
          key={i}
          ref={(el) => {
            boxes.current[i] = el;
          }}
          aria-label={`Digit ${i + 1}`}
          inputMode="numeric"
          autoComplete={i === 0 ? "one-time-code" : "off"}
          maxLength={6}
          value={d}
          disabled={disabled}
          onChange={(e) => fill(i, e.target.value.slice(-6))}
          onPaste={(e) => {
            e.preventDefault();
            fill(0, e.clipboardData.getData("text"));
          }}
          onKeyDown={(e) => {
            if (e.key === "Backspace" && !digits[i] && i > 0) {
              const next = [...digits];
              next[i - 1] = "";
              setDigits(next);
              boxes.current[i - 1]?.focus();
            }
          }}
          className={cn(
            "h-14 w-full min-w-0 rounded-xl border bg-surface text-center text-2xl caret-accent font-semibold tabular-nums focus-visible:outline-2 focus-visible:outline-ring disabled:opacity-60",
            error
              ? "border-danger"
              : d
                ? "border-accent"
                : "border-border-strong",
          )}
        />
      ))}
    </div>
  );
}
