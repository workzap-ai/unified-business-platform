import type { Metadata } from "next";
import { ProductsPage } from "@/features/admin/products-page";

export const metadata: Metadata = { title: "Platform products" };

export default function Page() {
  return <ProductsPage />;
}
