import type { Metadata } from "next";
import { EmployeeDetailPage } from "@/features/hr/employee-detail-page";

export const metadata: Metadata = { title: "Employee" };

export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <EmployeeDetailPage id={id} />;
}
