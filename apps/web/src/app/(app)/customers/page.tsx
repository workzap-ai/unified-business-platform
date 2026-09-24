import type { Metadata } from "next";
import { CustomersListPage } from "@/features/customers/customers-list-page";

export const metadata: Metadata = { title: "Customers" };

export default function Page() {
  return <CustomersListPage />;
}
