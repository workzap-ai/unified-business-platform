import Link from "next/link";
import { Closing, PageHead, PI_CONTACT, Shell, TALK } from "./chrome";

// Short answers. Anything not confirmed by Workzap says "ask us".
export const NORI_FAQ = [
  {
    question: "What is nori?",
    answer:
      "nori is a retail operations app from Workzap. Shop staff record cash, stock counts and store walks on their phones, with photos as proof. The owner sees one page of what needs them today.",
  },
  {
    question: "Who is nori for?",
    answer:
      "Owners of shops and chains that sell goods by style and size, such as clothing and footwear, and the heads of operations and finance who work for them. It is best with two or more shops.",
  },
  {
    question: "Do I still need my till, accounts or Odoo?",
    answer:
      "Yes. nori works beside your till, your accounts and your warehouse system, and does not replace them. It is not an ERP. You do not need Odoo or any other ERP to use nori. If you have one, keep it.",
  },
  {
    question: "How do my numbers get into nori?",
    answer:
      "Sales and stock load from CSV, Excel or Google Sheets. An optional Shopify sync brings in online orders. Shop staff record cash counts, store walks and stock counts on their phones.",
  },
  {
    question: "Can you connect nori to my POS?",
    answer:
      "Yes, on request. Tell us which POS you use and we build the connector. Ask us for the details on a call.",
  },
  {
    question: "Can my shop staff use it in Urdu?",
    answer:
      "Yes, on the shop-floor pages, which have an Urdu and English switch. The Help Center also understands Roman Urdu.",
  },
  {
    question: "Does it work on a phone?",
    answer:
      "Yes. nori installs on a phone like an app, with no app store. Owners can read the same pages on a phone or at a desk.",
  },
  {
    question: "Will nori decide things for me?",
    answer:
      "No. nori shows the figure and what it is compared with. The owner decides. The AI assistant answers only from data you can already see.",
  },
  {
    question: "Who sees what?",
    answer:
      "There are four roles: Owner, Admin, Member and Viewer. An owner or admin can narrow what a member sees. An outside consultant can have a view that shows operations but never sales, margin or profit.",
  },
  {
    question: "Can I use my own brand and domain?",
    answer:
      "Yes. You can change the logo, name, colours and sign-in page in Settings, and run nori on your own domain. You host it and run it day to day, you put in your own data, and you pay Workzap a service fee every month.",
  },
  {
    question: "Does nori send SMS to my customers?",
    answer:
      "Not by itself. You draft a message for a group of customers and an owner or admin approves it. It then goes out through your own SMS gateway.",
  },
  {
    question: "Does nori file my sales tax or connect to FBR?",
    answer:
      "No. nori is not a till and is not connected to FBR. If your shop needs an FBR-integrated till, that stays your till’s job. Ask your tax adviser which rules apply to you.",
  },
  {
    question: "What does it cost?",
    answer:
      "There are three plans: Starter for one store, Growth for up to 10 outlets and Enterprise for chains and groups. Every plan includes every module. We give you the price on a 30-minute call.",
  },
  {
    question: "Are the screens on this site real?",
    answer:
      "Yes. They come from a demo workspace with dummy data. They show how nori looks and works, not a real shop’s results.",
  },
];

export function NoriFaq() {
  return (
    <Shell current="/nori/faq">
      <PageHead
        label="FAQ"
        title="nori: questions, answered."
        lead="Short answers to what owners ask first."
      />
      <section className="nx-section nx-white">
        <div className="nx-wrap">
          <dl className="nx-faq">
            {NORI_FAQ.map((q) => (
              <div key={q.question} className="nx-faq-item">
                <dt>
                  <h2>{q.question}</h2>
                </dt>
                <dd>{q.answer}</dd>
              </div>
            ))}
          </dl>
          <p className="nv-more">
            Something else? <Link href={TALK}>Book a meeting</Link> or{" "}
            <Link href={PI_CONTACT}>message pi on WhatsApp</Link>.
          </p>
        </div>
      </section>
      <Closing />
    </Shell>
  );
}
