import type { Metadata } from "next";
import { MovementsPage } from "@/features/inventory/movements-page";

export const metadata: Metadata = { title: "Stock movements" };

export default function Page() {
  return <MovementsPage />;
}
