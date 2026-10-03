import Link from "next/link";
import { PI } from "@/features/pi/config";
import { Breadcrumbs, piMetadata } from "@/features/pi/meta";
import {
  CtaBlock,
  Face,
  Gate,
  PageIntro,
  Points,
  Section,
  Slot,
} from "@/features/pi/ui";

export const metadata = piMetadata({
  path: "/how-it-works",
  title: "How pi works: chat, sort, see your problems | pi by Workzap",
  description: PI.live.solutions
    ? "Start a WhatsApp chat and tell pi what’s wrong. See your problems sorted, then get a solution document and a quote if you ask for them."
    : "Start a WhatsApp chat and tell pi what’s wrong. pi notes and sorts your problems.",
});

export default function HowItWorks() {
  return (
    <>
      <Breadcrumbs path="/how-it-works" name="How pi works" />
      <PageIntro
        title="How pi works"
        sub={
          PI.live.solutions
            ? "You talk. pi listens, notes and sorts. When you’re ready, you get a solution and a quote."
            : "You talk. pi listens, notes and sorts."
        }
      />

      <Section
        title={
          PI.live.solutions
            ? "Part 1 — Tell pi what’s going wrong"
            : "Tell pi what’s going wrong"
        }
      >
        <ul className="pi-ribbon" aria-label="The first steps, in order">
          <li>
            <Face name="greet" size={96} />
            Start a chat
          </li>
          <li>
            <Face name="rest" size={96} />
            Tell pi
          </li>
          <li>
            <Face name="noted" size={96} />
            pi notes and sorts
          </li>
        </ul>
        <div style={{ height: 24 }} />
        <Points
          numbered
          items={[
            {
              lead: "Start a chat.",
              text: "Tap the button on this site. WhatsApp opens with a message ready to send. pi replies and tells you it’s an AI.",
            },
            {
              lead: "Tell pi what’s going wrong.",
              text: (
                <>
                  Write in your own words. pi asks one question at a time and
                  doesn’t rush you.{" "}
                  <Slot kind="CONFIRM">
                    voice notes, photos and video — list only what works at
                    launch
                  </Slot>
                </>
              ),
            },
            {
              lead: "pi notes and sorts.",
              text: "Each problem is noted and grouped with similar ones, so patterns show up. pi tells you what it has noted, so you can correct it.",
            },
            ...(PI.live.dashboard
              ? [
                  {
                    lead: "See it in one place.",
                    text: (
                      <>
                        Your problems appear on your dashboard, sorted by type.{" "}
                        <Slot kind="PRODUCT">
                          how you sign in, and when the dashboard is available
                        </Slot>
                      </>
                    ),
                  },
                ]
              : []),
          ]}
        />
      </Section>

      <Gate name="solutions">
        <Section
          title="Part 2 — From sorted problems to a solution"
          tone="soft"
        >
          <Points
            numbered
            start={5}
            items={[
              {
                lead: "pi asks if you’d like a solution.",
                text: "Only when your problems are sorted and you’re ready. pi won’t prepare anything unless you say yes.",
              },
              {
                lead: "You get a solution document.",
                text: (
                  <>
                    A plain-language document: your problems, what Workzap would
                    build, and what it won’t do.{" "}
                    <Slot kind="PRODUCT">format</Slot>
                  </>
                ),
              },
              {
                lead: "You get a quote.",
                text: (
                  <>
                    What’s included, what it costs, how long it takes, how
                    payment works. A quote is an offer, not a charge.{" "}
                    <Slot kind="WORKZAP">pricing model</Slot>
                  </>
                ),
              },
              {
                lead: "You review, then approve — or don’t.",
                text: (
                  <>
                    Ask questions, ask for changes, or say no. Nothing is
                    charged until you approve.{" "}
                    <Slot kind="PRODUCT">how you approve</Slot>
                  </>
                ),
              },
              {
                lead: "You pay, then Workzap begins.",
                text: (
                  <>
                    Payment details come with your approved quote — by bank
                    transfer or a secure card page, never in the chat. Check
                    them against your dashboard. Once your payment is confirmed,
                    Workzap begins your project with a kickoff.{" "}
                    <Slot kind="PRODUCT">timeline</Slot>
                  </>
                ),
              },
            ]}
          />
          <p style={{ marginTop: 18 }}>
            <Link href={`${PI.base}/solutions`}>The full detail →</Link>
          </p>
        </Section>
      </Gate>

      <Section title="pi remembers, so you don’t repeat yourself">
        <p>pi keeps what you’ve told it so you don’t have to say it twice.</p>
        <p>
          <Link href={`${PI.base}/trust`}>Your chats, your say →</Link>
        </p>
      </Section>

      <Section title="What pi can’t do" tone="soft">
        <Points
          items={[
            {
              lead: "It can’t give legal, medical or financial advice.",
              text: "If you ask, it says so and tells you what it can do instead.",
            },
            {
              lead: "It can’t promise a result.",
              text: "It notes, sorts and shows. It doesn’t decide for you.",
            },
            {
              lead: "It can’t see your business data unless you tell it.",
              text: (
                <Slot kind="CONFIRM">
                  say whether pi can ever access connected data. If not, keep
                  this line.
                </Slot>
              ),
            },
          ]}
        />
      </Section>

      <CtaBlock page="how-it-works" pos="closing" />
    </>
  );
}
