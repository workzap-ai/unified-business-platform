import type { Metadata } from "next";
import { BillingOverviewPage } from "@/features/billing/billing-overview-page";

export const metadata: Metadata = { title: "Billing" };

export default function Page() {
  return <BillingOverviewPage />;
}
