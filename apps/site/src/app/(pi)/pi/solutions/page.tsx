import { notFound } from "next/navigation";
import { PI } from "@/features/pi/config";
import { Breadcrumbs, piMetadata } from "@/features/pi/meta";
import { CtaBlock, Face, PageIntro, Points, Section } from "@/features/pi/ui";

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
          numbers. “Sorted” means noted and grouped. It doesn’t mean solved.
        </p>
      </PageIntro>

      <Section title="The path">
        <Points
          numbered
          items={[
            {
              lead: "Your problems are sorted.",
              text: "You’ve told pi what’s going wrong and seen what it has noted.",
            },
            {
              lead: "pi asks if you’d like a solution.",
              text: "Only when you’re ready. pi won’t send a document or a quote unless you say yes.",
            },
            {
              lead: "You get a solution document and a quote.",
              text: "Shared in the chat.",
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
              text: "The solution, described simply.",
            },
            {
              lead: "What it covers.",
              text: "The parts of your business it touches.",
            },
            {
              lead: "What it won’t do.",
              text: "Said plainly, so there are no surprises.",
            },
          ]}
        />
      </Section>

      <Section title="Your quote">
        <p>
          A written quote for building the solution: what’s included, what it
          costs, how long it takes, and how payment works.
        </p>
        <p className="pi-small">A quote is an offer. It isn’t a charge.</p>
      </Section>

      <Section title="Check it, change it, or say no" tone="soft">
        <p>
          Read both on your phone or computer. Ask pi questions. You can ask for
          changes to the quote. Saying no is fine, and nothing is charged.
        </p>
      </Section>

      <Section title="Approve and pay">
        <p>When you’re happy, you approve the quote.</p>
        <Points
          items={[
            {
              lead: "Bank transfer.",
              text: "The bank details are on your approved quote. Workzap confirms when the transfer arrives.",
            },
          ]}
        />
        <p style={{ marginTop: 14 }}>
          Payment never happens inside the chat, and pi never asks for card
          numbers.
        </p>
      </Section>

      <Section title="Then Workzap builds" tone="soft">
        <p>
          Once your payment is confirmed, Workzap begins your project, starting
          with a kickoff to agree the details.
        </p>
      </Section>

      <Section title="You stay in control">
        <Points
          items={[
            {
              lead: "Nothing is charged until you approve.",
              text: "A quote is an offer, not a charge.",
            },
            {
              lead: "You can stop at any point before paying.",
              text: "No reason needed.",
            },
          ]}
        />
      </Section>

      <CtaBlock page="solutions" pos="closing" />
    </>
  );
}
