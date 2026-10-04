import { PI } from "@/features/pi/config";
import { FaqItem } from "@/features/pi/client";
import { Breadcrumbs, JsonLd, piMetadata } from "@/features/pi/meta";
import { CtaBlock, PageIntro, Section } from "@/features/pi/ui";

export const metadata = piMetadata({
  path: "/faq",
  title: "pi FAQ: answers about pi, WhatsApp and your chats",
  description:
    "Is pi a real person? How do you start a chat? What does “sorted” mean? Plain answers to the questions people ask about pi on WhatsApp.",
});

type Gate = "solutions" | "dashboard";
interface Item {
  q: string;
  // Plain text of the answer. It is shown on the page and used for the
  // search-engine FAQ markup, so the two can never differ.
  a: string;
  gate?: Gate;
}

const sorts = PI.live.dashboard
  ? "notes each one, sorts them, and shows them to you in one place"
  : "notes each one and sorts them";
const whatIsPi = `pi is Workzap’s WhatsApp agent. You chat with it about problems in your business. It ${sorts}. pi is an AI.`;
const sellText = PI.live.solutions
  ? "pi doesn’t pitch while you’re describing a problem. When your problems are sorted, pi asks whether you’d like a solution document and a quote. You can say no."
  : "pi doesn’t pitch while you’re describing a problem.";
const startText = PI.whatsappNumber
  ? `Tap “Chat with pi on WhatsApp” on this site. WhatsApp opens with a message ready to send. You message first and pi replies. Or message pi directly on WhatsApp at ${PI.displayNumber}.`
  : "Tap “Chat with pi on WhatsApp” on this site. WhatsApp opens with a message ready to send. You message first and pi replies.";

const ITEMS: Item[] = [
  { q: "What is pi?", a: whatIsPi },
  {
    q: "What does “sorted” mean?",
    a: "pi notes your problems and groups similar ones together. It doesn’t mean they’re solved.",
  },
  {
    q: "Is pi a real person?",
    a: "No. pi is an AI. It says so in its first message, and it will tell you again whenever you ask.",
  },
  { q: "How do I start?", a: startText },
  { q: "Will pi try to sell me something?", a: sellText },
  {
    q: "What is a solution document?",
    gate: "solutions",
    a: "A plain-language document that sets out the solution Workzap would build for the problems you’ve told pi about. pi prepares it only if you ask.",
  },
  {
    q: "What does the quote include?",
    gate: "solutions",
    a: "A written quote for building the solution. A quote is an offer, not a charge.",
  },
  {
    q: "Do I have to buy anything?",
    gate: "solutions",
    a: "No. You can say no, and nothing is charged until you approve a quote.",
  },
  {
    q: "How do I pay?",
    gate: "solutions",
    a: "Not inside the chat. After you approve a quote, you pay by bank transfer. The details come with the quote.",
  },
  {
    q: "When does building start?",
    gate: "solutions",
    a: "Once you’ve approved the quote and your payment is confirmed, Workzap begins with a kickoff to agree the details.",
  },
  {
    q: "Can I change the quote?",
    gate: "solutions",
    a: "You can ask for changes to the quote.",
  },
  {
    q: "What if pi gets something wrong?",
    a: "Tell it, and it will correct its note. If pi can’t help, it says so.",
  },
  {
    q: "Is pi from WhatsApp?",
    a: "No. pi is made by Workzap and chats with you through WhatsApp’s business platform. WhatsApp is a trademark of Meta.",
  },
  {
    q: "Is it safe to share things with pi?",
    a: "Share what you’re comfortable with. Please don’t send card numbers, passwords or other people’s personal details. pi never needs them.",
  },
  {
    q: "Who makes pi, and how do I contact them?",
    a: "pi is made by Workzap. To reach Workzap, message pi on WhatsApp.",
  },
];

export default function Faq() {
  const visible = ITEMS.filter(
    (i) => (!i.gate || PI.live[i.gate]) && i.a.trim(),
  );
  return (
    <>
      <Breadcrumbs path="/faq" name="FAQ" />
      {visible.length > 0 ? (
        <JsonLd
          data={{
            "@context": "https://schema.org",
            "@type": "FAQPage",
            mainEntity: visible.map((i) => ({
              "@type": "Question",
              name: i.q,
              acceptedAnswer: { "@type": "Answer", text: i.a },
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
