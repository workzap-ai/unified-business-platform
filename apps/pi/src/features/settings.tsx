"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Banknote,
  Building2,
  CreditCard,
  ExternalLink,
  HeartPulse,
  MessageCircle,
  Pause,
  Play,
  ShieldCheck,
  UserPlus,
  Users,
} from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";

import { SubNav } from "@/components/shell";
import {
  Badge,
  Button,
  Card,
  CardSection,
  Dialog,
  DialogContent,
  ErrorState,
  Field,
  Input,
  LoadingBlock,
  Notice,
  PageHeader,
  Select,
  Spinner,
} from "@/components/ui";
import { BusinessReview, NotificationSettings } from "@/features/journey";
import { SetupCenter } from "@/features/setup-center";
import { WhatsAppConnect, useAccount } from "@/features/setup";
import { GettingPaid } from "@/features/getting-paid";
import { ManualBilling } from "@/features/manual-billing";
import product from "@/components/product.module.css";
import { del, errorText, get, post, put } from "@/lib/api";
import {
  REASON_LABEL,
  STATE_LABEL,
  count,
  date,
  dateTime,
  money,
} from "@/lib/format";
import { useAction, useBusinessKey, useCan, useSession } from "@/lib/session";
import type { BillingView, ConnectionView } from "@/lib/types";

const SECTIONS = [
  { href: "/settings/setup", label: "Setup" },
  { href: "/settings/business-review", label: "Business review" },
  { href: "/settings/whatsapp", label: "WhatsApp" },
  { href: "/settings/team", label: "Team and access" },
  { href: "/settings/billing", label: "Plan and billing" },
  { href: "/settings/payments", label: "Getting paid" },
  { href: "/settings/business", label: "Business" },
  { href: "/settings/notifications", label: "Notifications" },
];

export function BusinessReviewPage() {
  return (
    <Shell
      title="Business review"
      description="Tell us about your business. The Pi team approves it before your WhatsApp number goes live."
    >
      <BusinessReview />
    </Shell>
  );
}

export function NotificationSettingsPage() {
  return (
    <Shell
      title="Notifications"
      description="What Pi tells you about, and what also comes by email."
    >
      <NotificationSettings />
    </Shell>
  );
}

export function SetupCenterPage() {
  return (
    <Shell
      title="Setup"
      description="Every tool Pi can use, what's ready, and where to fix what isn't."
    >
      <SetupCenter />
    </Shell>
  );
}

export function PaymentsPage() {
  return (
    <Shell
      title="Getting paid"
      description="How your customers pay you: card, Pakistani bank transfer, mobile wallet or cash."
    >
      <GettingPaid />
    </Shell>
  );
}

function Shell({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <PageHeader title={title} description={description} />
      <SubNav items={SECTIONS} />
      {children}
    </div>
  );
}

export function SettingsOverview() {
  const cards = [
    {
      href: "/settings/business-review",
      icon: ShieldCheck,
      title: "Business review",
      body: "Approval by the Pi team before WhatsApp goes live.",
    },
    {
      href: "/settings/whatsapp",
      icon: MessageCircle,
      title: "WhatsApp",
      body: "Your connected number and its health.",
    },
    {
      href: "/settings/team",
      icon: Users,
      title: "Team and access",
      body: "Who can see and do what.",
    },
    {
      href: "/settings/billing",
      icon: CreditCard,
      title: "Plan and billing",
      body: "Your plan, usage and invoices.",
    },
    {
      href: "/settings/payments",
      icon: Banknote,
      title: "Getting paid",
      body: "Card, bank transfer, wallet and cash payments from customers.",
    },
    {
      href: "/settings/business",
      icon: Building2,
      title: "Business",
      body: "Name, hours and pausing Pi.",
    },
  ];
  return (
    <div>
      <PageHeader
        title="Everything in its place"
        description="Your connections, your people and the details that keep Pi running."
      />
      <div className={`grid gap-4 sm:grid-cols-2 ${product.overviewCards}`}>
        {cards.map(({ href, icon: Icon, title, body }) => (
          <Link key={href} href={href} className="group rounded-xl">
            <Card className="h-full transition-colors group-hover:border-accent/40">
              <CardSection className="flex gap-4">
                <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent-soft-foreground">
                  <Icon className="size-5" aria-hidden />
                </div>
                <div>
                  <h2 className="font-semibold">{title}</h2>
                  <p className="text-sm text-muted-foreground">{body}</p>
                </div>
              </CardSection>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}

const CONNECTION_LABEL: Record<
  ConnectionView["status"],
  [string, "neutral" | "success" | "warning" | "danger" | "info"]
> = {
  draft: ["Not connected", "neutral"],
  setup_pending: ["Waiting for you to finish", "info"],
  connected: ["Connected", "success"],
  action_required: ["Needs attention", "danger"],
  disconnected: ["Disconnected", "danger"],
};

export function WhatsAppPage() {
  const account = useAccount();
  const can = useCan();
  const key = useBusinessKey();
  const [confirmOpen, setConfirmOpen] = React.useState(false);
  const status = useQuery({
    queryKey: key(["whatsapp"]),
    queryFn: () =>
      get<{
        production: ConnectionView;
        test: ConnectionView;
        provider_available: boolean;
      }>("/whatsapp"),
  });
  const health = useAction(
    () =>
      post<ConnectionView>("/whatsapp/health", { environment: "production" }),
    {
      invalidate: [["whatsapp"]],
      success: "Health check finished",
    },
  );
  const disconnect = useAction(
    () =>
      post<ConnectionView>("/whatsapp/disconnect", {
        environment: "production",
        remove_from_provider: false,
      }),
    {
      invalidate: [["whatsapp"], ["account"], ["home"]],
      success: "Disconnected. Pi has stopped replying.",
      onSuccess: () => setConfirmOpen(false),
    },
  );
  return (
    <Shell title="WhatsApp" description="The number Pi replies from.">
      {account.isPending || status.isPending ? (
        <LoadingBlock rows={2} />
      ) : account.isError ? (
        <ErrorState
          message={errorText(account.error)}
          onRetry={() => account.refetch()}
        />
      ) : status.isError ? (
        <ErrorState
          message={errorText(status.error)}
          onRetry={() => status.refetch()}
        />
      ) : (
        <div className="space-y-6">
          <Card>
            <CardSection className="space-y-4">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="font-semibold">Your number</h2>
                <Badge
                  tone={CONNECTION_LABEL[status.data.production.status][1]}
                >
                  {CONNECTION_LABEL[status.data.production.status][0]}
                </Badge>
              </div>
              {status.data.production.status === "connected" ? (
                <>
                  <p className="text-2xl font-semibold tabular-nums">
                    {status.data.production.display_phone_number}
                  </p>
                  {status.data.production.health ? (
                    <div className="text-sm">
                      <p>
                        Health:{" "}
                        <Badge
                          tone={
                            status.data.production.health.status === "healthy"
                              ? "success"
                              : "warning"
                          }
                        >
                          {status.data.production.health.status}
                        </Badge>
                        <span className="ms-2 text-muted-foreground">
                          checked{" "}
                          {dateTime(status.data.production.health_checked_at)}
                        </span>
                      </p>
                    </div>
                  ) : null}
                  {can("pi.whatsapp.manage") ? (
                    <div className="flex flex-wrap gap-2">
                      <Button
                        variant="secondary"
                        loading={health.isPending}
                        onClick={() => health.mutate(undefined)}
                      >
                        <HeartPulse className="size-4" aria-hidden /> Check
                        health
                      </Button>
                      <Button
                        variant="danger"
                        onClick={() => setConfirmOpen(true)}
                      >
                        Disconnect
                      </Button>
                    </div>
                  ) : null}
                </>
              ) : can("pi.whatsapp.manage") ? (
                <WhatsAppConnect account={account.data} />
              ) : (
                <Notice tone="info">
                  Ask your business owner to connect WhatsApp.
                </Notice>
              )}
            </CardSection>
          </Card>
          <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
            <DialogContent
              title="Disconnect WhatsApp?"
              description="Pi will stop replying on this number straight away. Your conversations and customers are kept, and you can reconnect later."
            >
              <div className="flex justify-end gap-2">
                <Button variant="ghost" onClick={() => setConfirmOpen(false)}>
                  Keep connected
                </Button>
                <Button
                  variant="danger"
                  loading={disconnect.isPending}
                  onClick={() => disconnect.mutate(undefined)}
                >
                  Disconnect
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        </div>
      )}
    </Shell>
  );
}

export function WhatsAppConnectedPage() {
  const params = useSearchParams();
  const router = useRouter();
  const failed =
    params.get("failed") === "1" ||
    (params.get("status") && params.get("status") !== "completed");
  const environment =
    params.get("environment") === "test" ? "test" : "production";
  // The redirect's number is only a hint; the server confirms ownership with the provider.
  const hint = params.get("phone_number_id");
  const [state, setState] = React.useState<
    "checking" | "connected" | "pending" | "failed" | "error"
  >(failed ? "failed" : "checking");
  const [message, setMessage] = React.useState("");
  React.useEffect(() => {
    if (failed) return;
    let cancelled = false;
    let attempts = 0;
    async function check() {
      try {
        const view = await post<ConnectionView>("/whatsapp/confirm", {
          environment,
          phone_number_id: hint && /^[0-9]{5,32}$/.test(hint) ? hint : null,
        });
        if (cancelled) return;
        if (view.status === "connected") {
          setState("connected");
          return;
        }
        attempts += 1;
        if (attempts < 6) setTimeout(check, 4000);
        else setState("pending");
      } catch (err) {
        if (!cancelled) {
          setState("error");
          setMessage(errorText(err));
        }
      }
    }
    void check();
    return () => {
      cancelled = true;
    };
  }, [failed, environment, hint]);
  return (
    <div className="mx-auto max-w-lg py-8">
      <Card>
        <CardSection className="space-y-4 text-center">
          {state === "checking" ? (
            <Spinner label="Confirming your number with WhatsApp…" />
          ) : null}
          {state === "connected" ? (
            <>
              <ShieldCheck
                className="mx-auto size-10 text-success"
                aria-hidden
              />
              <h1 className="text-xl font-semibold">WhatsApp is connected</h1>
              <Button onClick={() => router.push("/setup?step=4")}>
                Continue setup
              </Button>
            </>
          ) : null}
          {state === "pending" ? (
            <Notice tone="info" title="Still finishing">
              WhatsApp is still setting up your number. This can take a few
              minutes. We&apos;ll update your setup page automatically.
            </Notice>
          ) : null}
          {state === "failed" ? (
            <Notice
              tone="warning"
              title="The connection wasn't completed"
              action={
                <Button onClick={() => router.push("/setup?step=3")}>
                  Try again
                </Button>
              }
            >
              Nothing was changed. You can try again, or choose &ldquo;Help me
              set up&rdquo;.
            </Notice>
          ) : null}
          {state === "error" ? (
            <ErrorState
              message={message}
              onRetry={() => window.location.reload()}
            />
          ) : null}
        </CardSection>
      </Card>
    </div>
  );
}

interface TeamView {
  members: {
    membership_id: string;
    user_id: string;
    email: string;
    display_name: string;
    status: string;
    roles: string[];
    joined_at: string;
  }[];
  roles: {
    key: string;
    name: string;
    description: string;
    permissions: { key: string; label: string; group: string }[];
  }[];
}

function InviteDialog({ roles }: { roles: TeamView["roles"] }) {
  const [open, setOpen] = React.useState(false);
  const [form, setForm] = React.useState({
    email: "",
    display_name: "",
    role: "member",
    temporary_password: "",
  });
  const invite = useAction(
    () =>
      post("/team", {
        ...form,
        temporary_password: form.temporary_password || null,
      }),
    {
      invalidate: [["team"]],
      success: "Added. Share the temporary password with them privately.",
      onSuccess: () => {
        setOpen(false);
        setForm({
          email: "",
          display_name: "",
          role: "member",
          temporary_password: "",
        });
      },
    },
  );
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Button onClick={() => setOpen(true)}>
        <UserPlus className="size-4" aria-hidden /> Add a person
      </Button>
      <DialogContent
        title="Add someone to your team"
        description="They sign in to Pi with their email."
      >
        <div className="space-y-4">
          <Field label="Name" htmlFor="inv-name">
            <Input
              id="inv-name"
              value={form.display_name}
              onChange={(e) =>
                setForm((f) => ({ ...f, display_name: e.target.value }))
              }
            />
          </Field>
          <Field label="Email" htmlFor="inv-email">
            <Input
              id="inv-email"
              type="email"
              value={form.email}
              onChange={(e) =>
                setForm((f) => ({ ...f, email: e.target.value }))
              }
            />
          </Field>
          <Field
            label="Role"
            htmlFor="inv-role"
            hint={roles.find((r) => r.key === form.role)?.description}
          >
            <Select
              id="inv-role"
              value={form.role}
              onChange={(e) => setForm((f) => ({ ...f, role: e.target.value }))}
            >
              {roles
                .filter((r) => r.key !== "owner")
                .map((r) => (
                  <option key={r.key} value={r.key}>
                    {r.name}
                  </option>
                ))}
            </Select>
          </Field>
          <Field
            label="Temporary password"
            htmlFor="inv-pw"
            hint="Needed only if they don't have a Pi account yet. At least 12 characters."
            optional
          >
            <Input
              id="inv-pw"
              type="password"
              autoComplete="new-password"
              value={form.temporary_password}
              onChange={(e) =>
                setForm((f) => ({ ...f, temporary_password: e.target.value }))
              }
            />
          </Field>
          <Button
            className="w-full"
            loading={invite.isPending}
            disabled={!form.email || !form.display_name}
            onClick={() => invite.mutate(undefined)}
          >
            Add to team
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function RoleDetails({ roles }: { roles: TeamView["roles"] }) {
  return (
    <details className="rounded-lg border border-border bg-surface p-4 text-sm">
      <summary className="cursor-pointer font-medium">
        What each role can do
      </summary>
      <div className="mt-3 grid gap-4 sm:grid-cols-2">
        {roles.map((role) => (
          <div key={role.key}>
            <p className="font-medium">{role.name}</p>
            <p className="text-muted-foreground">{role.description}</p>
            <ul className="mt-1 list-disc ps-5 text-xs text-muted-foreground">
              {role.permissions.slice(0, 12).map((p) => (
                <li key={p.key}>{p.label}</li>
              ))}
              {role.permissions.length > 12 ? (
                <li>and {role.permissions.length - 12} more</li>
              ) : null}
            </ul>
          </div>
        ))}
      </div>
    </details>
  );
}

function SupportAccess() {
  const key = useBusinessKey();
  const can = useCan();
  const grants = useQuery({
    queryKey: key(["support-access"]),
    queryFn: () =>
      get<{
        grants: {
          id: string;
          scope: string;
          status: string;
          reason: string;
          requested_by: string;
          expires_at: string | null;
        }[];
      }>("/account/support-access"),
  });
  const decide = useAction(
    ({
      id,
      action,
    }: {
      id: string;
      action: "approve" | "decline" | "revoke";
    }) => post(`/account/support-access/${id}/${action}`),
    {
      invalidate: [["support-access"]],
      success: "Updated",
    },
  );
  const SCOPE: Record<string, string> = {
    configuration: "Prepare your settings and knowledge",
    conversations: "Read your customer conversations",
    full_support: "Read and reply to conversations",
  };
  return (
    <Card>
      <CardSection className="space-y-3">
        <h2 className="flex items-center gap-2 font-semibold">
          <ShieldCheck className="size-4 text-accent" aria-hidden /> Support
          access
        </h2>
        <p className="text-sm text-muted-foreground">
          Our support team can only see your business when you allow it. Every
          access is recorded.
        </p>
        {grants.isPending ? (
          <LoadingBlock rows={1} />
        ) : grants.isError ? (
          <ErrorState
            message={errorText(grants.error)}
            onRetry={() => grants.refetch()}
          />
        ) : grants.data.grants.length ? (
          <ul className="divide-y divide-border">
            {grants.data.grants.map((g) => (
              <li
                key={g.id}
                className="flex flex-wrap items-center gap-2 py-3 text-sm"
              >
                <span className="min-w-0 flex-1">
                  <span className="font-medium">
                    {SCOPE[g.scope] ?? g.scope}
                  </span>
                  <span className="block text-muted-foreground">
                    {g.reason}
                    {g.expires_at ? ` · until ${date(g.expires_at)}` : ""}
                  </span>
                </span>
                <Badge
                  tone={
                    g.status === "active"
                      ? "success"
                      : g.status === "requested"
                        ? "warning"
                        : "neutral"
                  }
                >
                  {g.status}
                </Badge>
                {can("pi.support.grant") && g.status === "requested" ? (
                  <>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() =>
                        decide.mutate({ id: g.id, action: "decline" })
                      }
                    >
                      Decline
                    </Button>
                    <Button
                      size="sm"
                      onClick={() =>
                        decide.mutate({ id: g.id, action: "approve" })
                      }
                    >
                      Allow
                    </Button>
                  </>
                ) : null}
                {can("pi.support.grant") && g.status === "active" ? (
                  <Button
                    size="sm"
                    variant="danger"
                    onClick={() =>
                      decide.mutate({ id: g.id, action: "revoke" })
                    }
                  >
                    Revoke
                  </Button>
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">
            No access has been requested.
          </p>
        )}
      </CardSection>
    </Card>
  );
}

export function TeamPage() {
  const key = useBusinessKey();
  const can = useCan();
  const { data: session } = useSession();
  const team = useQuery({
    queryKey: key(["team"]),
    queryFn: () => get<TeamView>("/team"),
    enabled: can("admin.members.read"),
  });
  const change = useAction(
    ({ id, role }: { id: string; role: string }) =>
      put(`/team/${id}`, { role }),
    { invalidate: [["team"]], success: "Role updated" },
  );
  const remove = useAction((id: string) => del(`/team/${id}`), {
    invalidate: [["team"]],
    success: "Removed from your team",
  });
  return (
    <Shell
      title="Team and access"
      description="Give each person the access they need — nothing more."
    >
      <div className="space-y-6">
        {!can("admin.members.read") ? (
          <Notice tone="info">Only owners and admins manage the team.</Notice>
        ) : team.isPending ? (
          <LoadingBlock rows={3} />
        ) : team.isError ? (
          <ErrorState
            message={errorText(team.error)}
            onRetry={() => team.refetch()}
          />
        ) : (
          <>
            <div className="flex justify-end">
              {can("admin.members.manage") ? (
                <InviteDialog roles={team.data.roles} />
              ) : null}
            </div>
            <Card>
              <ul className="divide-y divide-border">
                {team.data.members.map((m) => {
                  const role = m.roles[0] ?? "";
                  const self = m.user_id === session?.user.id;
                  return (
                    <li
                      key={m.membership_id}
                      className="flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:px-5"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="truncate font-medium">
                          {m.display_name}
                          {self ? " (you)" : ""}
                        </p>
                        <p className="truncate text-sm text-muted-foreground">
                          {m.email}
                        </p>
                      </div>
                      {can("admin.members.manage") && !self ? (
                        <div className="flex items-center gap-2">
                          <Select
                            aria-label={`Role for ${m.display_name}`}
                            className="h-9 w-48"
                            value={
                              team.data.roles.find(
                                (r) => r.name === role || r.key === role,
                              )?.key ?? ""
                            }
                            onChange={(e) =>
                              change.mutate({
                                id: m.membership_id,
                                role: e.target.value,
                              })
                            }
                          >
                            {team.data.roles.map((r) => (
                              <option key={r.key} value={r.key}>
                                {r.name}
                              </option>
                            ))}
                          </Select>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => remove.mutate(m.membership_id)}
                            aria-label={`Remove ${m.display_name}`}
                          >
                            Remove
                          </Button>
                        </div>
                      ) : (
                        <Badge>{role}</Badge>
                      )}
                    </li>
                  );
                })}
              </ul>
            </Card>
            <RoleDetails roles={team.data.roles} />
          </>
        )}
        <SupportAccess />
      </div>
    </Shell>
  );
}

function UsageBar({
  label,
  used,
  limit,
}: {
  label: string;
  used: number;
  limit: number | null | undefined;
}) {
  const percent = limit
    ? Math.min(100, Math.round((used / limit) * 100))
    : null;
  return (
    <div>
      <div className="flex justify-between text-sm">
        <span>{label}</span>
        <span className="tabular-nums text-muted-foreground">
          {count(used)}
          {limit != null ? ` of ${count(limit)}` : ""}
        </span>
      </div>
      {percent !== null ? (
        <div
          className="mt-1.5 h-2 overflow-hidden rounded-full bg-surface-sunken"
          role="progressbar"
          aria-label={label}
          aria-valuenow={percent}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <div
            className={percent >= 90 ? "h-full bg-warning" : "h-full bg-accent"}
            style={{ width: `${percent}%` }}
          />
        </div>
      ) : null}
    </div>
  );
}

export function BillingPage() {
  const key = useBusinessKey();
  const can = useCan();
  const params = useSearchParams();
  const [cancelOpen, setCancelOpen] = React.useState(false);
  const [limit, setLimit] = React.useState("");
  const billing = useQuery({
    queryKey: key(["billing"]),
    queryFn: () => get<BillingView>("/billing"),
    enabled: can("pi.billing.read"),
    refetchInterval: 30_000,
  });
  const checkout = useAction(
    (plan: string) => post<{ url: string }>("/billing/checkout", { plan }),
    { onSuccess: ({ url }) => window.location.assign(url) },
  );
  const portal = useAction(() => post<{ url: string }>("/billing/portal"), {
    onSuccess: ({ url }) => window.location.assign(url),
  });
  const cancel = useAction(() => post<BillingView>("/billing/cancel"), {
    invalidate: [["billing"], ["home"]],
    success: "Cancellation requested",
    onSuccess: () => setCancelOpen(false),
  });
  const spend = useAction(
    (amount: string | null) =>
      put<BillingView>("/billing/spend-limit", { amount }),
    { invalidate: [["billing"]], success: "Spend limit saved" },
  );
  if (!can("pi.billing.read")) {
    return (
      <Shell title="Plan and billing" description="Your Pi plan.">
        <Notice tone="info">Ask your business owner for billing access.</Notice>
      </Shell>
    );
  }
  return (
    <Shell
      title="Plan and billing"
      description="Your Pi plan, this month's usage and invoices."
    >
      {params.get("checkout") === "success" ? (
        <div className="mb-4">
          <Notice tone="success" title="Thanks!">
            Your payment is being confirmed. Your plan updates here in a moment.
          </Notice>
        </div>
      ) : null}
      {billing.isPending ? (
        <LoadingBlock rows={3} />
      ) : billing.isError ? (
        <ErrorState
          message={errorText(billing.error)}
          onRetry={() => billing.refetch()}
        />
      ) : (
        (() => {
          const b = billing.data;
          const s = b.subscription;
          const allowances = b.plan?.allowances ?? {};
          return (
            <div className="space-y-6">
              <Card>
                <CardSection className="space-y-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="text-lg font-semibold">
                      {b.plan?.name ?? "No plan"}
                    </h2>
                    <Badge tone={s.entitled ? "success" : "danger"}>
                      {s.status === "trialing"
                        ? "Free trial"
                        : (s.status ?? "inactive")}
                    </Badge>
                    {s.cancel_at_period_end ? (
                      <Badge tone="warning">
                        Ends {date(s.current_period_end)}
                      </Badge>
                    ) : null}
                  </div>
                  {s.reason && REASON_LABEL[s.reason] ? (
                    <Notice tone={s.entitled ? "info" : "warning"}>
                      {REASON_LABEL[s.reason]}
                    </Notice>
                  ) : null}
                  {s.status === "trialing" && s.trial_ends_at ? (
                    <p className="text-sm text-muted-foreground">
                      Your trial ends on {date(s.trial_ends_at)}.
                    </p>
                  ) : null}
                  {s.current_period_end && s.status === "active" ? (
                    <p className="text-sm text-muted-foreground">
                      Renews on {date(s.current_period_end)}.
                    </p>
                  ) : null}
                  <div className="grid gap-4 sm:grid-cols-2">
                    <UsageBar
                      label="Messages sent"
                      used={Number(b.usage.messages_sent)}
                      limit={allowances.messages as number | null}
                    />
                    <UsageBar
                      label="Voice notes, images and videos"
                      used={Number(b.usage.media_items)}
                      limit={allowances.media_items as number | null}
                    />
                    <UsageBar
                      label="Team members"
                      used={b.usage.seats}
                      limit={allowances.seats as number | null}
                    />
                    <UsageBar
                      label="AI usage (tokens)"
                      used={Number(b.usage.ai_tokens)}
                      limit={allowances.ai_tokens as number | null}
                    />
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Usage for {date(b.usage.period)} onwards, production only.
                    Test mode: {count(b.usage.test_messages_sent)} messages (not
                    counted). Plans don&apos;t include unlimited use; when an
                    allowance is used up Pi hands new messages to your team.
                  </p>
                  {can("pi.billing.manage") ? (
                    <div className="flex flex-wrap gap-2">
                      {s.managed_online ? (
                        <Button
                          variant="secondary"
                          loading={portal.isPending}
                          onClick={() => portal.mutate(undefined)}
                        >
                          <ExternalLink className="size-4" aria-hidden />{" "}
                          Payment details and invoices
                        </Button>
                      ) : null}
                      {s.status !== "canceled" ? (
                        <Button
                          variant="ghost"
                          onClick={() => setCancelOpen(true)}
                        >
                          Cancel plan
                        </Button>
                      ) : null}
                    </div>
                  ) : null}
                </CardSection>
              </Card>

              <section aria-labelledby="plans-title">
                <h2 id="plans-title" className="mb-3 text-base font-semibold">
                  Plans
                </h2>
                <div className="grid gap-3 md:grid-cols-3">
                  {b.plans.map((plan) => (
                    <Card
                      key={plan.key}
                      className={plan.key === s.plan ? "border-accent" : ""}
                    >
                      <CardSection className="space-y-2">
                        <h3 className="font-semibold">{plan.name}</h3>
                        <p className="text-sm text-muted-foreground">
                          {plan.description}
                        </p>
                        <p className="text-lg font-semibold">
                          {plan.monthly_price
                            ? `${money(plan.monthly_price, plan.currency)} / month`
                            : "Price on request"}
                        </p>
                        {plan.manual_monthly_price_pkr ? (
                          <p className="text-sm text-accent">
                            Bank / cash:{" "}
                            {money(plan.manual_monthly_price_pkr, "PKR")} /
                            month
                          </p>
                        ) : null}
                        {plan.key === s.plan && s.status === "active" ? (
                          <Badge tone="accent">Your plan</Badge>
                        ) : can("pi.billing.manage") ? (
                          plan.purchasable ? (
                            <Button
                              size="sm"
                              loading={
                                checkout.isPending &&
                                checkout.variables === plan.key
                              }
                              onClick={() =>
                                s.managed_online && s.status !== "canceled"
                                  ? portal.mutate(undefined)
                                  : checkout.mutate(plan.key)
                              }
                            >
                              {s.managed_online && s.status !== "canceled"
                                ? "Change in Stripe"
                                : `Pay by card · ${plan.name}`}
                            </Button>
                          ) : (
                            <p className="text-sm text-muted-foreground">
                              Contact us to switch to this plan.
                            </p>
                          )
                        ) : null}
                      </CardSection>
                    </Card>
                  ))}
                </div>
              </section>

              <ManualBilling billing={b} />

              {can("pi.billing.manage") ? (
                <Card>
                  <CardSection className="space-y-3">
                    <h2 className="font-semibold">Spend limit</h2>
                    <p className="text-sm text-muted-foreground">
                      Pi stops using AI for new messages this month once
                      estimated AI costs reach this amount.{" "}
                      {s.spend_limit
                        ? `Current limit: ${s.spend_limit} USD.`
                        : "No limit set."}
                    </p>
                    <div className="flex max-w-sm gap-2">
                      <Input
                        aria-label="Monthly AI spend limit in USD"
                        inputMode="decimal"
                        placeholder="e.g. 50.00"
                        value={limit}
                        onChange={(e) => setLimit(e.target.value)}
                      />
                      <Button
                        variant="secondary"
                        disabled={!/^\d+(\.\d{1,2})?$/.test(limit)}
                        onClick={() => spend.mutate(limit)}
                      >
                        Save
                      </Button>
                      {s.spend_limit ? (
                        <Button
                          variant="ghost"
                          onClick={() => spend.mutate(null)}
                        >
                          Remove
                        </Button>
                      ) : null}
                    </div>
                  </CardSection>
                </Card>
              ) : null}

              <Card>
                <CardSection>
                  <h2 className="mb-3 font-semibold">Invoices</h2>
                  {b.invoices.length ? (
                    <ul className="divide-y divide-border text-sm">
                      {b.invoices.map((i) => (
                        <li
                          key={i.number + i.period_start}
                          className="flex flex-wrap items-center gap-3 py-2"
                        >
                          <span className="flex-1">
                            {i.number || "Invoice"} · {date(i.period_start)}
                          </span>
                          <Badge
                            tone={
                              i.status === "paid"
                                ? "success"
                                : i.status === "open"
                                  ? "warning"
                                  : "neutral"
                            }
                          >
                            {i.status}
                          </Badge>
                          <span className="tabular-nums">
                            {money(i.amount_due, i.currency)}
                          </span>
                          {i.url ? (
                            <a
                              className="text-accent underline"
                              href={i.url}
                              target="_blank"
                              rel="noreferrer"
                            >
                              View
                            </a>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-sm text-muted-foreground">
                      No invoices yet.
                    </p>
                  )}
                </CardSection>
              </Card>

              <Dialog open={cancelOpen} onOpenChange={setCancelOpen}>
                <DialogContent
                  title="Cancel your plan?"
                  description={
                    s.status === "trialing"
                      ? "Your trial ends now and Pi stops replying. Your customers and conversations are kept."
                      : "Your plan stays active until the end of the paid period. Then Pi stops replying. Your data is kept."
                  }
                >
                  <div className="flex justify-end gap-2">
                    <Button
                      variant="ghost"
                      onClick={() => setCancelOpen(false)}
                    >
                      Keep my plan
                    </Button>
                    <Button
                      variant="danger"
                      loading={cancel.isPending}
                      onClick={() => cancel.mutate(undefined)}
                    >
                      Cancel plan
                    </Button>
                  </div>
                </DialogContent>
              </Dialog>
            </div>
          );
        })()
      )}
    </Shell>
  );
}

export function BusinessPage() {
  const account = useAccount();
  const can = useCan();
  const [reason, setReason] = React.useState("");
  const pause = useAction(() => post("/account/pause", { reason }), {
    invalidate: [["account"], ["home"]],
    success: "Pi is paused. Your team handles all messages.",
  });
  const resume = useAction(() => post("/account/launch"), {
    invalidate: [["account"], ["home"]],
    success: "Pi is replying again",
  });
  return (
    <Shell
      title="Business"
      description="Your business details and whether Pi is replying."
    >
      {account.isPending ? (
        <LoadingBlock rows={2} />
      ) : account.isError ? (
        <ErrorState
          message={errorText(account.error)}
          onRetry={() => account.refetch()}
        />
      ) : (
        <div className="space-y-6">
          <Card>
            <CardSection className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="font-semibold">Pi status</h2>
                <Badge tone={STATE_LABEL[account.data.setup_state]?.tone}>
                  {STATE_LABEL[account.data.setup_state]?.label}
                </Badge>
              </div>
              {account.data.setup_state === "active" &&
              can("pi.settings.manage") ? (
                <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
                  <Field label="Reason (optional)" htmlFor="pause-reason">
                    <Input
                      id="pause-reason"
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                      maxLength={200}
                    />
                  </Field>
                  <Button
                    variant="secondary"
                    loading={pause.isPending}
                    onClick={() => pause.mutate(undefined)}
                  >
                    <Pause className="size-4" aria-hidden /> Pause Pi
                  </Button>
                </div>
              ) : null}
              {(account.data.setup_state === "paused" ||
                account.data.setup_state === "action_required") &&
              can("pi.settings.manage") ? (
                <div className="space-y-2">
                  {account.data.paused_reason ? (
                    <p className="text-sm text-muted-foreground">
                      Paused: {account.data.paused_reason}
                    </p>
                  ) : null}
                  <Button
                    loading={resume.isPending}
                    onClick={() => resume.mutate(undefined)}
                  >
                    <Play className="size-4" aria-hidden /> Resume Pi
                  </Button>
                </div>
              ) : null}
              {!["active", "paused", "action_required"].includes(
                account.data.setup_state,
              ) ? (
                <Button asChild variant="secondary">
                  <Link href="/setup">Continue setup</Link>
                </Button>
              ) : null}
            </CardSection>
          </Card>
          <Card>
            <CardSection className="space-y-2 text-sm">
              <h2 className="text-base font-semibold">Details</h2>
              <p>
                <span className="text-muted-foreground">Name:</span>{" "}
                {account.data.name}
              </p>
              <p>
                <span className="text-muted-foreground">Time zone:</span>{" "}
                {account.data.timezone}
              </p>
              {account.data.website ? (
                <p>
                  <span className="text-muted-foreground">Website:</span>{" "}
                  {account.data.website}
                </p>
              ) : null}
              <Button asChild size="sm" variant="secondary" className="mt-2">
                <Link href="/setup?step=1">Edit details</Link>
              </Button>
            </CardSection>
          </Card>
        </div>
      )}
    </Shell>
  );
}
