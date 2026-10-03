"use client";

import { useQuery } from "@tanstack/react-query";
import {
  CalendarCheck,
  ArrowUpRight,
  ArrowRight,
  CheckCircle2,
  Hand,
  MessageCircle,
  ShieldCheck,
  Sparkles,
  UsersRound,
} from "lucide-react";
import Link from "next/link";

import { PiFace } from "@/components/brand";
import {
  Button,
  Card,
  CardSection,
  ErrorState,
  Skeleton,
} from "@/components/ui";
import { errorText, get } from "@/lib/api";
import { count, money } from "@/lib/format";
import type { Plan } from "@/lib/types";
import s from "./public.module.css";

const FEATURES = [
  {
    icon: MessageCircle,
    title: "Answers from what you approve",
    body: "pi replies in your customer's language using only the information you've published.",
  },
  {
    icon: UsersRound,
    title: "Remembers returning customers",
    body: "Requirements, orders and preferences stay with each customer — and only that customer.",
  },
  {
    icon: Hand,
    title: "Your team stays in control",
    body: "Approve replies first, or let pi handle simple questions. Take over any conversation instantly.",
  },
  {
    icon: CalendarCheck,
    title: "Gets real work done",
    body: "Capture enquiries, check live stock and prepare orders for customers to confirm — only with the tools you switch on.",
  },
];

const ALLOWANCE_LABEL: Record<string, string> = {
  messages: "messages a month",
  seats: "team members",
  numbers: "WhatsApp numbers",
  media_items: "voice notes, images and videos",
};

function PlanCard({ plan }: { plan: Plan }) {
  return (
    <Card className={`flex flex-col ${s.planCard}`}>
      <CardSection className="flex flex-1 flex-col">
        <h3 className="text-lg font-semibold">{plan.name}</h3>
        <p className="mt-1 text-sm text-muted-foreground">{plan.description}</p>
        <p className="mt-5 text-2xl font-semibold">
          {plan.monthly_price !== null ? (
            <>
              {money(plan.monthly_price, plan.currency)}
              <span className="text-sm font-normal text-muted-foreground">
                {" "}
                / month
              </span>
            </>
          ) : (
            <span className="text-base font-medium text-foreground-secondary">
              Price on request
            </span>
          )}
        </p>
        <ul className="mt-5 space-y-2 text-sm">
          {Object.entries(ALLOWANCE_LABEL).map(([key, label]) =>
            plan.allowances[key] != null ? (
              <li key={key} className="flex gap-2">
                <CheckCircle2
                  className="mt-0.5 size-4 shrink-0 text-accent"
                  aria-hidden
                />
                {count(plan.allowances[key] ?? 0)} {label}
              </li>
            ) : null,
          )}
        </ul>
        <div className="mt-auto pt-6">
          <Button asChild variant="secondary" className="w-full">
            <Link href="/sign-up">
              {plan.trial_days > 0
                ? `Start a ${plan.trial_days}-day free trial`
                : "Get started"}
            </Link>
          </Button>
        </div>
      </CardSection>
    </Card>
  );
}

export function LandingPage() {
  const plans = useQuery({
    queryKey: ["public-plans"],
    queryFn: () => get<Plan[]>("/plans"),
  });
  return (
    <div>
      <section className={s.hero}>
        <div className={s.heroCopy}>
          <span className={s.eyebrow}>
            <Sparkles size={15} aria-hidden />A THOUGHTFUL WHATSAPP ASSISTANT
          </span>
          <h1>
            More conversations.
            <br />
            <em>More possibilities.</em>
          </h1>
          <p>
            Meet pi. Your business knowledge, your personality and a helping
            hand for every customer conversation.
          </p>
          <div className={s.heroActions}>
            <Button asChild size="lg">
              <Link href="/sign-up">
                Set up pi
                <ArrowUpRight size={17} aria-hidden />
              </Link>
            </Button>
            <Button asChild size="lg" variant="secondary">
              <Link href="#how-it-works">
                Meet your assistant
                <ArrowRight size={17} aria-hidden />
              </Link>
            </Button>
          </div>
          <p className={s.heroPromise}>
            <ShieldCheck className="size-4" aria-hidden />
            pi never replies to customers until you choose to launch.
          </p>
        </div>
        <div
          className={s.example}
          aria-label="Example conversation, illustrative only"
        >
          <div className={s.exampleHeader}>
            <PiFace size={48} decorative />
            <div>
              <strong>A little more personal.</strong>
              <small>Your business assistant on WhatsApp</small>
            </div>
            <Sparkles size={20} aria-hidden />
          </div>
          <div className={s.chat}>
            <p>Hi! Can you help me choose the right service?</p>
            <div>
              <span>
                <Sparkles size={12} aria-hidden />
                pi
              </span>
              <p>
                Of course. Tell me what you have in mind, and I’ll help you find
                the right fit.
              </p>
            </div>
          </div>
          <div className={s.exampleCaption}>
            <span>
              <ShieldCheck size={13} aria-hidden />
              Your knowledge. Your rules.
            </span>
            <span>Example conversation</span>
          </div>
        </div>
      </section>

      <section aria-labelledby="features" className={s.features}>
        <div className={s.featureGrid}>
          <h2 id="features" className="sr-only">
            What pi does
          </h2>
          {FEATURES.map(({ icon: Icon, title, body }) => (
            <div key={title}>
              <div className={s.featureIcon}>
                <Icon className="size-5" aria-hidden />
              </div>
              <h3 className="mt-4 font-semibold">{title}</h3>
              <p className="mt-1 text-sm text-muted-foreground">{body}</p>
            </div>
          ))}
        </div>
      </section>

      <section id="how-it-works" className={s.how} aria-labelledby="how-title">
        <div className={s.sectionTitle}>
          <span className={s.eyebrow}>SIMPLE FROM THE START</span>
          <h2 id="how-title">
            Your expertise.
            <br />
            <em>A helping hand.</em>
          </h2>
          <p>
            Start with what you know best: your business. We’ll guide you
            through the rest.
          </p>
        </div>
        <div className={s.steps}>
          <div className={s.step}>
            <span>01</span>
            <h3>Tell pi your story</h3>
            <p>
              Add your services, products and the questions customers ask.
              Review what pi learns before publishing it.
            </p>
          </div>
          <div className={s.step}>
            <span>02</span>
            <h3>Make the introduction</h3>
            <p>
              Connect your WhatsApp number and choose how much pi handles, with
              your team always in control.
            </p>
          </div>
          <div className={s.step}>
            <span>03</span>
            <h3>Find your rhythm</h3>
            <p>
              Try a conversation, refine the details and launch when your
              connection and plan are ready.
            </p>
          </div>
        </div>
      </section>

      <section
        id="pricing"
        aria-labelledby="pricing-title"
        className={s.pricing}
      >
        <div className={s.sectionTitle}>
          <span className={s.eyebrow}>ROOM TO GROW</span>
          <h2 id="pricing-title">
            A plan for <em>your next chapter.</em>
          </h2>
          <p>
            Choose what fits your business. Provider and number charges are
            shown before you agree to them.
          </p>
        </div>
        <div className="mt-8 grid gap-4 md:grid-cols-3">
          {plans.isPending ? (
            [0, 1, 2].map((i) => <Skeleton key={i} className="h-80" />)
          ) : plans.isError ? (
            <div className="md:col-span-3">
              <ErrorState
                message={errorText(plans.error)}
                onRetry={() => plans.refetch()}
              />
            </div>
          ) : (
            plans.data.map((plan) => <PlanCard key={plan.key} plan={plan} />)
          )}
        </div>
      </section>
      <section className={s.closing}>
        <div>
          <h2>Let’s make a good first impression.</h2>
          <p>Bring your business to pi, one conversation at a time.</p>
        </div>
        <Button asChild size="lg">
          <Link href="/sign-up">
            Make pi yours
            <ArrowUpRight size={17} aria-hidden />
          </Link>
        </Button>
      </section>
    </div>
  );
}
