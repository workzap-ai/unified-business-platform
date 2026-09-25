import type { Metadata } from "next";
import { EventsPage } from "@/features/integrations/events-page";

export const metadata: Metadata = { title: "Inbound events" };

export default function Page() {
  return <EventsPage />;
}
