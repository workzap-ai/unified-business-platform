import type { Metadata } from "next";
import { MeetingRoomPage } from "@/features/pi/workspace/meeting-room-page";

export const metadata: Metadata = { title: "Video room" };

export default function Page() {
  return <MeetingRoomPage />;
}
