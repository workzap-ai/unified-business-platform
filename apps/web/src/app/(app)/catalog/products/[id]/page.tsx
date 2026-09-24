import type { Metadata } from "next";
import { ProductDetailPage } from "@/features/catalog/product-detail-page";

export const metadata: Metadata = { title: "Product" };

export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <ProductDetailPage id={id} />;
}
