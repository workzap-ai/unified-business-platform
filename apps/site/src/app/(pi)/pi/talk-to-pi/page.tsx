import Image from "next/image";
import Link from "next/link";
import { PI } from "@/features/pi/config";
import { TrackOnMount, WhatsAppButton } from "@/features/pi/client";
import { Breadcrumbs, piMetadata } from "@/features/pi/meta";
import { Chat, PageIntro, Points, Section, Slot } from "@/features/pi/ui";

export const metadata = piMetadata({
  path: "/talk-to-pi",
  title: "Start a chat with pi on WhatsApp | pi by Workzap",
  description:
    "Message pi on WhatsApp to start. You message first and pi replies, telling you it’s an AI. Here is what happens and what to share.",
});

export default function TalkToPi() {
  return (
    <>
      <Breadcrumbs path="/talk-to-pi" name="Start a chat" />
      <TrackOnMount name="open_talk_page" page="talk-to-pi" />
      <PageIntro
        title="Start a chat with pi"
        sub="You message first. pi replies."
      />

      <Section title="On your phone">
        <WhatsAppButton
          page="talk-to-pi"
          pos="phone"
          label="Open WhatsApp"
          openDirect
        />
        <p className="pi-small">
          WhatsApp opens with “Hi pi” ready to send. Just tap send.
        </p>
        {PI.whatsappNumber ? (
          <p>
            Or message pi directly on WhatsApp at{" "}
            <strong>{PI.displayNumber}</strong>.
          </p>
        ) : null}
      </Section>

      <Section title="On a computer" tone="soft">
        <p>Scan this code with your phone’s camera.</p>
        <Image
          className="pi-qr-img"
          src="/pi-brand/pi-whatsapp-qr.svg"
          alt={`QR code that opens a WhatsApp chat with pi at ${PI.displayNumber}`}
          width={240}
          height={240}
          unoptimized
        />
      </Section>

      <Section title="What pi says first">
        <Chat
          lines={[
            [
              "pi",
              "Hi, I’m pi, an AI from Workzap. Tell me what’s going wrong in your business and I’ll start on it.",
            ],
          ]}
        />
      </Section>

      <Section title="What happens after you send it" tone="soft">
        <Points
          items={[
            {
              lead: "pi replies.",
              text: "It tells you it’s an AI, and asks what’s going wrong.",
            },
            {
              lead: "You say what’s wrong.",
              text: "In your own words, at your own pace.",
            },
            {
              lead: "pi notes and sorts it.",
              text: "And tells you what it has noted.",
            },
            ...(PI.live.dashboard
              ? [
                  {
                    lead: "You see it in one place.",
                    text: (
                      <Slot kind="PRODUCT">
                        when and how the dashboard link reaches you, and whether
                        you need an account first
                      </Slot>
                    ),
                  },
                ]
              : []),
          ]}
        />
      </Section>

      <Section title="Before you start">
        <Points
          items={[
            {
              lead: "pi is an AI.",
              text: "It will say so, and again whenever you ask.",
            },
            {
              lead: "Keep some things out of the chat.",
              text: "Please don’t send card numbers, passwords or other people’s personal details. pi never needs them.",
            },
            {
              lead: "You can stop any time.",
              text: (
                <Slot kind="PRODUCT">
                  the words to send, and what happens next
                </Slot>
              ),
            },
            {
              lead: "One-to-one chats only, for now.",
              text: (
                <Slot kind="CONFIRM">whether pi can be added to a group</Slot>
              ),
            },
          ]}
        />
        <p className="pi-small">
          Workzap’s <Link href={`${PI.base}/terms`}>Terms</Link> and{" "}
          <Link href={`${PI.base}/privacy`}>Privacy notice</Link> apply when you
          message pi.
        </p>
      </Section>

      <Section title="WhatsApp didn’t open?" tone="soft">
        <p>
          Install WhatsApp from your phone’s app store, or open WhatsApp Web,
          then message <Slot kind="PRODUCT">pi’s number</Slot>.
        </p>
        <p>
          <Link href={`${PI.base}/talk-to-pi/help`}>More help →</Link>
        </p>
      </Section>
    </>
  );
}
