import type { Metadata } from "next";
import { OrderDetailPage } from "@/features/documents/order-detail-page";

export const metadata: Metadata = { title: "Order" };

export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <OrderDetailPage id={id} />;
}
