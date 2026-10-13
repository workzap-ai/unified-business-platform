import type { Metadata } from "next";
import { HealthPage } from "@/features/pi/workspace/health-page";

export const metadata: Metadata = { title: "pi Health" };

export default function Page() {
  return <HealthPage />;
}
