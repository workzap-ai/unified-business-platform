import { notFound } from "next/navigation";
import { PI } from "@/features/pi/config";
import { Breadcrumbs, piMetadata } from "@/features/pi/meta";
import {
  CtaBlock,
  Face,
  PageIntro,
  Points,
  Section,
  Slot,
} from "@/features/pi/ui";

export const metadata = piMetadata({
  path: "/solutions",
  title: "From sorted problems to a built solution | pi by Workzap",
  description:
    "Once pi has sorted your problems, it can prepare a solution document and a quote. You decide whether to approve, pay and have Workzap build it.",
});

// Written and ready, but hidden until quoting, approval, payment and building really
// work (see PI.live in config.ts). Do not open this gate early.
export default function Solutions() {
  if (!PI.live.solutions) notFound();
  return (
    <>
      <Breadcrumbs path="/solutions" name="From problems to a solution" />
      <PageIntro
        title="From sorted problems to a solution built for you"
        sub="Once your problems are sorted, pi can prepare a solution document and a quote. You decide what happens next."
      >
        <p className="pi-small">
          Payment never happens inside the chat, and pi never asks for card
          numbers. Workzap will never change its bank details by message.
          “Sorted” means noted and grouped. It doesn’t mean solved.
        </p>
      </PageIntro>

      <Section title="The path">
        <Points
          numbered
          items={[
            {
              lead: "Your problems are sorted.",
              text: "You’ve told pi what’s going wrong and seen it on your dashboard.",
            },
            {
              lead: "pi asks if you’d like a solution.",
              text: "Only when you’re ready. pi won’t send a document or a quote unless you say yes.",
            },
            {
              lead: "You get a solution document and a quote.",
              text: (
                <>
                  Shared in the chat and on your dashboard.{" "}
                  <Slot kind="PRODUCT">
                    whether a person at Workzap checks them before they’re sent
                  </Slot>
                </>
              ),
            },
            {
              lead: "You review, ask, and decide.",
              text: "Approve, change, or say no.",
            },
            {
              lead: "You pay, then Workzap begins.",
              text: "Once you’ve approved the quote and your payment is confirmed, Workzap begins your project with a kickoff.",
            },
          ]}
        />
        <ul className="pi-ribbon" aria-label="The five steps">
          <li>
            <Face name="noted" size={88} />
            Sorted
          </li>
          <li>
            <Face name="think" size={88} />
            Preparing
          </li>
          <li>
            <Face name="heads" size={88} />
            The quote needs your decision
          </li>
          <li>
            <Face name="rest" size={88} />
            You decide
          </li>
          <li>
            <Face name="rest" size={88} />
            Build begins
          </li>
        </ul>
      </Section>

      <Section title="Your solution document" tone="soft">
        <p>
          A plain-language document that sets out the solution Workzap would
          build for your problems.
        </p>
        <Points
          items={[
            {
              lead: "Your problems, in your words.",
              text: "Taken from what you told pi, so you can check it’s right.",
            },
            {
              lead: "What Workzap would build.",
              text: (
                <>
                  The solution, described simply.{" "}
                  <Slot kind="WORKZAP">
                    how Workzap describes its solutions — existing modules,
                    custom builds, or both
                  </Slot>
                </>
              ),
            },
            {
              lead: "What it covers.",
              text: (
                <>
                  The parts of your business it touches.{" "}
                  <Slot kind="CONFIRM">
                    only claims Workzap can stand behind — no promised results
                  </Slot>
                </>
              ),
            },
            {
              lead: "What it won’t do.",
              text: "Said plainly, so there are no surprises.",
            },
          ]}
        />
        <p>
          <Slot kind="PRODUCT">
            format — for example a PDF in the chat and on your dashboard
          </Slot>
        </p>
      </Section>

      <Section title="Your quote">
        <p>
          A written quote for building the solution: what’s included, what it
          costs, how long it takes, and how payment works.{" "}
          <Slot kind="WORKZAP">pricing model</Slot>{" "}
          <Slot kind="PRODUCT">what the quote contains</Slot>
        </p>
        <p>
          The quote shows Workzap’s company name and the exact account name, so
          your bank can confirm who you’re paying.{" "}
          <Slot kind="PRODUCT">confirm what the quote shows</Slot>
        </p>
        <p className="pi-small">A quote is an offer. It isn’t a charge.</p>
      </Section>

      <Section title="Check it, change it, or say no" tone="soft">
        <p>
          Read both on your phone or computer. Ask pi questions, or ask for a
          person.{" "}
          <Slot kind="PRODUCT">how a person joins the conversation</Slot> You
          can ask for changes to the quote. Saying no is fine, and nothing is
          charged.{" "}
          <Slot kind="PRODUCT">
            what happens to your sorted problems if you say no
          </Slot>
        </p>
      </Section>

      <Section title="Approve and pay">
        <p>
          When you’re happy, you approve the quote.{" "}
          <Slot kind="PRODUCT">
            how you approve — in the chat, on the dashboard, or by signing
          </Slot>
        </p>
        <Points
          items={[
            {
              lead: "Bank transfer.",
              text: (
                <>
                  The bank details are on your approved quote. Workzap confirms
                  when the transfer arrives.{" "}
                  <Slot kind="PRODUCT">
                    how a transfer is confirmed, and any deposit or milestone
                    payments
                  </Slot>
                </>
              ),
            },
            {
              lead: "Card, on a secure payment page.",
              text: (
                <>
                  You’re sent to a secure Stripe page to pay.{" "}
                  <Slot kind="CONFIRM">
                    Stripe availability depends on where Workzap’s company is
                    registered, and which currencies it can take
                  </Slot>
                </>
              ),
            },
          ]}
        />
        <p style={{ marginTop: 14 }}>
          Either way, payment never happens inside the chat, and pi never asks
          for card numbers. Before you pay, check that the bank details match
          those on your Workzap dashboard.{" "}
          <Slot kind="PRODUCT">
            the dashboard shows the quote and the bank details
          </Slot>{" "}
          <Slot kind="CONFIRM">that Workzap commits to this</Slot>{" "}
          <Slot kind="PRODUCT">
            terms for deposits, refunds and cancellation — state them plainly on
            the quote
          </Slot>
        </p>
      </Section>

      <Section title="Then Workzap builds" tone="soft">
        <p>
          Once your payment is confirmed, Workzap begins your project, starting
          with a kickoff to agree the details.{" "}
          <Slot kind="PRODUCT">
            what Workzap needs from you, when work begins, how you’ll be kept
            updated, and who your contact is; and who owns and may use what’s
            built — state it plainly on the quote
          </Slot>
        </p>
      </Section>

      <Section title="You stay in control">
        <Points
          items={[
            {
              lead: "Nothing is charged until you approve.",
              text: (
                <>
                  Not for the quote, and not for choosing to look.{" "}
                  <Slot kind="CONFIRM">
                    that this matches Workzap’s process, including whether the
                    solution document itself is free
                  </Slot>
                </>
              ),
            },
            {
              lead: "You can stop at any point before paying.",
              text: "No reason needed.",
            },
            {
              lead: "You can ask pi to stop.",
              text: (
                <Slot kind="PRODUCT">how, and what happens to your chats</Slot>
              ),
            },
          ]}
        />
      </Section>

      <CtaBlock page="solutions" pos="closing" />
    </>
  );
}
