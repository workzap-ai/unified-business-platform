import type { Metadata } from "next";
import { IntegrationsDirectoryPage } from "@/features/integrations/directory-page";

export const metadata: Metadata = { title: "Integrations" };

export default function Page() {
  return <IntegrationsDirectoryPage />;
}
