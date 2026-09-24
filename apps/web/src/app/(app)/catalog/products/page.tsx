import type { Metadata } from "next";
import { ProductsListPage } from "@/features/catalog/products-list-page";

export const metadata: Metadata = { title: "Products" };

export default function Page() {
  return <ProductsListPage />;
}
