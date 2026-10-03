import type { Metadata } from "next";
import { NoriHow } from "@/features/nori/nori-page";

export const metadata: Metadata = {
  title: "How nori works | nori by Workzap",
  description:
    "Connect your data, let nori read it, and get a short read each morning.",
  alternates: { canonical: "/nori/how-it-works" },
};

export default function Page() {
  return <NoriHow />;
}
