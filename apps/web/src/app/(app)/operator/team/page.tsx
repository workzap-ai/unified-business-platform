import type { Metadata } from "next";
import { OperatorTeamPage } from "@/features/operator/operator-pages";

export const metadata: Metadata = { title: "Operator team" };

export default function Page() {
  return <OperatorTeamPage />;
}
