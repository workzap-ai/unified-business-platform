import type { Metadata } from "next";
import { PiReport } from "@/features/reports/pi-report";

export const metadata: Metadata = { title: "PI analytics report" };

export default function Page() {
  return <PiReport />;
}
