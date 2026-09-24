import type { Metadata } from "next";
import { QuotesReport } from "@/features/reports/quotes-report";

export const metadata: Metadata = { title: "Quotes report" };

export default function Page() {
  return <QuotesReport />;
}
