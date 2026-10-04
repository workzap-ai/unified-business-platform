import { Breadcrumbs, piMetadata } from "@/features/pi/meta";
import { PageIntro, Points, Section } from "@/features/pi/ui";

export const metadata = piMetadata({
  path: "/privacy",
  title: "Privacy notice for pi | pi by Workzap",
  description:
    "What to know about your chats with pi, Workzap’s WhatsApp agent: what to share, what pi never asks for, and how pi reaches you through WhatsApp.",
});

export default function Privacy() {
  return (
    <>
      <Breadcrumbs path="/privacy" name="Privacy notice" />
      <PageIntro
        title="Privacy notice for pi"
        sub="What to know before you tell pi about your business."
      />
      <Section>
        <Points
          items={[
            {
              lead: "You choose what to tell pi.",
              text: "Share what you’re comfortable with.",
            },
            {
              lead: "What pi never asks for.",
              text: "Card numbers, passwords or other people’s personal details. Please don’t send them. pi never needs them.",
            },
            {
              lead: "What pi remembers.",
              text: "pi keeps what you’ve told it so you don’t have to say it twice.",
            },
            {
              lead: "WhatsApp.",
              text: "pi chats with you through WhatsApp’s business platform. WhatsApp is a trademark of Meta. pi isn’t made, run or endorsed by WhatsApp or Meta.",
            },
          ]}
        />
      </Section>
    </>
  );
}
