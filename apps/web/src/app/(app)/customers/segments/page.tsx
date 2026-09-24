import type { Metadata } from "next";
import { CustomerSegmentsPage } from "@/features/customers/customer-segments-page";

export const metadata: Metadata = { title: "Customer segments" };

export default function Page() {
  return <CustomerSegmentsPage />;
}
