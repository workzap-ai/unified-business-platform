import type { ReactNode } from "react";
import { PI } from "@/features/pi/config";
import { FaqItem } from "@/features/pi/client";
import { Breadcrumbs, JsonLd, piMetadata } from "@/features/pi/meta";
import { CtaBlock, PageIntro, Section, Slot } from "@/features/pi/ui";

export const metadata = piMetadata({
  path: "/faq",
  title: "pi FAQ: answers about pi, WhatsApp and your chats",
  description:
    "Is pi a real person? What happens to your chats? Can you make it stop? Plain answers to the questions people ask about pi.",
});

type Gate = "solutions" | "dashboard";
interface Item {
  q: string;
  a: ReactNode;
  // Plain text of the answer, used for the search-engine FAQ markup. Set it only
  // when the visible answer is final text. An answer that still contains a Slot
  // has no `plain`, so it stays out of the markup until it is finished.
  plain?: string;
  gate?: Gate;
}

const sorts = PI.live.dashboard
  ? "notes each one, sorts them, and shows them to you in one place"
  : "notes each one and sorts them";
const whatIsPi = `pi is Workzap’s WhatsApp agent. You chat with it about problems in your business. It ${sorts}. pi is an AI.`;
const sellText = PI.live.solutions
  ? "pi doesn’t pitch while you’re describing a problem. When your problems are sorted, pi asks whether you’d like a solution document and a quote. You can say no."
  : "pi doesn’t pitch while you’re describing a problem.";

const ITEMS: Item[] = [
  { q: "What is pi?", a: whatIsPi, plain: whatIsPi },
  {
    q: "What does “sorted” mean?",
    a: "pi notes your problems and groups similar ones together. It doesn’t mean they’re solved.",
    plain:
      "pi notes your problems and groups similar ones together. It doesn’t mean they’re solved.",
  },
  {
    q: "Is pi a real person?",
    a: "No. pi is an AI. It says so in its first message, and it will tell you again whenever you ask.",
    plain:
      "No. pi is an AI. It says so in its first message, and it will tell you again whenever you ask.",
  },
  {
    q: "How do I start?",
    a: (
      <>
        Tap “Chat with pi on WhatsApp” on this site. WhatsApp opens with a
        message ready to send. You message first and pi replies.{" "}
        <Slot kind="PRODUCT">number or link</Slot>
      </>
    ),
  },
  {
    q: "Does it cost anything?",
    a: (
      <>
        <Slot kind="WORKZAP">
          whether chatting with pi costs anything — Workzap to decide; do not
          publish a price, or the word “free”, until it is decided
        </Slot>
        {PI.live.solutions
          ? " If you later choose a solution, you’ll see a written quote first, and nothing is charged until you approve it."
          : null}
      </>
    ),
  },
  {
    q: "What happens to what I tell pi?",
    a: (
      <Slot kind="PRODUCT">
        what is kept, who at Workzap can see it, and for how long
      </Slot>
    ),
  },
  { q: "Will pi try to sell me something?", a: sellText, plain: sellText },
  {
    q: "What is a solution document?",
    gate: "solutions",
    a: (
      <>
        A plain-language document that sets out the solution Workzap would build
        for the problems you’ve told pi about. pi prepares it only if you ask.{" "}
        <Slot kind="PRODUCT">format and contents</Slot>
      </>
    ),
  },
  {
    q: "What does the quote include?",
    gate: "solutions",
    a: (
      <>
        A written quote for building the solution.{" "}
        <Slot kind="PRODUCT">
          contents — for example what’s included, the cost, the timeline and how
          payment works
        </Slot>{" "}
        A quote is an offer, not a charge.
      </>
    ),
  },
  {
    q: "Do I have to buy anything?",
    gate: "solutions",
    a: (
      <>
        No. Saying no costs nothing.{" "}
        <Slot kind="CONFIRM">that this matches Workzap’s process</Slot>
      </>
    ),
  },
  {
    q: "How do I pay?",
    gate: "solutions",
    a: (
      <>
        Not inside the chat. After you approve a quote, you pay by bank
        transfer, or by card on a secure Stripe payment page. The details come
        with the quote. Workzap will never change its bank details by message.{" "}
        <Slot kind="CONFIRM">payment methods at launch</Slot> Check the bank
        details against those on your Workzap dashboard before you pay.
      </>
    ),
  },
  {
    q: "When does building start?",
    gate: "solutions",
    a: (
      <>
        Once you’ve approved the quote and your payment is confirmed, starting
        with a kickoff to agree the details.{" "}
        <Slot kind="PRODUCT">how long it takes — the quote will say</Slot>
      </>
    ),
  },
  {
    q: "Can I change the quote?",
    gate: "solutions",
    a: (
      <>
        You can ask. <Slot kind="PRODUCT">how changes are handled</Slot>
      </>
    ),
  },
  {
    q: "Who owns what Workzap builds?",
    gate: "solutions",
    a: (
      <Slot kind="PRODUCT">
        ownership and licence terms — state them plainly on the quote, then
        answer here
      </Slot>
    ),
  },
  {
    q: "Can I make pi stop?",
    a: (
      <>
        Yes.{" "}
        <Slot kind="PRODUCT">
          one fixed word to send that is always recognised, and what happens
          next
        </Slot>
      </>
    ),
  },
  {
    q: "What if pi gets something wrong?",
    a: (
      <>
        Tell it, and it will correct its note. If pi can’t help, it says so.{" "}
        <Slot kind="PRODUCT">how to reach a person, if you can</Slot>
      </>
    ),
  },
  {
    q: "What languages does pi speak?",
    a: (
      <Slot kind="CONFIRM">
        launch languages. Draft: English now; Urdu and Arabic planned and
        written by native speakers
      </Slot>
    ),
  },
  {
    q: "Can pi understand voice notes, photos and videos?",
    a: (
      <Slot kind="CONFIRM">
        these worked in a sandbox test, but publish only what is live and
        verified
      </Slot>
    ),
  },
  {
    q: "Can I add pi to a group chat?",
    a: (
      <>
        Right now pi works in one-to-one chats.{" "}
        <Slot kind="CONFIRM">before publishing</Slot>
      </>
    ),
  },
  {
    q: "Is pi from WhatsApp?",
    a: "No. pi is made by Workzap and chats with you through WhatsApp’s business platform. WhatsApp is a trademark of Meta.",
    plain:
      "No. pi is made by Workzap and chats with you through WhatsApp’s business platform. WhatsApp is a trademark of Meta.",
  },
  {
    q: "Where do I see my dashboard?",
    gate: "dashboard",
    a: <Slot kind="PRODUCT">sign-in link and method</Slot>,
  },
  {
    q: "Does pi see my sales or business data?",
    a: (
      <Slot kind="CONFIRM">
        state plainly whether pi can reach any connected data. If it can’t, say:
        pi only knows what you tell it in the chat
      </Slot>
    ),
  },
  {
    q: "Is it safe to share things with pi?",
    a: "Share what you’re comfortable with. Please don’t send card numbers, passwords or other people’s personal details. pi never needs them.",
    plain:
      "Share what you’re comfortable with. Please don’t send card numbers, passwords or other people’s personal details. pi never needs them.",
  },
  {
    q: "Who makes pi, and how do I contact them?",
    a: (
      <>
        pi is made by Workzap. To reach Workzap, message pi on WhatsApp.{" "}
        <Slot kind="CONFIRM">
          pi can hand a chat to a person at Workzap — build the hand-off before
          this answer goes live
        </Slot>
      </>
    ),
  },
];

export default function Faq() {
  const visible = ITEMS.filter((i) => !i.gate || PI.live[i.gate]);
  const schemaItems = visible.filter((i) => i.plain);
  return (
    <>
      <Breadcrumbs path="/faq" name="FAQ" />
      {schemaItems.length > 0 ? (
        <JsonLd
          data={{
            "@context": "https://schema.org",
            "@type": "FAQPage",
            mainEntity: schemaItems.map((i) => ({
              "@type": "Question",
              name: i.q,
              acceptedAnswer: { "@type": "Answer", text: i.plain },
            })),
          }}
        />
      ) : null}
      <PageIntro
        title="Questions about pi"
        sub="Short, plain answers. If yours isn’t here, ask pi."
      />
      <Section>
        <div className="pi-faq">
          <h2 className="pi-sr">All questions</h2>
          {visible.map((i) => (
            <FaqItem key={i.q} question={i.q}>
              <p>{i.a}</p>
            </FaqItem>
          ))}
        </div>
      </Section>
      <CtaBlock page="faq" pos="closing" />
    </>
  );
}
