import type { Metadata } from "next";
import { AnalyticsPage } from "@/features/pi/config/analytics/analytics-page";

export const metadata: Metadata = { title: "PI analytics" };

export default function Page() {
  return <AnalyticsPage />;
}
