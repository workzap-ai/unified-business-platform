import type { Metadata } from "next";
import { PiOverviewPage } from "@/features/pi/workspace/pi-overview-page";

export const metadata: Metadata = { title: "PI overview" };

export default function Page() {
  return <PiOverviewPage />;
}
