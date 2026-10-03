"use client";

import { useQuery } from "@tanstack/react-query";
import { Bell, CheckCircle2, Circle, Clock, Phone } from "lucide-react";
import Link from "next/link";
import * as React from "react";

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
  Switch,
  Textarea,
  cn,
} from "@/components/ui";
import { del, errorText, get, post, put } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { useAction, useBusinessKey, useCan } from "@/lib/session";

// ------------------------------------------------------------------ WhatsApp access

export interface WhatsAppAccessView {
  ok: boolean;
  reason: string;
  message: string;
  steps: { key: string; label: string; done: boolean }[];
  held: { display_phone_number: string; held_until: string } | null;
}

const STEP_LINK: Record<string, { href: string; label: string }> = {
  details: { href: "/settings/business-review", label: "Send details" },
  approval: { href: "/settings/business-review", label: "See review" },
  payment: { href: "/settings/billing", label: "Choose a plan" },
};

export function useWhatsAppAccess() {
  const key = useBusinessKey();
  return useQuery({
    queryKey: key(["whatsapp-access"]),
    queryFn: () => get<WhatsAppAccessView>("/whatsapp/access"),
  });
}

/** The three steps before WhatsApp connects, and the number held meanwhile. */
export function WhatsAppAccess() {
  const access = useWhatsAppAccess();
  const release = useAction(() => del("/whatsapp/numbers/hold"), {
    invalidate: [["whatsapp-access"], ["pool-numbers"]],
    success: "The number went back to the pool.",
  });
  if (access.isPending) return <LoadingBlock rows={1} />;
  if (access.isError || access.data.ok) return null;
  const next = access.data.steps.find((s) => !s.done);
  return (
    <Card>
      <CardSection className="space-y-4">
        <div>
          <h3 className="font-semibold">Before your number connects</h3>
          <p className="text-sm text-muted-foreground">
            {access.data.message} You can pick your number now; we hold it for
            you and connect it automatically.
          </p>
        </div>
        <ol className="grid gap-2 sm:grid-cols-3" aria-label="Steps">
          {access.data.steps.map((step, index) => (
            <li
              key={step.key}
              className={cn(
                "flex items-start gap-2 rounded-lg border p-3 text-sm",
                step.done
                  ? "border-accent/40 bg-accent-soft"
                  : "border-border bg-surface",
              )}
            >
              {step.done ? (
                <CheckCircle2
                  className="mt-0.5 size-4 text-accent"
                  aria-hidden
                />
              ) : (
                <Circle
                  className="mt-0.5 size-4 text-muted-foreground"
                  aria-hidden
                />
              )}
              <span className="min-w-0 flex-1">
                <span className="block font-medium">
                  {index + 1}. {step.label}
                </span>
                {!step.done && next?.key === step.key && STEP_LINK[step.key] ? (
                  <Link
                    href={STEP_LINK[step.key].href}
                    className="text-accent underline-offset-2 hover:underline"
                  >
                    {STEP_LINK[step.key].label}
                  </Link>
                ) : (
                  <span className="text-muted-foreground">
                    {step.done ? "Done" : "Waiting"}
                  </span>
                )}
              </span>
            </li>
          ))}
        </ol>
        {access.data.held ? (
          <Notice
            tone="info"
            title={`${access.data.held.display_phone_number} is held for you`}
            action={
              <Button
                size="sm"
                variant="secondary"
                loading={release.isPending}
                onClick={() => release.mutate(undefined)}
              >
                Release
              </Button>
            }
          >
            It connects as soon as the steps above are done. Held until{" "}
            {dateTime(access.data.held.held_until)}.
          </Notice>
        ) : null}
      </CardSection>
    </Card>
  );
}

// ------------------------------------------------------------------ business review

interface Review {
  status:
    "not_started" | "submitted" | "changes_requested" | "approved" | "rejected";
  details: Record<string, string>;
  missing: string[];
  editable: boolean;
  submitted_at: string | null;
  decided_at: string | null;
  note: string;
}

const REVIEW_STATE: Record<
  Review["status"],
  {
    label: string;
    tone: "neutral" | "accent" | "warning" | "success" | "danger";
  }
> = {
  not_started: { label: "Not sent", tone: "neutral" },
  submitted: { label: "In review", tone: "accent" },
  changes_requested: { label: "Changes needed", tone: "warning" },
  approved: { label: "Approved", tone: "success" },
  rejected: { label: "Not approved", tone: "danger" },
};

const FIELDS: {
  key: string;
  label: string;
  hint?: string;
  optional?: boolean;
  long?: boolean;
  placeholder?: string;
}[] = [
  {
    key: "legal_name",
    label: "Business name",
    hint: "As customers and invoices know it.",
  },
  {
    key: "category",
    label: "Type of business",
    optional: true,
    placeholder: "e.g. Clothing, Salon, Clinic",
  },
  { key: "address", label: "Business address" },
  { key: "city", label: "City" },
  {
    key: "contact_phone",
    label: "Contact phone",
    placeholder: "+92 300 1234567",
  },
  {
    key: "website",
    label: "Website or social page",
    optional: true,
    placeholder: "https://",
  },
  {
    key: "about",
    label: "What you sell",
    long: true,
    hint: "A sentence or two: your products or services and who buys them.",
  },
];

export function BusinessReview() {
  const key = useBusinessKey();
  const canEdit = useCan()("pi.settings.manage");
  const review = useQuery({
    queryKey: key(["business-review"]),
    queryFn: () => get<Review>("/business-review"),
  });
  // Local edits on top of what the server has.
  const [edits, setEdits] = React.useState<Record<string, string>>({});
  const form: Record<string, string> = {
    ...(review.data?.details ?? {}),
    ...edits,
  };
  const setForm = (next: Record<string, string>) => setEdits(next);
  const save = useAction(
    (body: Record<string, string>) => put<Review>("/business-review", body),
    {
      invalidate: [["business-review"]],
    },
  );
  const submit = useAction(
    async (body: Record<string, string>) => {
      await put("/business-review", body);
      return post<Review>("/business-review/submit");
    },
    {
      invalidate: [["business-review"], ["whatsapp-access"], ["notifications"]],
      success: "Sent. We'll let you know as soon as it's reviewed.",
    },
  );
  if (review.isPending) return <LoadingBlock rows={4} />;
  if (review.isError)
    return (
      <ErrorState
        message={errorText(review.error)}
        onRetry={() => review.refetch()}
      />
    );
  const data = review.data;
  const state = REVIEW_STATE[data.status];
  const editable = data.editable && canEdit;
  return (
    <div className="space-y-5">
      <Card>
        <CardSection className="flex flex-wrap items-center gap-3">
          <Badge tone={state.tone}>{state.label}</Badge>
          <p className="min-w-0 flex-1 basis-56 text-sm text-muted-foreground">
            {data.status === "not_started"
              ? "The Pi team checks every business before its WhatsApp number goes live. It usually takes one working day."
              : data.status === "submitted"
                ? `Sent ${data.submitted_at ? dateTime(data.submitted_at) : ""}. You'll get a notification when it's reviewed.`
                : data.status === "approved"
                  ? "Your business is approved. Next: choose a plan and your WhatsApp number."
                  : data.status === "changes_requested"
                    ? "Please update the details below and send them again."
                    : "Contact the Pi team if you think this is a mistake."}
          </p>
          {data.status === "approved" ? (
            <Button asChild size="sm">
              <Link href="/settings/billing">Choose a plan</Link>
            </Button>
          ) : null}
        </CardSection>
        {data.note ? (
          <CardSection className="border-t border-border">
            <Notice
              tone={data.status === "rejected" ? "danger" : "warning"}
              title="Note from the Pi team"
            >
              {data.note}
            </Notice>
          </CardSection>
        ) : null}
      </Card>
      <Card>
        <CardSection>
          <form
            className="grid gap-4 sm:grid-cols-2"
            onSubmit={(event) => {
              event.preventDefault();
              submit.mutate(form);
            }}
          >
            {FIELDS.map((f) => (
              <div key={f.key} className={f.long ? "sm:col-span-2" : undefined}>
                <Field
                  label={f.label}
                  hint={f.hint}
                  optional={f.optional}
                  htmlFor={`review-${f.key}`}
                >
                  {f.long ? (
                    <Textarea
                      id={`review-${f.key}`}
                      value={form[f.key] ?? ""}
                      maxLength={600}
                      disabled={!editable}
                      onChange={(e) =>
                        setForm({ ...form, [f.key]: e.target.value })
                      }
                    />
                  ) : (
                    <Input
                      id={`review-${f.key}`}
                      value={form[f.key] ?? ""}
                      placeholder={f.placeholder}
                      disabled={!editable}
                      onChange={(e) =>
                        setForm({ ...form, [f.key]: e.target.value })
                      }
                    />
                  )}
                </Field>
              </div>
            ))}
            {editable ? (
              <div className="flex flex-wrap gap-2 sm:col-span-2">
                <Button type="submit" loading={submit.isPending}>
                  Send for review
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  loading={save.isPending}
                  onClick={() => save.mutate(form)}
                >
                  Save draft
                </Button>
              </div>
            ) : null}
          </form>
        </CardSection>
      </Card>
    </div>
  );
}

// ------------------------------------------------------------------ notifications

interface NotificationItem {
  id: string;
  kind: string;
  severity: string;
  title: string;
  body: string;
  link: string | null;
  read: boolean;
  created_at: string;
}

export function NotificationBell({ className }: { className?: string }) {
  const key = useBusinessKey();
  const unread = useQuery({
    queryKey: key(["notifications", "unread"]),
    queryFn: () => get<{ unread: number }>("/notifications/unread-count"),
    refetchInterval: 60_000,
  });
  const count = unread.data?.unread ?? 0;
  return (
    <Link
      href="/notifications"
      aria-label={count ? `Notifications, ${count} unread` : "Notifications"}
      className={cn(
        "relative inline-flex size-10 items-center justify-center rounded-lg text-foreground-secondary hover:bg-surface-muted hover:text-foreground",
        className,
      )}
    >
      <Bell className="size-5" aria-hidden />
      {count ? (
        <span className="absolute end-1 top-1 min-w-4 rounded-full bg-accent px-1 text-center text-[10px] font-semibold leading-4 text-accent-foreground">
          {count > 9 ? "9+" : count}
        </span>
      ) : null}
    </Link>
  );
}

export function NotificationsList() {
  const key = useBusinessKey();
  const list = useQuery({
    queryKey: key(["notifications", "list"]),
    queryFn: () =>
      get<{ items: NotificationItem[]; total: number }>(
        "/notifications?page_size=50",
      ),
  });
  const markAll = useAction(() => post("/notifications/read", {}), {
    invalidate: [["notifications"]],
  });
  const markOne = useAction(
    (id: string) => post("/notifications/read", { ids: [id] }),
    {
      invalidate: [["notifications"]],
      silentError: true,
    },
  );
  if (list.isPending) return <LoadingBlock rows={4} />;
  if (list.isError)
    return (
      <ErrorState
        message={errorText(list.error)}
        onRetry={() => list.refetch()}
      />
    );
  if (!list.data.items.length)
    return (
      <EmptyState
        icon={<Bell className="size-5" aria-hidden />}
        title="Nothing yet"
      >
        Updates about your review, plan and WhatsApp number show up here.
      </EmptyState>
    );
  const unread = list.data.items.some((n) => !n.read);
  return (
    <div className="space-y-3">
      {unread ? (
        <div className="flex justify-end">
          <Button
            size="sm"
            variant="secondary"
            loading={markAll.isPending}
            onClick={() => markAll.mutate(undefined)}
          >
            Mark all as read
          </Button>
        </div>
      ) : null}
      <Card>
        <ul className="divide-y divide-border">
          {list.data.items.map((n) => {
            const body = (
              <div className="flex gap-3 px-4 py-3">
                <span
                  className={cn(
                    "mt-1.5 size-2 shrink-0 rounded-full",
                    n.read
                      ? "bg-transparent"
                      : n.severity === "warning"
                        ? "bg-warning"
                        : "bg-accent",
                  )}
                  aria-hidden
                />
                <span className="min-w-0 flex-1">
                  <span
                    className={cn(
                      "block text-sm",
                      n.read ? "font-medium" : "font-semibold",
                    )}
                  >
                    {n.title}
                  </span>
                  {n.body ? (
                    <span className="mt-0.5 block whitespace-pre-line text-sm text-muted-foreground">
                      {n.body}
                    </span>
                  ) : null}
                  <span className="mt-1 flex items-center gap-1 text-xs text-muted-foreground">
                    <Clock className="size-3" aria-hidden />
                    {dateTime(n.created_at)}
                    {!n.read ? <span className="sr-only">, unread</span> : null}
                  </span>
                </span>
              </div>
            );
            return (
              <li key={n.id}>
                {n.link ? (
                  <Link
                    href={n.link}
                    className="block hover:bg-surface-muted"
                    onClick={() => !n.read && markOne.mutate(n.id)}
                  >
                    {body}
                  </Link>
                ) : (
                  <button
                    type="button"
                    className="block w-full text-start hover:bg-surface-muted"
                    onClick={() => !n.read && markOne.mutate(n.id)}
                  >
                    {body}
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      </Card>
    </div>
  );
}

interface Category {
  key: string;
  label: string;
  email: boolean;
  in_app: boolean;
}

const CATEGORY_HINT: Record<string, string> = {
  review: "Your business review: received, approved, changes needed.",
  billing: "Plan activated and payments received.",
  whatsapp: "Your number held, connected, or released.",
  trial: "A reminder before your trial ends.",
};

export function NotificationSettings() {
  const key = useBusinessKey();
  const canEdit = useCan()("pi.settings.manage");
  const prefs = useQuery({
    queryKey: key(["notification-settings"]),
    queryFn: () => get<{ categories: Category[] }>("/notification-settings"),
  });
  const save = useAction(
    (email: Record<string, boolean>) =>
      put("/notification-settings", { email }),
    { invalidate: [["notification-settings"]], success: "Saved." },
  );
  if (prefs.isPending) return <LoadingBlock rows={3} />;
  if (prefs.isError)
    return (
      <ErrorState
        message={errorText(prefs.error)}
        onRetry={() => prefs.refetch()}
      />
    );
  return (
    <Card>
      <CardSection className="space-y-1">
        <h2 className="font-semibold">Email me about</h2>
        <p className="text-sm text-muted-foreground">
          Everything always appears under the bell. Email goes to the business
          owner.
        </p>
      </CardSection>
      <ul className="divide-y divide-border border-t border-border">
        {prefs.data.categories.map((c) => (
          <li key={c.key} className="flex items-center gap-4 px-5 py-4">
            <span className="min-w-0 flex-1">
              <span className="block text-sm font-medium">{c.label}</span>
              <span className="block text-sm text-muted-foreground">
                {CATEGORY_HINT[c.key]}
              </span>
            </span>
            <Switch
              id={`email-${c.key}`}
              label={`Email about ${c.label}`}
              checked={c.email}
              disabled={!canEdit || save.isPending}
              onCheckedChange={(value) => save.mutate({ [c.key]: value })}
            />
          </li>
        ))}
      </ul>
    </Card>
  );
}

export function HeldNumberHint({ number }: { number: string }) {
  return (
    <p className="flex items-center gap-2 text-sm text-muted-foreground">
      <Phone className="size-4 text-accent" aria-hidden />
      {number} is held for you.
    </p>
  );
}
