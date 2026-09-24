import type { Metadata } from "next";
import { AgentDetailPage } from "@/features/pi/config/agents/agent-detail-page";

export const metadata: Metadata = { title: "PI agent" };

export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <AgentDetailPage id={id} />;
}
