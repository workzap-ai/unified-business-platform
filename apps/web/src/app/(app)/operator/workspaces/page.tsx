import type { Metadata } from "next";
import { OperatorWorkspacesPage } from "@/features/operator/operator-pages";

export const metadata: Metadata = { title: "Workspaces" };

export default function Page() {
  return <OperatorWorkspacesPage />;
}
