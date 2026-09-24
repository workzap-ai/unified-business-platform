import type { Metadata } from "next";
import { WhatsAppStatusPage } from "@/features/pi/config/whatsapp/whatsapp-status-page";

export const metadata: Metadata = { title: "WhatsApp status" };

export default function Page() {
  return <WhatsAppStatusPage />;
}
