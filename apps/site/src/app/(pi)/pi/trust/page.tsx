import Link from "next/link";
import { PI } from "@/features/pi/config";
import { TrackOnMount } from "@/features/pi/client";
import { Breadcrumbs, piMetadata } from "@/features/pi/meta";
import { CtaBlock, Gate, PageIntro, Section } from "@/features/pi/ui";

export const metadata = piMetadata({
  path: "/trust",
  title: "Your chats, your say: how pi treats what you tell it",
  description: PI.live.solutions
    ? "pi is an AI and says so. See what pi never asks for, what to share, and how quotes and payment work. Plain answers about your chats."
    : "pi is an AI and says so. See what pi never asks for and what to share. Plain answers about your chats.",
});

export default function Trust() {
  return (
    <>
      <Breadcrumbs path="/trust" name="Your chats, your say" />
      <TrackOnMount name="view_trust" page="trust" />
      <PageIntro
        title="Your chats, your say"
        sub="pi talks to you about your business. Here is what to know before you start."
      />
      <Section title="pi is an AI">
        <p>
          pi is an AI agent made by Workzap. It says so in its first message and
          whenever you ask. It has no human name and no human photo.
        </p>
      </Section>
      <Section title="What pi never asks for" tone="tint">
        <p>
          Card numbers, passwords, other people’s personal details, or payment
          inside the chat. If you send them, pi will ask you not to.
        </p>
      </Section>
      <Gate name="solutions">
        <Section title="Quotes and payment" tone="soft">
          <p>
            A quote from Workzap is an offer. Nothing is charged until you
            approve it. You pay by bank transfer, never inside the chat, and pi
            never asks for card numbers.
          </p>
        </Section>
      </Gate>
      <Section title="Privacy and terms">
        <p>
          Workzap’s <Link href={`${PI.base}/privacy`}>privacy notice</Link> and{" "}
          <Link href={`${PI.base}/terms`}>terms</Link> apply to pi.
        </p>
      </Section>
      <Section title="pi and WhatsApp" tone="soft">
        <p>
          pi chats with you through WhatsApp’s business platform. WhatsApp is a
          trademark of Meta. pi isn’t made, run or endorsed by WhatsApp or Meta.
        </p>
      </Section>
      <Section title="Something not right?" tone="tint">
        <p>Tell pi in the chat.</p>
      </Section>
      <CtaBlock page="trust" pos="closing" />
    </>
  );
}
