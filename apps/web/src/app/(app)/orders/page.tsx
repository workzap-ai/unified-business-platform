import type { Metadata } from "next";
import { OrdersListPage } from "@/features/documents/orders-list-page";

export const metadata: Metadata = { title: "Orders" };

export default function Page() {
  return <OrdersListPage />;
}
