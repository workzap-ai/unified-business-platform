import type { Metadata } from "next";
import { OperatorSystemPage } from "@/features/operator/system-pages";

export const metadata: Metadata = { title: "System" };

export default function Page() {
  return <OperatorSystemPage />;
}
