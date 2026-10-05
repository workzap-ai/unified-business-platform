import type { MetadataRoute } from "next";

/** The pi app (for businesses) as an installable app. pi Customer has its own
 * manifest under /customer so the two install as separate apps. */
export default function manifest(): MetadataRoute.Manifest {
  return {
    id: "/home",
    name: "pi — your business assistant",
    short_name: "pi",
    description:
      "Your WhatsApp inbox, customers and pi's answers, one tap from your home screen.",
    start_url: "/home",
    scope: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#f6f6fb",
    theme_color: "#5a47f5",
    categories: ["business", "productivity"],
    icons: [
      {
        src: "/icons/pi-192.png",
        sizes: "192x192",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/icons/pi-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/icons/pi-maskable-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
    shortcuts: [
      {
        name: "Inbox",
        url: "/inbox",
        icons: [{ src: "/icons/pi-192.png", sizes: "192x192" }],
      },
      {
        name: "Problems",
        url: "/problems",
        icons: [{ src: "/icons/pi-192.png", sizes: "192x192" }],
      },
    ],
  };
}
