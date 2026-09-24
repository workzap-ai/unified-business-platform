import type { Metadata } from "next";
import { InvoiceNewPage } from "@/features/billing/invoice-new-page";

export const metadata: Metadata = { title: "New invoice" };

export default function Page() {
  return <InvoiceNewPage />;
}
