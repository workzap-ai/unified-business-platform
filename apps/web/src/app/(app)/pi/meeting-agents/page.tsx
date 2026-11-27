import type { Metadata } from "next";
import { MeetingAgentsPage } from "@/features/pi/agents/agents-page";

export const metadata: Metadata = { title: "Meeting agents" };

export default function Page() {
  return <MeetingAgentsPage />;
}
