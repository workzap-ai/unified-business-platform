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
  const nori = ["", "/whats-inside", "/how-it-works", "/pricing", "/faq"].map(
    (p) => `${PI.siteUrl}/nori${p}`,
  );
  return [PI.siteUrl, ...nori, ...pi].map((url) => ({ url }));
}
