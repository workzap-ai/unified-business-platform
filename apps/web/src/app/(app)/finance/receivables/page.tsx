import type { Metadata } from "next";
import { ReceivablesPage } from "@/features/finance/receivables-page";

export const metadata: Metadata = { title: "Receivables" };

export default function Page() {
  return <ReceivablesPage />;
}
