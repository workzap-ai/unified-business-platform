// Settings for the pi section of the Workzap site (workzap.ai/pi).
export const PI = {
  siteUrl: "https://workzap.ai",
  base: "/pi",
  // WhatsApp number for pi, digits only with the country code (no "+").
  // Must be a number registered under Workzap's own Meta Business account — never a
  // test provider's number. Until it is set, every button opens /pi/talk-to-pi.
  whatsappNumber: null as string | null,
  whatsappText: "Hi pi",
  // Pages that are written but must stay hidden until the product behind them exists.
  // solutions: opened on 4 Oct 2026 at the owner's request. "How pi solves your problem"
  // is half of the sales pitch, so it is public. The unfinished answers inside it are
  // still Slot markers, so a production deploy stays blocked until they are resolved.
  live: {
    dashboard: false as boolean,
    solutions: true as boolean,
  },
} as const;

// A production deploy on Vercel refuses to build while anything is unfinished.
export const IS_PRODUCTION = process.env.VERCEL_ENV === "production";

export function assertReadyToPublish() {
  if (!IS_PRODUCTION) return;
  if (!PI.whatsappNumber) {
    throw new Error(
      "pi: whatsappNumber is not set. Register pi's number under Workzap's own Meta Business account and set it in src/features/pi/config.ts before a production deploy.",
    );
  }
}
