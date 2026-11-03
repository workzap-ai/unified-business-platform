// The nori films. Each is a silent film built from real screens of the demo workspace
// (dummy data). Files live in public/nori-video. The transcript is the on-screen captions,
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
    seconds: 42,
    file: "/nori-video/nori-morning.mp4",
    poster: "/nori-video/nori-morning.jpg",
    transcript: [
      "It is 8:10 in the morning. You open nori.",
      "Yesterday’s sales, next to the usual pace.",
      "Shops that are behind. Numbers that do not tie.",
      "Open defects. Demands waiting for the warehouse.",
      "Shops ask the warehouse for stock.",
      "You approve a request. The decision is yours.",
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
