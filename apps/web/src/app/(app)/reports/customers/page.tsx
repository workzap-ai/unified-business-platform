import type { Metadata } from "next";
import { CustomersReport } from "@/features/reports/customers-report";

export const metadata: Metadata = { title: "Customers report" };

export default function Page() {
  return <CustomersReport />;
}
