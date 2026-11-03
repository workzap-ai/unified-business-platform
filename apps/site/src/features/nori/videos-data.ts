// The nori films, built from real nori screens. Files live in public/nori-video. The transcript is the on-screen captions,
// in order, so people without sound and search engines can read the film.
export interface Film {
  slug: string;
  title: string;
  line: string;
  seconds: number;
  file: string;
  poster: string;
  transcript: string[];
}

export const FILMS: Film[] = [
  {
    slug: "morning",
    title: "A morning with nori",
    line: "What sold, which shops are behind, what does not tie.",
    seconds: 65,
    file: "/nori-video/nori-morning.mp4",
    poster: "/nori-video/nori-morning.jpg",
    transcript: [
      "It is ten past eight in the morning, and you open nori.",
      "Yesterday’s sales are on one page, for every shop.",
      "You can see which shops are behind, before anyone has to tell you.",
      "You can see which numbers do not tie, and the gap is shown.",
      "Discounts at the till, stock across the shops, all in one place.",
      "Shops record their work on their phones, with photos as proof.",
      "Daily checks and cash counts are done the same way, and you see who is late.",
      "A request is waiting for you. You approve it. The decision is yours.",
      "Five minutes, one page. You know which shop is slipping before the week is out.",
      "Talk to us for thirty minutes.",
    ],
  },
  {
    slug: "stock",
    title: "Stock that is stuck, lost or trapped",
    line: "Where the stock money is, and what to do first.",
    seconds: 42,
    file: "/nori-video/nori-stock.mp4",
    poster: "/nori-video/nori-stock.jpg",
    transcript: [
      "Planning shows where the stock money is.",
      "Stock that ran out, and stock in the wrong shop.",
      "Stars: keep in stock. Traps: re-price. Dogs: clear.",
      "A request is tracked: open, on the way, received.",
      "Every day each shop counts a round of items.",
      "Find where the size a customer wants is held.",
    ],
  },
  {
    slug: "checks",
    title: "Are the shops doing their checks?",
    line: "Store walks, stock counts, cash and discounts, with proof.",
    seconds: 45,
    file: "/nori-video/nori-checks.mp4",
    poster: "/nori-video/nori-checks.jpg",
    transcript: [
      "Each day a shop is walked. A week strip shows it.",
      "Shop staff can switch to Urdu.",
      "A calendar shows on time, missed and to do.",
      "nori ranks which shop needs a visit first.",
      "The drawer is counted against the standard float.",
      "Discounts at the till are compared across shops.",
    ],
  },
];
