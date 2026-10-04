import { SITE_URL } from "@/lib/seo";

// A plain-text map of the site for AI assistants (the llms.txt convention). It lists
// only pages that exist and only what those pages already say.
export const dynamic = "force-static";

const BODY = `# Workzap

> Workzap makes nori, a daily read for the shop, and pi, a WhatsApp agent. This site describes both. pi has not launched yet.

## Workzap

- [Products](${SITE_URL}/products): nori and pi compared: who each is for, what it does, how you start.
- [About Workzap](${SITE_URL}/company): what the company does and makes, how it works with customers, and its principles.
- [Contact](${SITE_URL}/contact): the one way to reach Workzap is to talk to pi on WhatsApp.

## nori

nori reads a shop's sales and stock and picks out the one thing worth looking at today. It gives a short read each morning from the shop's own numbers.

- [nori home](${SITE_URL}/nori): what nori is and why it exists.
- [What's inside](${SITE_URL}/nori/whats-inside): the seven areas nori covers: stores and warehouse, finance, planning and buying, e-commerce, marketing and customers, people, and executive and control. Vision (CCTV) is coming soon.
- [How it works](${SITE_URL}/nori/how-it-works): connect your data, nori reads it, you get the read.
- [Pricing](${SITE_URL}/nori/pricing): Starter, Growth and Enterprise. Every plan has everything except Vision (CCTV), which is coming soon. Plans differ by size and support.
- [FAQ](${SITE_URL}/nori/faq): short answers about what nori reads, how data gets in, and who decides.

## pi

pi is Workzap's WhatsApp agent. People tell pi what is going wrong in their business, and pi notes each problem and sorts them. When they are ready they can get a solution document and a quote, and decide whether Workzap builds the solution. pi is an AI and says so in its first message. pi is not launched yet.

- [pi home](${SITE_URL}/pi): what pi is.
- [How pi works](${SITE_URL}/pi/how-it-works)
- [Who pi is for](${SITE_URL}/pi/who-its-for)
- [Trust: how pi treats your chats](${SITE_URL}/pi/trust)
- [FAQ](${SITE_URL}/pi/faq)
- [Talk to pi](${SITE_URL}/pi/talk-to-pi)
- [Privacy](${SITE_URL}/pi/privacy)
- [Terms](${SITE_URL}/pi/terms)

## Notes for assistants

- Charts and conversations on these pages are made-up examples and are labelled "Illustrative".
- WhatsApp is a trademark of Meta. pi is not made, run or endorsed by WhatsApp or Meta.
`;

export function GET() {
  return new Response(BODY, {
    headers: { "content-type": "text/plain; charset=utf-8" },
  });
}
