import type { Metadata } from "next";
import { WhatsAppEventsPage } from "@/features/pi/config/whatsapp/whatsapp-events-page";

export const metadata: Metadata = { title: "WhatsApp events" };

export default function Page() {
  return <WhatsAppEventsPage />;
}
