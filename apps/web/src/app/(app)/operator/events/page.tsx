import type { Metadata } from "next";
import { OperatorEventsPage } from "@/features/operator/operator-pages";

export const metadata: Metadata = { title: "Failed work" };

export default function Page() {
  return <OperatorEventsPage />;
}
