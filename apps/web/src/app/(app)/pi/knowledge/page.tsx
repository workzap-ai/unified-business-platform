import type { Metadata } from "next";
import { KnowledgeOverviewPage } from "@/features/pi/config/knowledge/knowledge-overview-page";

export const metadata: Metadata = { title: "PI knowledge" };

export default function Page() {
  return <KnowledgeOverviewPage />;
}
