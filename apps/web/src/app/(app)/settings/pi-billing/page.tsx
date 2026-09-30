import type { Metadata } from "next";
import { PiBillingPage } from "@/features/pi-billing/pi-billing-page";

export const metadata: Metadata = { title: "Pi subscriptions & payments" };
export default function Page() {
  return <PiBillingPage />;
}
