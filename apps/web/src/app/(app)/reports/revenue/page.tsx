import type { Metadata } from "next";
import { RevenueReport } from "@/features/reports/revenue-report";

export const metadata: Metadata = { title: "Revenue report" };

export default function Page() {
  return <RevenueReport />;
}
