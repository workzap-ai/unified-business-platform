import type { Metadata } from "next";
import { AgentVersionsPage } from "@/features/pi/config/agents/agent-versions-page";

export const metadata: Metadata = { title: "Agent versions" };

export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <AgentVersionsPage id={id} />;
}
