import type { Metadata } from "next";
import { HealthPage } from "@/features/integrations/health-page";

export const metadata: Metadata = { title: "Integration health" };

export default function Page() {
  return <HealthPage />;
}
