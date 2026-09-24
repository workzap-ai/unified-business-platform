import type { Metadata } from "next";
import { QuoteApprovalsPage } from "@/features/documents/quote-approvals-page";

export const metadata: Metadata = { title: "Quote approvals" };

export default function Page() {
  return <QuoteApprovalsPage />;
}
