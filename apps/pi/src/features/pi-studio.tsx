"use client";

import {
  ArrowRight,
  ArrowUpRight,
  BellRing,
  BookOpenText,
  ChevronRight,
  Globe2,
  MessageCircle,
  Play,
  PlugZap,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
} from "lucide-react";
import Link from "next/link";

import { ErrorState, LoadingBlock } from "@/components/ui";
import { LANGUAGES, MODE_LABEL, useAccount } from "@/features/setup";
import { errorText } from "@/lib/api";
import { STATE_LABEL } from "@/lib/format";
import type { Account } from "@/lib/types";

import s from "./pi-studio.module.css";

const SECTIONS = [
  {
    title: "Business knowledge",
    label: "THE FOUNDATION",
    description:
      "Your services, your story, the little details. Give Pi the knowledge to answer with confidence.",
    action: "Shape what Pi knows",
    href: "/my-pi/knowledge",
    icon: BookOpenText,
    tone: "lavender",
  },
  {
    title: "Voice & behaviour",
    label: "THE PERSONALITY",
    description:
      "Warm or professional? You decide. Set the tone, boundaries and when your team steps in.",
    action: "Make it sound like you",
    href: "/my-pi/behaviour",
    icon: SlidersHorizontal,
    tone: "peach",
  },
  {
    title: "Tools & actions",
    label: "THE HELPING HAND",
    description:
      "From remembering customers to looking up orders. Choose how Pi can lend a hand.",
    action: "Explore your tools",
    href: "/my-pi/tools",
    icon: PlugZap,
    tone: "sage",
  },
  {
    title: "Thoughtful follow-ups",
    label: "THE NEXT HELLO",
    description:
      "Keep the conversation going with friendly reminders for customers who opt in.",
    action: "Plan your follow-ups",
    href: "/my-pi/follow-ups",
    icon: BellRing,
    tone: "sand",
  },
];

const CONNECTION_LABEL: Record<Account["whatsapp"]["status"], string> = {
  connected: "Connected",
  draft: "Not connected",
  setup_pending: "Setup in progress",
  action_required: "Needs attention",
  disconnected: "Disconnected",
};

export function PiStudio() {
  const account = useAccount();
  if (account.isPending) return <LoadingBlock label="Opening My Pi" />;
  if (account.isError)
    return (
      <ErrorState
        message={errorText(account.error)}
        onRetry={() => account.refetch()}
      />
    );
  return <Studio account={account.data} />;
}

function Studio({ account }: { account: Account }) {
  const state = STATE_LABEL[account.setup_state];
  const connected = account.whatsapp.status === "connected";
  const language =
    LANGUAGES.find(([code]) => code === account.language)?.[1] ??
    account.language;
  const mode = MODE_LABEL[account.automation_mode];
  const completed = account.readiness.filter((item) => item.done).length;
  const total = account.readiness.length;

  return (
    <div className={s.studio}>
      <div className={s.breadcrumb}>
        <Link href="/home">Workspace</Link>
        <ChevronRight size={12} aria-hidden />
        <span>My Pi</span>
      </div>
      <header className={s.header}>
        <div>
          <h1>
            Make Pi your own<span>.</span>
          </h1>
          <p>A little of your knowledge. A lot of your personality.</p>
        </div>
        <Link href="/my-pi/settings" className={s.settingsButton}>
          <Settings2 size={16} aria-hidden />
          All settings
        </Link>
      </header>

      <section className={s.hero} aria-labelledby="pi-studio-hero">
        <div className={s.heroContent}>
          <span className={s.heroEyebrow}>
            <Sparkles size={14} aria-hidden /> BUILT AROUND YOUR BUSINESS
          </span>
          <h2 id="pi-studio-hero">
            Your business.
            <br />
            <em>Your voice.</em> Your Pi.
          </h2>
          <p>
            Turn what makes your business special into conversations that feel a
            little more human.
          </p>
          <Link href="/my-pi/test" className={s.heroButton}>
            <Play size={13} fill="currentColor" aria-hidden />
            Try a conversation
            <ArrowUpRight size={17} aria-hidden />
          </Link>
          <span className={s.heroHint}>
            A safe space to try things. Nothing is sent.
          </span>
        </div>
        <div className={s.heroArt} aria-hidden="true">
          <div className={s.artGlow} />
          <span className={s.artSparkOne}>✦</span>
          <span className={s.artSparkTwo}>✧</span>
          <div className={s.piTile}>
            <span>
              Pi<span className={s.piDot}>.</span>
            </span>
            <div className={s.tileShine} />
          </div>
          <div className={s.artSignature}>
            <Sparkles size={14} />
            <span>
              A little intelligence.
              <br />
              <strong>A personal touch.</strong>
            </span>
          </div>
        </div>
      </section>

      <div className={s.mainGrid}>
        <section className={s.personalize} aria-labelledby="pi-personalize">
          <div className={s.sectionHeading}>
            <div>
              <span className={s.eyebrow}>THE DETAILS MAKE THE DIFFERENCE</span>
              <h2 id="pi-personalize">A Pi that feels like you</h2>
            </div>
            <span className={s.sectionCount}>04 essentials</span>
          </div>
          <div className={s.cards}>
            {SECTIONS.map(
              (
                { title, label, description, action, href, icon: Icon, tone },
                index,
              ) => (
                <Link
                  href={href}
                  key={href}
                  className={s.featureCard}
                  data-tone={tone}
                >
                  <div className={s.cardTop}>
                    <span className={s.cardIcon}>
                      <Icon size={22} strokeWidth={1.6} aria-hidden />
                    </span>
                    <span className={s.cardNumber}>0{index + 1}</span>
                  </div>
                  <span className={s.cardEyebrow}>{label}</span>
                  <h3>{title}</h3>
                  <p>{description}</p>
                  <span className={s.cardAction}>
                    {action}
                    <ArrowUpRight size={17} aria-hidden />
                  </span>
                </Link>
              ),
            )}
          </div>
        </section>

        <aside className={s.aside} aria-label="Your Pi overview">
          <section className={s.profile} aria-labelledby="pi-profile-title">
            <div className={s.profileHeading}>
              <span className={s.eyebrow}>YOUR ASSISTANT</span>
              <Link
                href="/settings/business"
                aria-label="Open business details"
              >
                <ArrowUpRight size={17} />
              </Link>
            </div>
            <div className={s.profileIdentity}>
              <span className={s.avatar} aria-hidden>
                Pi
              </span>
              <div>
                <h2 id="pi-profile-title">{account.name || "Your business"}</h2>
                <span
                  className={s.state}
                  data-active={account.setup_state === "active"}
                >
                  <span />
                  {state?.label ?? "Setting up"}
                </span>
              </div>
            </div>
            <dl className={s.details}>
              <div>
                <dt>
                  <MessageCircle size={16} aria-hidden />
                  WhatsApp
                </dt>
                <dd>
                  <Link
                    href="/settings/whatsapp"
                    className={connected ? s.connected : s.needsSetup}
                  >
                    {CONNECTION_LABEL[account.whatsapp.status]}
                    <ChevronRight size={12} aria-hidden />
                  </Link>
                </dd>
              </div>
              <div>
                <dt>
                  <Globe2 size={16} aria-hidden />
                  Language
                </dt>
                <dd>{language || "Not set"}</dd>
              </div>
              <div>
                <dt>
                  <ShieldCheck size={16} aria-hidden />
                  Reply mode
                </dt>
                <dd>{mode?.[0] ?? "Not set"}</dd>
              </div>
              <div>
                <dt>
                  <PlugZap size={16} aria-hidden />
                  Tool groups
                </dt>
                <dd>{account.tools.length} selected</dd>
              </div>
            </dl>
            <Link href="/my-pi/behaviour" className={s.profileLink}>
              Fine-tune your assistant
              <ArrowRight size={15} aria-hidden />
            </Link>
          </section>

          {account.setup_state !== "active" && (
            <section className={s.setupCard} aria-label="Setup progress">
              <div className={s.setupTitle}>
                <h2>A strong start for Pi</h2>
                {total > 0 && (
                  <span>
                    {completed}/{total}
                  </span>
                )}
              </div>
              <p>
                {account.paused_reason ||
                  "A few finishing touches, then you're ready for your first conversation."}
              </p>
              {total > 0 && (
                <progress
                  value={completed}
                  max={total}
                  aria-label={`${completed} of ${total} setup checks complete`}
                />
              )}
              <Link href="/setup">
                {account.setup_state === "paused"
                  ? "Review setup"
                  : "Continue setup"}
                <ArrowRight size={15} aria-hidden />
              </Link>
            </section>
          )}

          <section className={s.noteCard} aria-labelledby="pi-note-title">
            <span className={s.noteIcon}>
              <BookOpenText size={19} strokeWidth={1.6} aria-hidden />
            </span>
            <span className={s.eyebrow}>A SMALL TIP, A BIG DIFFERENCE</span>
            <h2 id="pi-note-title">
              The best answers
              <br />
              start with <em>your story.</em>
            </h2>
            <p>
              Add the questions customers ask most. A little context helps Pi
              make a better first impression.
            </p>
            <Link href="/my-pi/knowledge">
              Give Pi something to learn
              <ArrowRight size={15} aria-hidden />
            </Link>
          </section>
        </aside>
      </div>

      <footer className={s.footer}>
        <span>
          <ShieldCheck size={14} aria-hidden />
          Your business. Your rules. Always.
        </span>
        <Link href="/inbox">
          Back to conversations
          <ArrowUpRight size={14} aria-hidden />
        </Link>
      </footer>
    </div>
  );
}
