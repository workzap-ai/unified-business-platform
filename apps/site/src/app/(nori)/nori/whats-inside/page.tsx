import type { Metadata } from "next";
import { NoriInside } from "@/features/nori/nori-page";

export const metadata: Metadata = {
  title: "What’s inside nori | nori by Workzap",
  description:
    "Shops, money, stock, online, marketing and people, each with the numbers, the reasons and the next step.",
  alternates: { canonical: "/nori/whats-inside" },
};

export default function Page() {
  return <NoriInside />;
}
