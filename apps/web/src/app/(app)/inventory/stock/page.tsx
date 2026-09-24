import type { Metadata } from "next";
import { StockPage } from "@/features/inventory/stock-page";

export const metadata: Metadata = { title: "Stock levels" };

export default function Page() {
  return <StockPage />;
}
