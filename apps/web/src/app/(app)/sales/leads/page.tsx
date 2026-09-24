import type { Metadata } from "next";
import { LeadsListPage } from "@/features/sales/leads-list-page";

export const metadata: Metadata = { title: "Leads" };

export default function Page() {
  return <LeadsListPage />;
}
