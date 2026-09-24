import type { Metadata } from "next";
import { InvoicesPage } from "@/features/billing/invoices-page";

export const metadata: Metadata = { title: "Invoices" };

export default function Page() {
  return <InvoicesPage />;
}
