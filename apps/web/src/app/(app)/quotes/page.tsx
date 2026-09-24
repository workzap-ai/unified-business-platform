import type { Metadata } from "next";
import { QuotesListPage } from "@/features/documents/quotes-list-page";

export const metadata: Metadata = { title: "Quotes" };

export default function Page() {
  return <QuotesListPage />;
}
