import type { Metadata } from "next";
import { IntegrationDetailPage } from "@/features/integrations/integration-detail-page";

export const metadata: Metadata = { title: "Integration" };

export default async function Page({
  params,
}: {
  params: Promise<{ key: string }>;
}) {
  const { key } = await params;
  return <IntegrationDetailPage integrationKey={key} />;
}
