import type { Metadata } from "next";
import { KnowledgeSourcesPage } from "@/features/pi/config/knowledge/knowledge-sources-page";

export const metadata: Metadata = { title: "Knowledge sources" };

export default function Page() {
  return <KnowledgeSourcesPage />;
}
