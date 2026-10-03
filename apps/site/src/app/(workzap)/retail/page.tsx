import type { Metadata } from "next";
import { RetailPage } from "@/features/retail/retail-page";

export const metadata: Metadata = {
  alternates: { canonical: "/retail" },
};

export default function Page() {
  return <RetailPage />;
}
