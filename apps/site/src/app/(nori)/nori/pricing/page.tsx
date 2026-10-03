import type { Metadata } from "next";
import { NoriPricing } from "@/features/nori/nori-page";

export const metadata: Metadata = {
  title: "nori pricing | nori by Workzap",
  description:
    "A one-time setup, then a simple monthly plan. Every plan has everything. You choose the size and the support.",
  alternates: { canonical: "/nori/pricing" },
};

export default function Page() {
  return <NoriPricing />;
}
