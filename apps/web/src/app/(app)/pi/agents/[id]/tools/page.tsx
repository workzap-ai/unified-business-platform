import type { Metadata } from "next";
import { AgentToolsPage } from "@/features/pi/config/agents/agent-tools-page";

export const metadata: Metadata = { title: "Agent tools" };

export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <AgentToolsPage id={id} />;
}
