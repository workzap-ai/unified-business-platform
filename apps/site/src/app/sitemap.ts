import type { MetadataRoute } from "next";
import { PI } from "@/features/pi/config";

export default function sitemap(): MetadataRoute.Sitemap {
  const pi = [
    "",
    "/how-it-works",
    "/talk-to-pi",
    "/talk-to-pi/help",
    "/who-its-for",
    "/trust",
    "/faq",
    "/privacy",
    "/terms",
    ...(PI.live.dashboard ? ["/dashboard"] : []),
    ...(PI.live.solutions ? ["/solutions"] : []),
  ].map((p) => `${PI.siteUrl}${PI.base}${p}`);
  return [PI.siteUrl, `${PI.siteUrl}/retail`, ...pi].map((url) => ({ url }));
}
