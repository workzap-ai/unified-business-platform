import type { Metadata } from "next";
import { EnvironmentsPage } from "@/features/admin/environments-page";

export const metadata: Metadata = { title: "Environments" };

export default function Page() {
  return <EnvironmentsPage />;
}
