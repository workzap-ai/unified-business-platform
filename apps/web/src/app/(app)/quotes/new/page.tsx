import type { Metadata } from "next";
import { NewQuotePage } from "@/features/documents/builder-pages";

export const metadata: Metadata = { title: "New quote" };

export default function Page() {
  return <NewQuotePage />;
}
