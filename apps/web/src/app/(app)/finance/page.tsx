import type { Metadata } from "next";
import { FinanceOverviewPage } from "@/features/finance/finance-overview-page";

export const metadata: Metadata = { title: "Finance" };

export default function Page() {
  return <FinanceOverviewPage />;
}
