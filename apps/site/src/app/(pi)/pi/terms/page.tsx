import { Breadcrumbs, piMetadata } from "@/features/pi/meta";
import { PageIntro, Points, Section } from "@/features/pi/ui";

export const metadata = piMetadata({
  path: "/terms",
  title: "Terms for pi | pi by Workzap",
  description:
    "What to know before you use pi, Workzap’s WhatsApp agent: pi is an AI, what it can’t do, and that a quote is an offer and not a charge.",
});

export default function Terms() {
  return (
    <>
      <Breadcrumbs path="/terms" name="Terms" />
      <PageIntro title="Terms for pi" sub="What to know when you message pi." />
      <Section>
        <Points
          items={[
            {
              lead: "pi is an AI.",
              text: "pi is an AI agent made by Workzap. It says so in its first message and whenever you ask.",
            },
            {
              lead: "pi can’t give legal, medical or financial advice.",
              text: "If you ask, it says so and tells you what it can do instead.",
            },
            {
              lead: "pi can’t promise a result.",
              text: "It notes, sorts and shows. It doesn’t decide for you.",
            },
            {
              lead: "A quote is an offer.",
              text: "Nothing is charged until you approve it. Payment never happens inside the chat.",
            },
            {
              lead: "pi and WhatsApp.",
              text: "pi chats with you through WhatsApp’s business platform. WhatsApp is a trademark of Meta. pi isn’t made, run or endorsed by WhatsApp or Meta.",
            },
          ]}
        />
      </Section>
    </>
  );
}
