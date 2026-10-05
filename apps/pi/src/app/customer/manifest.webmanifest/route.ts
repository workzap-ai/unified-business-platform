/** pi Customer as its own installable app (separate from the business pi app). */
export const dynamic = "force-static";

export function GET() {
  return Response.json(
    {
      id: "/customer",
      name: "pi Customer — your chats with businesses",
      short_name: "pi Customer",
      description:
        "See your WhatsApp chats with businesses and where each of your requests stands.",
      start_url: "/customer",
      scope: "/customer",
      display: "standalone",
      orientation: "portrait",
      background_color: "#f6f6fb",
      theme_color: "#5a47f5",
      categories: ["lifestyle", "productivity"],
      icons: [
        {
          src: "/icons/customer-192.png",
          sizes: "192x192",
          type: "image/png",
          purpose: "any",
        },
        {
          src: "/icons/customer-512.png",
          sizes: "512x512",
          type: "image/png",
          purpose: "any",
        },
        {
          src: "/icons/customer-maskable-512.png",
          sizes: "512x512",
          type: "image/png",
          purpose: "maskable",
        },
      ],
    },
    { headers: { "Content-Type": "application/manifest+json" } },
  );
}
