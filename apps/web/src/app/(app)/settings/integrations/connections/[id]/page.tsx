import type { Metadata } from "next";
import { ConnectionDetailPage } from "@/features/integrations/connection-detail-page";

export const metadata: Metadata = { title: "Connection" };

export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <ConnectionDetailPage connectionId={id} />;
}
