import type { Metadata } from "next";
import { ProductDetailPage } from "@/features/admin/product-detail-page";

export const metadata: Metadata = { title: "Platform product" };

export default async function Page({
  params,
}: {
  params: Promise<{ key: string }>;
}) {
  const { key } = await params;
  return <ProductDetailPage productKey={key} />;
}
