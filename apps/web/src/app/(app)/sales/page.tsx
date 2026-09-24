import type { Metadata } from "next";
import { SalesOverviewPage } from "@/features/sales/sales-overview-page";

export const metadata: Metadata = { title: "Sales" };

export default function Page() {
  return <SalesOverviewPage />;
}
