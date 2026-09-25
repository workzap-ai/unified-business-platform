import type { Metadata } from "next";
import { WebhooksPage } from "@/features/integrations/webhooks-page";

export const metadata: Metadata = { title: "Outbound webhooks" };

export default function Page() {
  return <WebhooksPage />;
}
