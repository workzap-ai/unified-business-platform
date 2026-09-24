import type { Metadata } from "next";
import { BranchesPage } from "@/features/admin/branches-page";

export const metadata: Metadata = { title: "Branches" };

export default function Page() {
  return <BranchesPage />;
}
