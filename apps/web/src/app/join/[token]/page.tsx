import type { Metadata } from "next";
import { MeetingJoinPage } from "@/features/pi/meeting-join-page";

export const metadata: Metadata = {
  title: "Join the meeting",
  robots: { index: false, follow: false },
  referrer: "no-referrer",
};

export default async function Page({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  return <MeetingJoinPage token={token} />;
}
