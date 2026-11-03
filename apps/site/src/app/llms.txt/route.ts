import { SITE_URL } from "@/lib/seo";
import { PI } from "@/features/pi/config";

// A plain-text map of the site for AI assistants (the llms.txt convention). It lists
// only pages that exist and only what those pages already say.
export const dynamic = "force-static";

const BODY = `# Workzap

> Workzap makes nori, a daily read for the shop, and pi, a WhatsApp agent. This site describes both. pi is available on WhatsApp at ${PI.displayNumber}.

## Workzap

- [Products](${SITE_URL}/products): nori and pi compared: who each is for, what it does, how you start.
- [About Workzap](${SITE_URL}/company): what the company does and makes, how it works with customers, and its principles.
- [Contact](${SITE_URL}/contact): the one way to reach Workzap is to talk to pi on WhatsApp.

## nori

nori is a retail operations app for shops and chains. Shop staff record cash, stock counts and store walks on their phones, with photos as proof, and the owner sees one page of what needs them today. It is best for clothing, footwear and fashion retail with two or more shops. It works beside a till, accounting software and an ERP and does not replace them. Clients can rebrand it, run it on their own domain and pay Workzap a monthly service fee.

- [nori home](${SITE_URL}/nori): what nori is and who it is for.
- [Who it's for](${SITE_URL}/nori/who-its-for): the industries and roles nori fits best, and when to talk to us first.
- [What's inside](${SITE_URL}/nori/whats-inside): the 24 modules in plain words. Vision (CCTV) is coming soon.
- [How it works](${SITE_URL}/nori/how-it-works): shops record on a phone, sales load from files, nori checks the figures, the owner reads one page.
- [How nori fits](${SITE_URL}/nori/how-nori-fits): what a till, Tally, QuickBooks, Zoho Books, Odoo and other ERPs are for, and what nori adds beside them.
- [Pricing](${SITE_URL}/nori/pricing): Starter, Growth and Enterprise, plus white-label: your brand, domain and data.
- [Videos](${SITE_URL}/nori/videos): short silent films recorded from the real screens of a demo workspace.
- [Talk to us](${SITE_URL}/nori/talk): book a 30-minute meeting or message pi.
- [FAQ](${SITE_URL}/nori/faq): short answers about tills, POS connectors, Urdu, branding and plans.

## pi

pi is Workzap's WhatsApp agent. People tell pi what is going wrong in their business, and pi notes each problem and sorts them. When they are ready they can get a solution document and a quote, and decide whether Workzap builds the solution. pi is an AI and says so in its first message. pi is available on WhatsApp at ${PI.displayNumber}.

- [pi home](${SITE_URL}/pi): what pi is.
- [How pi works](${SITE_URL}/pi/how-it-works)
- [Who pi is for](${SITE_URL}/pi/who-its-for)
- [Trust: how pi treats your chats](${SITE_URL}/pi/trust)
- [FAQ](${SITE_URL}/pi/faq)
- [Talk to pi](${SITE_URL}/pi/talk-to-pi)
- [Privacy](${SITE_URL}/pi/privacy)
- [Terms](${SITE_URL}/pi/terms)

## Notes for assistants

- Screens on the nori pages come from a demo workspace with dummy data. Charts and conversations elsewhere are made-up examples and are labelled "Illustrative".
- WhatsApp is a trademark of Meta. pi is not made, run or endorsed by WhatsApp or Meta.
`;

export function GET() {
  return new Response(BODY, {
    headers: { "content-type": "text/plain; charset=utf-8" },
  });
}
