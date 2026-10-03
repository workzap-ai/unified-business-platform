import Link from "next/link";
import { PI } from "@/features/pi/config";
import { WhatsAppButton } from "@/features/pi/client";
import { Breadcrumbs, piMetadata } from "@/features/pi/meta";
import {
  AiChip,
  Chat,
  CtaBlock,
  Face,
  Gate,
  PersonLine,
  Points,
  Section,
  Slot,
  Thread,
} from "@/features/pi/ui";

export const metadata = piMetadata({
  path: "",
  title: "pi by Workzap: talk about your problems on WhatsApp",
  description: PI.live.dashboard
    ? "Chat with pi on WhatsApp about the problems in your business. pi, an AI from Workzap, notes each one, sorts them and shows you everything in one place."
    : "Chat with pi on WhatsApp about the problems in your business. pi, an AI from Workzap, notes each one and sorts them.",
});

export default function PiLanding() {
  return (
    <>
      <Breadcrumbs path="" />
      <section className="pi-hero">
        <div className="pi-wrap pi-hero-grid">
          <div>
            <h1>Tell pi what’s going wrong. pi keeps track.</h1>
            <p className="pi-lead">
              pi is Workzap’s WhatsApp agent. Chat about the problems in your
              business the way you’d tell a colleague. pi notes each one
              {PI.live.dashboard
                ? ", sorts them, and shows you everything in one place."
                : " and sorts them."}
            </p>
            <div className="pi-cta-row">
              <WhatsAppButton page="landing" pos="hero" />
              <Link
                className="pi-btn pi-btn-secondary"
                href={`${PI.base}/how-it-works`}
              >
                See how pi works
              </Link>
            </div>
            <p className="pi-small">
              pi is an AI. It says so in its first message.
            </p>
            <p className="pi-small">
              <Link href={`${PI.base}/trust`}>How we treat your chats</Link> →
            </p>
          </div>
          <div className="pi-hero-visual">
            <div className="pi-hero-face">
              <Face name="rest" size={240} />
              <AiChip />
            </div>
            <Chat
              lines={[
                [
                  "pi",
                  "Hi, I’m pi, an AI from Workzap. Tell me what’s going wrong in your business and I’ll start on it.",
                ],
                ["you", "We keep running out of our best-selling items."],
              ]}
            />
          </div>
        </div>
      </section>

      <Section title="Talk first. Sort it out later.">
        <Points
          items={[
            {
              lead: "No forms. Just chat.",
              text: (
                <>
                  Describe a problem in your own words, on the app you already
                  use.{" "}
                  <Slot kind="CONFIRM">
                    voice notes and photos — say so only if they work at launch
                  </Slot>
                </>
              ),
            },
            {
              lead: "Nothing gets lost.",
              text: "pi notes the problems you describe and sorts them by type, so you don’t have to explain the same thing twice.",
            },
            ...(PI.live.dashboard
              ? [
                  {
                    lead: "Everything in one place.",
                    text: "See your problems, sorted, on your own dashboard.",
                  },
                ]
              : []),
          ]}
        />
      </Section>

      <Section title="This is what a chat looks like" tone="soft">
        <Chat
          note="Illustrative conversation. pi’s real questions are set by Workzap."
          lines={[
            [
              "pi",
              "Hi, I’m pi, an AI from Workzap. Tell me what’s going wrong in your business and I’ll start on it.",
              "greet",
            ],
            ["you", "We keep running out of our best-selling items."],
            [
              "pi",
              "That’s a real problem. Is it happening in every shop, or only some?",
              "rest",
            ],
            ["you", "Two of the four."],
            [
              "pi",
              "Thanks. I’ve noted it: best-sellers running out, in two of four shops. Anything else getting in the way?",
              "noted",
            ],
          ]}
        />
      </Section>

      <Section title="Your chats, your say">
        <p className="pi-big">
          You choose what to tell pi. See how to stop, and what pi never asks
          for.
        </p>
        <p>
          <Link className="pi-arrow" href={`${PI.base}/trust`}>
            Read how we treat your chats →
          </Link>
        </p>
      </Section>

      <Section title="pi is straight with you" tone="tint">
        <Thread
          lines={[
            ["you", "Am I talking to a person?"],
            [
              "pi",
              <>
                <strong>pi is an AI, not a person.</strong> It says so in its
                first message, and again whenever you ask.
              </>,
              "rest",
            ],
            ["you", "What if I’m still explaining the problem?"],
            [
              "pi",
              <>
                <strong>pi puts your problem first.</strong> Nothing gets
                suggested while you’re still explaining what’s wrong.
              </>,
              "rest",
            ],
            ["you", "And if you can’t do what I ask?"],
            [
              "pi",
              <>
                <strong>pi says what it can’t do.</strong> And what happens
                next.
              </>,
              "heads",
            ],
          ]}
        />
      </Section>

      <Gate name="solutions">
        <Section title="From sorted problems to a solution built for you">
          <p>
            When your problems are sorted and you’re ready, pi prepares a
            solution document and a quote. You read them, ask questions, and
            decide. If you approve and pay, Workzap starts building. You can say
            no at any point.
          </p>
          <Points
            numbered
            items={[
              {
                lead: "Sort your problems.",
                text: "Tell pi what’s wrong and see it sorted.",
              },
              {
                lead: "Get a solution document.",
                text: "Only if you ask for one.",
              },
              {
                lead: "Get a quote.",
                text: "Written, with what’s included. An offer, not a charge.",
              },
              {
                lead: "Approve and pay.",
                text: "By bank transfer or secure card payment — never inside the chat.",
              },
              {
                lead: "Workzap begins the build.",
                text: "Once your payment is confirmed, starting with a kickoff.",
              },
            ]}
          />
          <p>
            <Slot kind="PRODUCT">
              whether a person at Workzap checks each quote before it is sent
            </Slot>{" "}
            <Slot kind="WORKZAP">how Workzap describes what it builds</Slot>
          </p>
          <p>
            <Link href={`${PI.base}/solutions`}>
              How quotes and payment work →
            </Link>
          </p>
        </Section>
      </Gate>

      <Section title="Quick answers" tone="soft" layout="stack">
        <div className="pi-qa">
          <div className="pi-qa-item">
            <h3>Is pi a real person?</h3>
            <p>No. pi is an AI, and it says so in its first message.</p>
          </div>
          <div className="pi-qa-item">
            <h3>Will pi try to sell me something?</h3>
            <p>
              {PI.live.solutions
                ? "Not while you’re describing a problem. When your problems are sorted, pi asks whether you’d like a solution document and a quote. You can say no."
                : "Not while you’re describing a problem."}
            </p>
          </div>
          <div className="pi-qa-item">
            <h3>Can I make pi stop?</h3>
            <p>
              Yes.{" "}
              <Slot kind="PRODUCT">
                one fixed word that is always recognised, and what happens next
              </Slot>
            </p>
          </div>
        </div>
        <p className="pi-qa-more">
          <Link className="pi-arrow" href={`${PI.base}/faq`}>
            All questions →
          </Link>
        </p>
      </Section>

      <CtaBlock page="landing" pos="closing" heading="Start with one problem.">
        <PersonLine />
      </CtaBlock>
    </>
  );
}
