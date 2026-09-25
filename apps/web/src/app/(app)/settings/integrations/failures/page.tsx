import type { Metadata } from "next";
import { FailuresPage } from "@/features/integrations/failures-page";

export const metadata: Metadata = { title: "Integration failures" };

export default function Page() {
  return <FailuresPage />;
}
