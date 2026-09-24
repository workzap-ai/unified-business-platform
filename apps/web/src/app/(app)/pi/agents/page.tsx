import type { Metadata } from "next";
import { AgentsPage } from "@/features/pi/config/agents/agents-page";

export const metadata: Metadata = { title: "PI agents" };

export default function Page() {
  return <AgentsPage />;
}
