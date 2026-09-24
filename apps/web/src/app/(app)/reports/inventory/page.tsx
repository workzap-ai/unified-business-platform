import type { Metadata } from "next";
import { InventoryReport } from "@/features/reports/inventory-report";

export const metadata: Metadata = { title: "Inventory report" };

export default function Page() {
  return <InventoryReport />;
}
