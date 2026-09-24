import type { Metadata } from "next";
import { CategoriesPage } from "@/features/catalog/categories-page";

export const metadata: Metadata = { title: "Categories" };

export default function Page() {
  return <CategoriesPage />;
}
