import type { Metadata } from "next";
import { OperatorPlansPage } from "@/features/operator/operator-pages";

export const metadata: Metadata = { title: "Plans" };

export default function Page() {
  return <OperatorPlansPage />;
}
