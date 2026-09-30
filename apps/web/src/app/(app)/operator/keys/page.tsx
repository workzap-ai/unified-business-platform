import type { Metadata } from "next";
import { OperatorKeysPage } from "@/features/operator/control-pages";

export const metadata: Metadata = { title: "Platform keys" };

export default function Page() {
  return <OperatorKeysPage />;
}
