import type { Metadata } from "next";
import { InboxPage } from "@/features/pi/workspace/inbox-page";

export const metadata: Metadata = { title: "PI inbox" };

export default function Page() {
  return <InboxPage />;
}
