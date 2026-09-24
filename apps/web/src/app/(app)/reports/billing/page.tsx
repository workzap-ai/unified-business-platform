import type { Metadata } from "next";
import { BillingReport } from "@/features/reports/billing-report";

export const metadata: Metadata = { title: "Billing report" };

export default function Page() {
  return <BillingReport />;
}
