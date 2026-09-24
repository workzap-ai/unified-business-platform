import type { Metadata } from "next";
import { ReportsCatalog } from "@/features/reports/reports-catalog";

export const metadata: Metadata = { title: "Reports" };

export default function Page() {
  return <ReportsCatalog />;
}
