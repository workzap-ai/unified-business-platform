import type { Metadata } from "next";
import { OperatorHelpPage } from "@/features/operator/help-page";

export const metadata: Metadata = { title: "Pi help guides" };

export default function Page() {
  return <OperatorHelpPage />;
}
