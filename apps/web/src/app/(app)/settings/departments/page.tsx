import type { Metadata } from "next";
import { DepartmentsPage } from "@/features/admin/departments-page";

export const metadata: Metadata = { title: "Departments" };

export default function Page() {
  return <DepartmentsPage />;
}
