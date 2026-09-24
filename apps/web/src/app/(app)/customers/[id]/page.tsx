import type { Metadata } from "next";
import { CustomerDetailPage } from "@/features/customers/customer-detail-page";

export const metadata: Metadata = { title: "Customer" };

export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <CustomerDetailPage id={id} />;
}
