import type { Metadata } from "next";
import { OperatorWorkspaceDetailPage } from "@/features/operator/workspace-admin";

export const metadata: Metadata = { title: "Workspace" };

export default async function Page({
  params,
}: {
  params: Promise<{ tenantId: string }>;
}) {
  const { tenantId } = await params;
  return <OperatorWorkspaceDetailPage id={tenantId} />;
}
