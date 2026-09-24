import type { Metadata } from "next";
import { EmployeeNewPage } from "@/features/hr/employee-new-page";

export const metadata: Metadata = { title: "Add employee" };

export default function Page() {
  return <EmployeeNewPage />;
}
