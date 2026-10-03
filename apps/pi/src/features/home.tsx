"use client";

import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  ArrowUpRight,
  CheckCircle2,
  CircleAlert,
  CirclePause,
  Inbox,
  Users,
  MessageCircleQuestion,
  Sparkles,
  UserRoundCheck,
} from "lucide-react";
import Link from "next/link";

import {
  Badge,
  Button,
  Card,
  CardSection,
  ErrorState,
  LoadingBlock,
} from "@/components/ui";
import { DigestCard } from "@/features/digest-card";
import {
  ActivityChart,
  InsightKpis,
  InsightsSkeleton,
  RecentConversations,
  TopicsCard,
  useInsights,
} from "@/features/home-insights";
import { useAccount } from "@/features/setup";
import { WhatsAppLiveCard } from "@/features/whatsapp-live";
import { errorText, get } from "@/lib/api";
import { REASON_LABEL, STATE_LABEL, count } from "@/lib/format";
import { useBusinessKey, useSession } from "@/lib/session";
import type { HomeView } from "@/lib/types";
import s from "./home.module.css";

const ACTION_ICON: Record<string, typeof Inbox> = {
  approvals: UserRoundCheck,
  questions: MessageCircleQuestion,
  handoffs: Inbox,
  problem: CircleAlert,
  billing: CircleAlert,
  setup: Sparkles,
};

function StatusCard({ data }: { data: HomeView }) {
  const state = STATE_LABEL[data.setup_state];
  if (data.active && data.metrics.ai_unavailable_24h > 0) {
    return (
      <Card className="border-warning/40">
        <CardSection className="flex items-start gap-4">
          <CircleAlert
            className="mt-0.5 size-6 shrink-0 text-warning"
            aria-hidden
          />
          <div>
            <h2 className="text-lg font-semibold">
              Pi is on, but couldn&apos;t reply recently
            </h2>
            <p className="text-sm text-muted-foreground">
              Pi&apos;s AI service wasn&apos;t available, so those conversations
              were handed to your team and the customers were told a person will
              reply.
            </p>
          </div>
        </CardSection>
      </Card>
    );
  }
  if (data.active) {
    return (
      <Card className={s.statusActive}>
        <CardSection className={s.activeContent}>
          <CheckCircle2
            className="mt-0.5 size-6 shrink-0 text-success"
            aria-hidden
          />
          <div>
            <h2 className="text-lg font-semibold">
              Pi is answering your customers
            </h2>
            <p className="text-sm text-muted-foreground">
              It hands conversations to your team whenever a person is needed.
            </p>
          </div>
        </CardSection>
      </Card>
    );
  }
  const reason = data.plan_reason ? REASON_LABEL[data.plan_reason] : null;
  return (
    <Card className="border-warning/30">
      <CardSection className="flex flex-col gap-4 sm:flex-row sm:items-center">
        <CirclePause className="size-6 shrink-0 text-warning" aria-hidden />
        <div className="flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-lg font-semibold">
              Pi isn&apos;t replying to customers
            </h2>
            <Badge tone={state?.tone}>{state?.label}</Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            {reason ??
              (data.setup_state === "paused"
                ? "You paused Pi. Your team is handling all messages."
                : "Finish setting up and launch when you're ready. Nothing is sent before that.")}
          </p>
        </div>
        <Button asChild>
          <Link
            href={
              data.setup_state === "paused" ? "/settings/business" : "/setup"
            }
          >
            {data.setup_state === "paused"
              ? "Review and resume"
              : "Continue setup"}
          </Link>
        </Button>
      </CardSection>
    </Card>
  );
}

/** The live-number card, once WhatsApp is connected. */
function HomeWhatsApp() {
  const account = useAccount();
  const connection = account.data?.whatsapp;
  if (connection?.status !== "connected" || !connection.display_phone_number)
    return null;
  return (
    <WhatsAppLiveCard
      number={connection.display_phone_number}
      live={account.data?.setup_state === "active"}
    />
  );
}

function greeting() {
  const hour = new Date().getHours();
  return hour < 12
    ? "Good morning"
    : hour < 17
      ? "Good afternoon"
      : "Good evening";
}

function NeedsYou({ data }: { data: HomeView }) {
  return (
    <section aria-labelledby="needs-you">
      <div className="mb-3 flex items-center gap-2">
        <h2 id="needs-you" className="text-base font-semibold">
          Needs your attention
        </h2>
        {data.next_actions.length > 0 && (
          <Badge tone="warning">{data.next_actions.length}</Badge>
        )}
      </div>
      {data.next_actions.length === 0 ? (
        <Card>
          <CardSection className="flex items-center gap-3 text-sm text-muted-foreground">
            <CheckCircle2 className="size-5 text-success" aria-hidden />
            You&apos;re all caught up.
          </CardSection>
        </Card>
      ) : (
        <Card>
          <ul className="divide-y divide-border">
            {data.next_actions.map((action) => {
              const Icon = ACTION_ICON[action.kind] ?? ArrowRight;
              return (
                <li key={action.kind + action.label}>
                  <Link
                    href={action.href}
                    className="flex min-h-14 items-center gap-3 px-4 py-3 text-[15px] hover:bg-surface-muted active:bg-surface-muted sm:px-5"
                  >
                    <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-accent-soft text-accent">
                      <Icon className="size-4" aria-hidden />
                    </span>
                    <span className="flex-1">{action.label}</span>
                    <ArrowRight
                      className="size-4 text-muted-foreground rtl:rotate-180"
                      aria-hidden
                    />
                  </Link>
                </li>
              );
            })}
          </ul>
        </Card>
      )}
    </section>
  );
}

function TeamCard({ data }: { data: HomeView }) {
  const m = data.metrics;
  const rows = [
    {
      label: "Waiting for a person",
      value: m.waiting_for_team,
      href: "/inbox?mode=human",
      icon: Users,
    },
    {
      label: "Replies to approve",
      value: m.awaiting_approval,
      href: "/inbox",
      icon: UserRoundCheck,
    },
    {
      label: "Questions Pi asked you",
      value: m.open_questions,
      href: "/inbox",
      icon: MessageCircleQuestion,
    },
    {
      label: "Unread messages",
      value: m.unread,
      href: "/inbox?filter=unread",
      icon: Inbox,
    },
    {
      label: "Enquiries this week",
      value: m.enquiries_7d,
      href: "/customers",
      icon: Sparkles,
    },
  ];
  return (
    <Card className="overflow-hidden">
      <div className="border-b border-border px-4 py-3.5 sm:px-5">
        <h2 className="font-semibold">For your team</h2>
      </div>
      <ul className="divide-y divide-border">
        {rows.map(({ label, value, href, icon: Icon }) => (
          <li key={label}>
            <Link
              href={href}
              className="flex min-h-12 items-center gap-3 px-4 py-2.5 text-sm hover:bg-surface-muted active:bg-surface-muted sm:px-5"
            >
              <Icon
                className="size-4 shrink-0 text-muted-foreground"
                aria-hidden
              />
              <span className="flex-1">{label}</span>
              <span
                className={
                  value > 0
                    ? "rounded-full bg-accent px-2 text-xs font-semibold tabular-nums text-accent-foreground"
                    : "text-xs tabular-nums text-muted-foreground"
                }
              >
                {count(value)}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </Card>
  );
}

export function HomePage() {
  const key = useBusinessKey();
  const session = useSession();
  const home = useQuery({
    queryKey: key(["home"]),
    queryFn: () => get<HomeView>("/home"),
    refetchInterval: 60_000,
  });
  const insights = useInsights();
  if (home.isPending)
    return <LoadingBlock rows={4} label="Loading your overview" />;
  if (home.isError)
    return (
      <ErrorState
        message={errorText(home.error)}
        onRetry={() => home.refetch()}
      />
    );
  const firstName = session.data?.user.display_name.split(" ")[0];
  const unread = home.data.metrics.unread;
  return (
    <div className={s.home}>
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <p className="text-sm text-muted-foreground">
            {greeting()}
            {firstName ? `, ${firstName}` : ""}
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <h1 className="truncate text-2xl font-semibold tracking-tight sm:text-3xl">
              {home.data.name}
            </h1>
            <Badge tone={home.data.active ? "success" : "warning"}>
              <span
                className={
                  home.data.active
                    ? "size-1.5 rounded-full bg-success"
                    : "size-1.5 rounded-full bg-warning"
                }
                aria-hidden
              />
              {home.data.active ? "Pi is live" : "Pi is off"}
            </Badge>
          </div>
        </div>
        <Button asChild variant="secondary" className="w-full sm:w-auto">
          <Link href="/inbox">
            <Inbox size={16} aria-hidden />
            Open inbox
            {unread > 0 && (
              <span className="rounded-full bg-accent px-1.5 text-xs text-accent-foreground">
                {count(unread)}
              </span>
            )}
            <ArrowUpRight size={15} aria-hidden />
          </Link>
        </Button>
      </header>
      <StatusCard data={home.data} />
      {insights.data ? (
        <InsightKpis data={insights.data} />
      ) : (
        <InsightsSkeleton />
      )}
      <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="min-w-0 space-y-6">
          {insights.data ? <ActivityChart data={insights.data} /> : null}
          <NeedsYou data={home.data} />
          <RecentConversations />
        </div>
        <div className="min-w-0 space-y-6">
          <HomeWhatsApp />
          {insights.data ? <TopicsCard data={insights.data} /> : null}
          <TeamCard data={home.data} />
          <DigestCard />
        </div>
      </div>
      <div className={s.quickLinks}>
        <Link href="/my-pi">
          <Sparkles size={23} aria-hidden />
          <div>
            <strong>A Pi that sounds like you</strong>
            <p>Refine your knowledge, your tone and the ways Pi helps.</p>
          </div>
          <ArrowUpRight size={18} aria-hidden />
        </Link>
        <Link href="/customers">
          <Users size={23} aria-hidden />
          <div>
            <strong>Every customer has a story</strong>
            <p>
              Pick up where you left off, with context that stays with them.
            </p>
          </div>
          <ArrowUpRight size={18} aria-hidden />
        </Link>
      </div>
    </div>
  );
}
