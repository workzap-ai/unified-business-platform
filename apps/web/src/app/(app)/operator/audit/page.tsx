import type { Metadata } from "next";
import { OperatorAuditPage } from "@/features/operator/system-pages";

export const metadata: Metadata = { title: "Audit log" };

export default function Page() {
  return <OperatorAuditPage />;
}
