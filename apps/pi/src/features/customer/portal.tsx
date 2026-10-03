"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  AudioLines,
  CalendarClock,
  ChevronRight,
  CircleCheck,
  CreditCard,
  HelpCircle,
  ImageIcon,
  Inbox,
  LifeBuoy,
  LogOut,
  MessageCircle,
  MessageSquareWarning,
  Package,
  Play,
  Sparkles,
  UserRound,
} from "lucide-react";

import { ApiError, errorText } from "@/lib/api";
import {
  customerFile,
  customerGet,
  customerPost,
  type CustomerConversationDetail,
  type CustomerConversationItem,
  type CustomerIssue,
  type CustomerIssues,
  type CustomerMe,
  type CustomerMessage,
} from "@/lib/customer-api";
import {
  Badge,
  Button,
  Card,
  CardSection,
  EmptyState,
  ErrorState,
  Field,
  Input,
  LoadingBlock,
  Notice,
  Spinner,
} from "@/components/ui";

const ME = ["pi-customer", "me"] as const;
const LIST = ["pi-customer", "conversations"] as const;

function useMe() {
  return useQuery({
    queryKey: ME,
    queryFn: async () => {
      try {
        return await customerGet<CustomerMe>("/me");
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null;
        throw error;
      }
    },
    retry: false,
  });
}

function when(iso: string) {
  const date = new Date(iso);
  const today = new Date().toDateString() === date.toDateString();
  return today
    ? date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })
    : date.toLocaleDateString([], { day: "numeric", month: "short" });
}

/* ------------------------------------------------------------------ home */

export function CustomerHome() {
  const me = useMe();
  if (me.isPending) return <LoadingBlock rows={3} label="Loading" />;
  if (me.isError)
    return (
      <ErrorState message={errorText(me.error)} onRetry={() => me.refetch()} />
    );
  return me.data ? <Dashboard me={me.data} /> : <SignIn />;
}

function SignIn() {
  const client = useQueryClient();
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [step, setStep] = useState<"phone" | "code">("phone");
  const [wait, setWait] = useState(0);
  const codeInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (wait <= 0) return;
    const timer = setTimeout(() => setWait((w) => w - 1), 1000);
    return () => clearTimeout(timer);
  }, [wait]);

  const send = useMutation({
    mutationFn: () => customerPost("/code", { phone }),
    onSuccess: () => {
      setStep("code");
      setCode("");
      setWait(60);
      setTimeout(() => codeInput.current?.focus(), 50);
    },
  });
  const verify = useMutation({
    mutationFn: () => customerPost<CustomerMe>("/verify", { phone, code }),
    onSuccess: (me) => client.setQueryData(ME, me),
  });

  return (
    <div className="mx-auto w-full max-w-md">
      <div className="mb-6 text-center">
        <div className="mx-auto mb-4 flex size-14 items-center justify-center rounded-2xl bg-accent-soft text-accent-soft-foreground">
          <MessageCircle className="size-7" aria-hidden />
        </div>
        <h1 className="text-2xl font-semibold tracking-tight">PI Customer</h1>
        <p className="mt-2 text-[15px] text-muted-foreground">
          See your WhatsApp conversations with businesses, and where each of
          your requests stands.
        </p>
      </div>
      <Card>
        <CardSection className="space-y-5">
          {step === "phone" ? (
            <form
              className="space-y-5"
              onSubmit={(e) => {
                e.preventDefault();
                send.mutate();
              }}
            >
              <Field
                label="Your WhatsApp number"
                htmlFor="pc-phone"
                hint="With country code, e.g. +92 300 1234567"
                error={send.isError ? errorText(send.error) : null}
              >
                <Input
                  id="pc-phone"
                  type="tel"
                  inputMode="tel"
                  autoComplete="tel"
                  placeholder="+92 300 1234567"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  className="h-12"
                  required
                />
              </Field>
              <Button
                type="submit"
                size="lg"
                className="w-full"
                loading={send.isPending}
                disabled={phone.replace(/\D/g, "").length < 7}
              >
                Send code on WhatsApp
              </Button>
            </form>
          ) : (
            <form
              className="space-y-5"
              onSubmit={(e) => {
                e.preventDefault();
                verify.mutate();
              }}
            >
              <Notice tone="info" title="Check WhatsApp">
                If {phone} has messaged a business on WhatsApp in the last 24
                hours, a 6-digit code is on its way from that business. No code?
                Send any message to the business on WhatsApp, then send the code
                again.
              </Notice>
              <Field
                label="6-digit code"
                htmlFor="pc-code"
                error={verify.isError ? errorText(verify.error) : null}
              >
                <Input
                  id="pc-code"
                  ref={codeInput}
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  maxLength={6}
                  placeholder="••••••"
                  value={code}
                  onChange={(e) =>
                    setCode(e.target.value.replace(/\D/g, "").slice(0, 6))
                  }
                  className="h-12 text-center text-xl tracking-[0.5em]"
                  required
                />
              </Field>
              <Button
                type="submit"
                size="lg"
                className="w-full"
                loading={verify.isPending}
                disabled={code.length !== 6}
              >
                Open my conversations
              </Button>
              <div className="flex items-center justify-between text-sm">
                <button
                  type="button"
                  className="text-muted-foreground hover:text-foreground"
                  onClick={() => setStep("phone")}
                >
                  Change number
                </button>
                <button
                  type="button"
                  className="font-medium text-accent disabled:text-muted-foreground"
                  disabled={wait > 0 || send.isPending}
                  onClick={() => send.mutate()}
                >
                  {wait > 0 ? `Send again in ${wait}s` : "Send code again"}
                </button>
              </div>
            </form>
          )}
        </CardSection>
      </Card>
      <p className="mt-4 text-center text-xs text-muted-foreground">
        Only you can see your conversations. The code proves this number is
        yours; never share it.
      </p>
    </div>
  );
}

function Dashboard({ me }: { me: CustomerMe }) {
  const client = useQueryClient();
  const list = useQuery({
    queryKey: LIST,
    queryFn: () => customerGet<CustomerConversationItem[]>("/conversations"),
    refetchInterval: 20_000,
  });
  const signOut = useMutation({
    mutationFn: () => customerPost("/sign-out"),
    onSettled: () => {
      client.setQueryData(ME, null);
      client.removeQueries({ queryKey: ["pi-customer"] });
    },
  });
  const items = list.data ?? [];
  const open = items.reduce((n, c) => n + c.issues_open, 0);
  const withTeam = items.filter((c) => c.with_team).length;

  return (
    <div className="mx-auto w-full max-w-2xl space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm text-muted-foreground">
            Signed in as {me.phone}
          </p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">
            Your conversations
          </h1>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => signOut.mutate()}
          loading={signOut.isPending}
        >
          <LogOut className="size-4" aria-hidden />
          Sign out
        </Button>
      </header>

      {items.length > 0 && (
        <div className="grid grid-cols-3 gap-3">
          <Stat
            label="Businesses"
            value={new Set(items.map((c) => c.business)).size}
          />
          <Stat label="Open requests" value={open} />
          <Stat label="With a team" value={withTeam} />
        </div>
      )}

      {list.isPending ? (
        <LoadingBlock rows={3} label="Loading conversations" />
      ) : list.isError ? (
        <ErrorState
          message={errorText(list.error)}
          onRetry={() => list.refetch()}
        />
      ) : items.length === 0 ? (
        <Card>
          <EmptyState
            icon={<Inbox className="size-6" aria-hidden />}
            title="No conversations to show"
          >
            Conversations appear here when you chat with a business that uses Pi
            on WhatsApp.
          </EmptyState>
        </Card>
      ) : (
        <ul className="space-y-3">
          {items.map((c) => (
            <li key={c.id}>
              <Link
                href={`/customer/c/${c.id}`}
                className="block rounded-2xl border border-border bg-surface p-4 shadow-sm transition-colors hover:border-accent/40 hover:bg-accent-soft/30 focus-visible:outline-2 focus-visible:outline-ring"
              >
                <div className="flex items-start gap-3">
                  <Avatar name={c.business} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline justify-between gap-2">
                      <p className="truncate font-semibold">{c.business}</p>
                      <span className="shrink-0 text-xs text-muted-foreground">
                        {when(c.last_message_at)}
                      </span>
                    </div>
                    <p className="mt-0.5 line-clamp-2 text-sm text-muted-foreground">
                      {c.preview || "Conversation"}
                    </p>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {c.with_team && <Badge tone="info">With the team</Badge>}
                      {c.issues_open > 0 && (
                        <Badge tone="warning">
                          {c.issues_open} open{" "}
                          {c.issues_open === 1 ? "request" : "requests"}
                        </Badge>
                      )}
                      {c.issues_total > 0 && c.issues_open === 0 && (
                        <Badge tone="success">All sorted</Badge>
                      )}
                      {c.status === "closed" && <Badge>Closed</Badge>}
                    </div>
                  </div>
                  <ChevronRight
                    className="mt-1 size-4 shrink-0 text-muted-foreground"
                    aria-hidden
                  />
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-2xl border border-border bg-surface p-3 text-center shadow-sm">
      <p className="text-2xl font-semibold tabular-nums">{value}</p>
      <p className="text-xs text-muted-foreground">{label}</p>
    </div>
  );
}

function Avatar({ name }: { name: string }) {
  return (
    <span
      aria-hidden
      className="flex size-11 shrink-0 items-center justify-center rounded-full bg-accent-soft text-base font-semibold text-accent-soft-foreground"
    >
      {name.trim().charAt(0).toUpperCase() || "?"}
    </span>
  );
}

/* ---------------------------------------------------------- conversation */

export function CustomerConversation({ id }: { id: string }) {
  const me = useMe();
  if (me.isPending) return <LoadingBlock rows={4} label="Loading" />;
  if (!me.data) return <SignIn />;
  return <ConversationView id={id} />;
}

function ConversationView({ id }: { id: string }) {
  const client = useQueryClient();
  const detail = useQuery({
    queryKey: ["pi-customer", "conversation", id],
    queryFn: () =>
      customerGet<CustomerConversationDetail>(`/conversations/${id}`),
    refetchInterval: 15_000,
  });
  const team = useMutation({
    mutationFn: () => customerPost(`/conversations/${id}/team`),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["pi-customer"] });
    },
  });

  if (detail.isPending) return <LoadingBlock rows={4} label="Loading" />;
  if (detail.isError)
    return (
      <div className="mx-auto max-w-2xl space-y-4">
        <BackLink />
        <ErrorState
          message={errorText(detail.error)}
          onRetry={() => detail.refetch()}
        />
      </div>
    );
  const c = detail.data;
  return (
    <div className="mx-auto w-full max-w-2xl space-y-5">
      <BackLink />
      <header className="flex items-center gap-3">
        <Avatar name={c.business} />
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-xl font-semibold">{c.business}</h1>
          <p className="text-sm text-muted-foreground">{c.business_phone}</p>
        </div>
      </header>
      <div className="flex flex-wrap gap-2">
        {c.whatsapp_link && (
          <Button asChild size="sm">
            <a href={c.whatsapp_link} target="_blank" rel="noreferrer">
              <MessageCircle className="size-4" aria-hidden />
              Continue on WhatsApp
            </a>
          </Button>
        )}
        {c.with_team || team.isSuccess ? (
          <Badge tone="info" className="px-3 py-1.5">
            <UserRound className="size-3.5" aria-hidden />A person from the team
            will reply
          </Badge>
        ) : (
          <Button
            variant="secondary"
            size="sm"
            loading={team.isPending}
            onClick={() => team.mutate()}
          >
            <UserRound className="size-4" aria-hidden />
            Talk to a person
          </Button>
        )}
      </div>
      {team.isError && <ErrorState message={errorText(team.error)} />}

      <Requests id={id} initial={c.issues} detail={c} />

      <section aria-labelledby="pc-chat">
        <h2 id="pc-chat" className="mb-3 text-base font-semibold">
          Conversation
        </h2>
        <Card>
          <CardSection>
            <ol className="space-y-3" aria-label="Messages">
              {c.messages.map((m) => (
                <Bubble
                  key={m.id}
                  message={m}
                  conversationId={id}
                  business={c.business}
                />
              ))}
            </ol>
          </CardSection>
        </Card>
      </section>
    </div>
  );
}

function BackLink() {
  return (
    <Link
      href="/customer"
      className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
    >
      <ArrowLeft className="size-4" aria-hidden />
      All conversations
    </Link>
  );
}

const CATEGORY: Record<
  CustomerIssue["category"],
  { label: string; icon: typeof HelpCircle }
> = {
  inquiry: { label: "Question", icon: HelpCircle },
  order: { label: "Order", icon: Package },
  booking: { label: "Booking", icon: CalendarClock },
  payment: { label: "Payment", icon: CreditCard },
  complaint: { label: "Complaint", icon: MessageSquareWarning },
  support: { label: "Support", icon: LifeBuoy },
  other: { label: "Request", icon: Sparkles },
};

const STATUS: Record<
  CustomerIssue["status"],
  { label: string; tone: "warning" | "info" | "success" }
> = {
  open: { label: "In progress", tone: "warning" },
  with_team: { label: "With the team", tone: "info" },
  resolved: { label: "Sorted", tone: "success" },
};

function Requests({
  id,
  initial,
  detail,
}: {
  id: string;
  initial: CustomerConversationDetail["issues"];
  detail: CustomerConversationDetail;
}) {
  const issues = useQuery({
    queryKey: ["pi-customer", "issues", id, detail.last_message_at],
    queryFn: () => customerGet<CustomerIssues>(`/conversations/${id}/issues`),
    initialData: initial
      ? { available: true, at: initial.at, issues: initial.issues }
      : undefined,
    staleTime: Infinity,
  });
  const list = issues.data?.issues ?? [];
  return (
    <section aria-labelledby="pc-requests" className="space-y-3">
      <div className="flex items-center gap-2">
        <h2 id="pc-requests" className="text-base font-semibold">
          Your requests
        </h2>
        <Badge tone="accent">
          <Sparkles className="size-3" aria-hidden />
          Organised by Pi
        </Badge>
      </div>
      {issues.isPending ? (
        <Card>
          <CardSection>
            <Spinner label="Pi is organising your requests…" />
          </CardSection>
        </Card>
      ) : issues.isError || !issues.data?.available ? (
        <Notice tone="info">
          We couldn&apos;t organise your requests right now. Your full
          conversation is below.
        </Notice>
      ) : list.length === 0 ? (
        <Notice tone="info">No requests found in this conversation yet.</Notice>
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2">
          {list.map((issue, i) => {
            const category = CATEGORY[issue.category];
            const status = STATUS[issue.status];
            const Icon = category.icon;
            return (
              <li key={i}>
                <Card className="h-full">
                  <CardSection className="space-y-2 p-4 sm:p-4">
                    <div className="flex items-center justify-between gap-2">
                      <span className="inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                        <Icon className="size-3.5" aria-hidden />
                        {category.label}
                      </span>
                      <Badge tone={status.tone}>
                        {issue.status === "resolved" && (
                          <CircleCheck className="size-3" aria-hidden />
                        )}
                        {status.label}
                      </Badge>
                    </div>
                    <p className="font-semibold leading-snug">{issue.title}</p>
                    {issue.summary && (
                      <p className="text-sm text-foreground-secondary">
                        {issue.summary}
                      </p>
                    )}
                    {issue.next_step && issue.status !== "resolved" && (
                      <p className="rounded-lg bg-surface-muted px-3 py-2 text-[13px]">
                        <span className="font-medium">Next: </span>
                        {issue.next_step}
                      </p>
                    )}
                  </CardSection>
                </Card>
              </li>
            );
          })}
        </ul>
      )}
      {detail.requests.length > 0 && (
        <Card>
          <CardSection className="space-y-2 p-4 sm:p-4">
            <p className="text-sm font-semibold">Opened by the team</p>
            <ul className="space-y-2">
              {detail.requests.map((r, i) => (
                <li
                  key={i}
                  className="flex items-start justify-between gap-3 text-sm"
                >
                  <span>
                    {r.title}
                    {r.note && (
                      <span className="block text-xs text-muted-foreground">
                        {r.note}
                      </span>
                    )}
                  </span>
                  <Badge tone={r.status === "resolved" ? "success" : "info"}>
                    {r.status === "resolved" ? "Done" : "With the team"}
                  </Badge>
                </li>
              ))}
            </ul>
          </CardSection>
        </Card>
      )}
    </section>
  );
}

const SENDER: Record<CustomerMessage["from"], string> = {
  you: "You",
  assistant: "Pi assistant",
  team: "Team",
  business: "",
};

function Bubble({
  message,
  conversationId,
  business,
}: {
  message: CustomerMessage;
  conversationId: string;
  business: string;
}) {
  const mine = message.from === "you";
  if (
    message.from === "business" &&
    message.type === "text" &&
    !message.has_media
  )
    return (
      <li className="flex justify-center">
        <p className="max-w-[90%] rounded-full bg-surface-muted px-3 py-1 text-center text-xs text-muted-foreground">
          {message.body}
        </p>
      </li>
    );
  return (
    <li className={mine ? "flex justify-end" : "flex justify-start"}>
      <div
        className={
          "max-w-[85%] rounded-2xl px-3.5 py-2 text-[15px] " +
          (mine
            ? "rounded-br-md bg-accent text-accent-foreground"
            : "rounded-bl-md bg-surface-muted text-foreground")
        }
      >
        {!mine && (
          <p className="mb-0.5 text-xs font-medium opacity-75">
            {SENDER[message.from] || business}
          </p>
        )}
        {message.has_media && (
          <MediaPart
            message={message}
            conversationId={conversationId}
            mine={mine}
          />
        )}
        {message.body && <Formatted text={message.body} />}
        <p className="mt-1 text-right text-[11px] opacity-70">
          {when(message.at)}
        </p>
      </div>
    </li>
  );
}

function MediaPart({
  message,
  conversationId,
  mine,
}: {
  message: CustomerMessage;
  conversationId: string;
  mine: boolean;
}) {
  const [url, setUrl] = useState<string | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "failed">("idle");
  useEffect(
    () => () => {
      if (url) URL.revokeObjectURL(url);
    },
    [url],
  );
  async function load() {
    setState("loading");
    try {
      const blob = await customerFile(
        `/conversations/${conversationId}/messages/${message.id}/media`,
      );
      setUrl(URL.createObjectURL(blob));
      setState("idle");
    } catch {
      setState("failed");
    }
  }
  const audio = message.type === "audio";
  return (
    <div className="mb-1.5 space-y-1.5">
      {url ? (
        audio ? (
          <audio controls autoPlay src={url} className="h-9 w-64 max-w-full" />
        ) : message.type === "video" ? (
          <video controls src={url} className="max-h-72 w-full rounded-xl" />
        ) : (
          // eslint-disable-next-line @next/next/no-img-element -- a private blob URL
          <img
            src={url}
            alt="Your photo"
            className="max-h-72 w-full rounded-xl object-contain"
          />
        )
      ) : (
        <button
          type="button"
          onClick={load}
          disabled={state === "loading"}
          className={
            "inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-sm font-medium " +
            (mine ? "bg-white/20" : "bg-surface")
          }
        >
          {state === "loading" ? (
            <Spinner label="Loading" />
          ) : (
            <>
              {audio ? (
                <AudioLines className="size-4" aria-hidden />
              ) : (
                <ImageIcon className="size-4" aria-hidden />
              )}
              {audio
                ? "Voice note"
                : message.type === "video"
                  ? "Video"
                  : "Photo"}
              <Play className="size-3.5" aria-hidden />
            </>
          )}
        </button>
      )}
      {state === "failed" && (
        <p className="text-xs opacity-80">This file is no longer available.</p>
      )}
      {message.transcript && (
        <p className="text-[13px] italic opacity-85">“{message.transcript}”</p>
      )}
    </div>
  );
}

function Formatted({ text }: { text: string }) {
  const parts = text.split(
    /((?<!\w)(?:\*[^*\n]+\*|_[^_\n]+_|~[^~\n]+~)(?!\w))/g,
  );
  return (
    <p className="whitespace-pre-wrap break-words">
      {parts.map((part, i) => {
        const inner = part.slice(1, -1);
        if (part.length > 2 && part.startsWith("*") && part.endsWith("*"))
          return <strong key={i}>{inner}</strong>;
        if (part.length > 2 && part.startsWith("_") && part.endsWith("_"))
          return <em key={i}>{inner}</em>;
        if (part.length > 2 && part.startsWith("~") && part.endsWith("~"))
          return <s key={i}>{inner}</s>;
        return part;
      })}
    </p>
  );
}
