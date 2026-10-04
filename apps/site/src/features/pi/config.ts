// Settings for the pi section of the Workzap site (workzap.ai/pi).
export const PI = {
  siteUrl: "https://workzap.ai",
  base: "/pi",
  // WhatsApp number for pi, digits only with the country code (no "+").
  // Must be a number registered under Workzap's own Meta Business account — never a
  // test provider's number. Until it is set, every button opens /pi/talk-to-pi.
  // Set on 4 Oct 2026 from the owner: +1 (201) 471-3467. If it ever changes, also
  // regenerate public/pi-brand/pi-whatsapp-qr.svg (a QR for wa.me/<number>?text=Hi%20pi).
  whatsappNumber: "12014713467" as string | null,
  // The same number as people read it.
  displayNumber: "+1 201 471 3467",
  whatsappText: "Hi pi",
  // Pages that are written but must stay hidden until the product behind them exists.
  // solutions: opened on 4 Oct 2026 at the owner's request. "How pi solves your problem"
  // is half of the sales pitch, so it is public.
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
