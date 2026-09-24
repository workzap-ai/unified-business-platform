import type { Metadata } from "next";
import { ProductCreatePage } from "@/features/catalog/product-create-page";

export const metadata: Metadata = { title: "Add product" };

export default function Page() {
  return <ProductCreatePage />;
}
