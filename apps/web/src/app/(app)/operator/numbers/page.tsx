import type { Metadata } from "next";
import { OperatorNumbersPage } from "@/features/operator/numbers-page";

export const metadata: Metadata = { title: "WhatsApp numbers" };

export default function Page() {
  return <OperatorNumbersPage />;
}
