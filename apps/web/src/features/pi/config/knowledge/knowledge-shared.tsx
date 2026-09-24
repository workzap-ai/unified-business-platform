"use client";

import { SubNav } from "../shared";
import type { KnowledgeDocument } from "../../types";

export function KnowledgeNav() {
  return (
    <SubNav
      label="Knowledge sections"
      items={[
        { href: "/pi/knowledge", label: "Overview", exact: true },
        { href: "/pi/knowledge/sources", label: "Sources" },
        { href: "/pi/knowledge/documents", label: "Documents" },
        { href: "/pi/knowledge/ingestion", label: "Ingestion" },
      ]}
    />
  );
}

export const KNOWLEDGE_HEADER = {
  title: "Knowledge",
  description:
    "Approved company information PI can quote from. Retrieval is always scoped to this workspace and environment.",
};

/** Poll every 3s while any document is still being processed. */
export function pollWhileProcessing(docs: KnowledgeDocument[] | undefined) {
  return docs?.some((d) => d.status === "pending" || d.status === "processing")
    ? 3000
    : false;
}
