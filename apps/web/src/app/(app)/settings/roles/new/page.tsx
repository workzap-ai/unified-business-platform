import type { Metadata } from "next";
import { RoleEditor } from "@/features/admin/role-editor";

export const metadata: Metadata = { title: "New role" };

export default function Page() {
  return <RoleEditor />;
}
