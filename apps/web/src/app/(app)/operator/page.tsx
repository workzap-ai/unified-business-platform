import type { Metadata } from "next";
import { OperatorOverviewPage } from "@/features/operator/operator-pages";

export const metadata: Metadata = { title: "Operator console" };

export default function Page() {
  return <OperatorOverviewPage />;
}
