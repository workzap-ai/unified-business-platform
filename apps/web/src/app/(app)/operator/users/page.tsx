import type { Metadata } from "next";
import { OperatorUsersPage } from "@/features/operator/system-pages";

export const metadata: Metadata = { title: "Users" };

export default function Page() {
  return <OperatorUsersPage />;
}
