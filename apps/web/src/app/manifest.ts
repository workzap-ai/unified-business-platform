import type { MetadataRoute } from "next";

/** Owner OS as one installable app: the workspace, its Pi pages and the admin console. */
export default function manifest(): MetadataRoute.Manifest {
  const icon = [{ src: "/icons/owner-os-192.png", sizes: "192x192" }];
  return {
    id: "/",
    name: "Owner OS",
    short_name: "Owner OS",
    description:
      "Run your business workspace, PI and the admin console from your home screen.",
    start_url: "/",
    scope: "/",
    display: "standalone",
    background_color: "#f5f6f3",
    theme_color: "#1c6653",
    categories: ["business", "productivity"],
    icons: [
      {
        src: "/icons/owner-os-192.png",
        sizes: "192x192",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/icons/owner-os-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/icons/owner-os-maskable-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
    shortcuts: [
      { name: "Overview", url: "/", icons: icon },
      { name: "PI inbox", url: "/pi/inbox", icons: icon },
      { name: "Admin console", url: "/operator", icons: icon },
    ],
  };
}
