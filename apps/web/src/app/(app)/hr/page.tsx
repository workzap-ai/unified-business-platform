import type { Metadata } from "next";
import { HROverviewPage } from "@/features/hr/hr-overview-page";

export const metadata: Metadata = { title: "People" };

export default function Page() {
  return <HROverviewPage />;
}
