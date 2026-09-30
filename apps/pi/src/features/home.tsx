"use client";

import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  ArrowUpRight,
  CheckCircle2,
  CircleAlert,
  CirclePause,
  Inbox,
  MessageCircle,
  Send,
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
  PageHeader,
} from "@/components/ui";
import { DigestCard } from "@/features/digest-card";
import { errorText, get } from "@/lib/api";
import { REASON_LABEL, STATE_LABEL, count } from "@/lib/format";
import { useBusinessKey } from "@/lib/session";
import type { HomeView } from "@/lib/types";
import s from "./home.module.css";

function Metric({
  label,
  value,
  hint,
}: {
  label: string;
  value: number;
  hint: string;
}) {
  const Icon =
    (
      {
        Conversations: MessageCircle,
        "Replies sent by Pi": Send,
        Enquiries: Sparkles,
        "With your team": Users,
      } as Record<string, typeof Inbox>
    )[label] ?? Inbox;
  return (
    <Card className={s.metric}>
      <CardSection className="p-4 sm:p-5">
        <div className={s.metricTop}>
          <p className="text-sm text-muted-foreground">{label}</p>
          <span className={s.metricIcon}>
            <Icon size={16} aria-hidden />
          </span>
        </div>
        <p className={s.metricValue}>{count(value)}</p>
        <p className={s.metricHint}>{hint}</p>
      </CardSection>
    </Card>
  );
}

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

export function HomePage() {
  const key = useBusinessKey();
  const home = useQuery({
    queryKey: key(["home"]),
    queryFn: () => get<HomeView>("/home"),
    refetchInterval: 60_000,
  });
  if (home.isPending)
    return <LoadingBlock rows={4} label="Loading your overview" />;
  if (home.isError)
    return (
      <ErrorState
        message={errorText(home.error)}
        onRetry={() => home.refetch()}
      />
    );
  const { metrics } = home.data;
  return (
    <div className={s.home}>
      <div>
        <p className={s.eyebrow}>YOUR BUSINESS AT A GLANCE</p>
        <PageHeader
          title={home.data.name}
          description="What Pi has done this week and what needs you."
          action={
            <Button asChild variant="secondary">
              <Link href="/inbox">
                <Inbox size={16} aria-hidden />
                Open inbox
                <ArrowUpRight size={15} aria-hidden />
              </Link>
            </Button>
          }
        />
      </div>
      <StatusCard data={home.data} />
      <section aria-labelledby="needs-you">
        <h2 id="needs-you" className="mb-3 text-base font-semibold">
          Needs your attention
        </h2>
        {home.data.next_actions.length === 0 ? (
          <Card>
            <CardSection className="flex items-center gap-3 text-sm text-muted-foreground">
              <CheckCircle2 className="size-5 text-success" aria-hidden />
              You&apos;re all caught up.
            </CardSection>
          </Card>
        ) : (
          <Card>
            <ul className="divide-y divide-border">
              {home.data.next_actions.map((action) => {
                const Icon = ACTION_ICON[action.kind] ?? ArrowRight;
                return (
                  <li key={action.kind + action.label}>
                    <Link
                      href={action.href}
                      className="flex min-h-14 items-center gap-3 px-5 py-3 text-[15px] hover:bg-surface-muted"
                    >
                      <Icon
                        className="size-5 shrink-0 text-accent"
                        aria-hidden
                      />
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
      <section aria-labelledby="this-week">
        <h2 id="this-week" className="mb-3 text-base font-semibold">
          Last 7 days
        </h2>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Metric
            label="Conversations"
            value={metrics.conversations_7d}
            hint="with new messages"
          />
          <Metric
            label="Replies sent by Pi"
            value={metrics.pi_replies_7d}
            hint="delivered to WhatsApp"
          />
          <Metric
            label="Enquiries"
            value={metrics.enquiries_7d}
            hint="requirements, quotes or orders"
          />
          <Metric
            label="With your team"
            value={metrics.waiting_for_team}
            hint="waiting for a person now"
          />
        </div>
      </section>
      <div className="mt-6">
        <DigestCard />
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
