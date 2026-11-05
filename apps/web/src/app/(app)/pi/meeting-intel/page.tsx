import type { Metadata } from "next";
import { MeetingIntelPage } from "@/features/pi/workspace/meeting-intel-page";

export const metadata: Metadata = { title: "Meeting intelligence" };

export default function Page() {
  return <MeetingIntelPage />;
}
