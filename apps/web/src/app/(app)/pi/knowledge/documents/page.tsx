import type { Metadata } from "next";
import { KnowledgeDocumentsPage } from "@/features/pi/config/knowledge/knowledge-documents-page";

export const metadata: Metadata = { title: "Knowledge documents" };

export default function Page() {
  return <KnowledgeDocumentsPage />;
}
