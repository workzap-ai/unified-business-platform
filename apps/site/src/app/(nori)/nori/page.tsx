import type { Metadata } from "next";
import { NoriHome } from "@/features/nori/nori-page";

export const metadata: Metadata = {
  alternates: { canonical: "/nori" },
};

export default function Page() {
  return <NoriHome />;
}
