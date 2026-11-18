import type { Metadata } from "next";
import { TemplatesPage } from "@/features/pi/workspace/templates-page";

export const metadata: Metadata = { title: "WhatsApp templates" };

export default function Page() {
  return <TemplatesPage />;
}
