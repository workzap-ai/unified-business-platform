import type { Metadata } from "next";
import { AgentNewPage } from "@/features/pi/config/agents/agent-new-page";

export const metadata: Metadata = { title: "New agent configuration" };

export default function Page() {
  return <AgentNewPage />;
}
