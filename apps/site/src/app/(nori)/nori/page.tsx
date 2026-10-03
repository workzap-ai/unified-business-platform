import type { Metadata } from "next";
import { NoriPage } from "@/features/nori/nori-page";

export const metadata: Metadata = {
  alternates: { canonical: "/nori" },
};

export default function Page() {
  return <NoriPage />;
}
