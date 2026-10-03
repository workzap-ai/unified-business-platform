import { AgentDetailPage } from "@/features/agents";

export const metadata = { title: "Agent" };

export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <AgentDetailPage id={id} />;
}
