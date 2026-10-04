// Shared copy for the Workzap parent site. Only facts the owner has given.

export const APP_URL = "https://app.workzap.ai";
export const TALK = "/pi/talk-to-pi";

export const PRODUCTS = {
  nori: {
    name: "nori",
    full: "nori by Workzap",
    href: "/nori",
    logo: "/nori-brand/nori-lockup-horizontal-color.svg",
    width: 300.77,
    height: 103.1,
    line: "The daily read for the shop.",
    menu: "Reads your sales and stock and picks out the one thing worth looking at today.",
  },
  pi: {
    name: "pi",
    full: "pi by Workzap",
    href: "/pi",
    logo: "/pi-brand/pi-lockup-horizontal-color.svg",
    width: 285.8,
    height: 149.8,
    line: "Workzap’s WhatsApp agent.",
    menu: "Tell pi what is going wrong. Coming soon.",
  },
} as const;

export const AREAS = [
  "Stores and warehouse",
  "Finance",
  "Planning and buying",
  "E-commerce",
  "Marketing and customers",
  "People",
  "Executive and control",
] as const;

export const PRINCIPLES = [
  {
    lead: "AI is always disclosed.",
    text: "pi is an AI, and it says so in its first message.",
  },
  {
    lead: "You decide.",
    text: "You get a solution document and a quote first. Workzap builds only if you say yes.",
  },
  {
    lead: "Payment stays out of the chat.",
    text: "Payment never happens inside a conversation with pi.",
  },
  {
    lead: "Examples are labelled.",
    text: "Any made-up chart, conversation or document on our sites says Illustrative.",
  },
  {
    lead: "We say what is not ready.",
    text: "pi and Vision (CCTV) are coming soon, and our pages say so.",
  },
  {
    lead: "One way to reach us.",
    text: "Every enquiry starts with pi.",
  },
] as const;
