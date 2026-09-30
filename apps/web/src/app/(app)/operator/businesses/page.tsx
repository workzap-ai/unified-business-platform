import type { Metadata } from "next";
import { OperatorBusinessesPage } from "@/features/operator/operator-pages";

export const metadata: Metadata = { title: "Pi businesses" };

export default function Page() {
  return <OperatorBusinessesPage />;
}
