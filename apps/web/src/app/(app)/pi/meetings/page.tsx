import type { Metadata } from "next";
import { MeetingsPage } from "@/features/pi/workspace/meetings-page";

export const metadata: Metadata = { title: "Meetings" };

export default function Page() {
  return <MeetingsPage />;
}
