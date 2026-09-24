import type { Metadata } from "next";
import { RoleEditor } from "@/features/admin/role-editor";

export const metadata: Metadata = { title: "Role" };

export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <RoleEditor roleId={id} />;
}
