import type { Metadata } from "next";
import { WhatsAppConnectionPage } from "@/features/pi/config/whatsapp/whatsapp-connection-page";

export const metadata: Metadata = { title: "WhatsApp connection" };

export default function Page() {
  return <WhatsAppConnectionPage />;
}
