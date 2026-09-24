import type { Metadata } from "next";
import { OrdersReport } from "@/features/reports/orders-report";

export const metadata: Metadata = { title: "Orders report" };

export default function Page() {
  return <OrdersReport />;
}
