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
  const workzap = ["", "/products", "/company", "/contact"].map(
    (p) => `${PI.siteUrl}${p}`,
  );
  return [...workzap, ...nori, ...pi].map((url) => ({ url }));
}
