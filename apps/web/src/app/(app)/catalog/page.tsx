import type { Metadata } from "next";
import { CatalogOverviewPage } from "@/features/catalog/catalog-overview-page";

export const metadata: Metadata = { title: "Catalog" };

export default function Page() {
  return <CatalogOverviewPage />;
}
