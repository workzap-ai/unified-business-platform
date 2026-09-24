import type { Metadata } from "next";
import { KnowledgeIngestionPage } from "@/features/pi/config/knowledge/knowledge-ingestion-page";

export const metadata: Metadata = { title: "Knowledge ingestion" };

export default function Page() {
  return <KnowledgeIngestionPage />;
}
