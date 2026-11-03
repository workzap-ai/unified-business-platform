import type { Metadata } from "next";
import { BrainDocumentsPage } from "@/features/pi/workspace/brain-documents-page";

export const metadata: Metadata = { title: "PI documents" };

export default function Page() {
  return <BrainDocumentsPage />;
}
