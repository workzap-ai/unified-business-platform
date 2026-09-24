import type { Metadata } from "next";
import { EmployeesReport } from "@/features/reports/employees-report";

export const metadata: Metadata = { title: "Employees report" };

export default function Page() {
  return <EmployeesReport />;
}
