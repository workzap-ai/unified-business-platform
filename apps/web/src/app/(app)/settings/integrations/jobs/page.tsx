import type { Metadata } from "next";
import { JobsPage } from "@/features/integrations/jobs-page";

export const metadata: Metadata = { title: "Sync jobs" };

export default function Page() {
  return <JobsPage />;
}
