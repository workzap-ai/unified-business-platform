import type { Metadata } from "next";
import { BlocklistPage } from "@/features/pi/workspace/blocklist-page";

export const metadata: Metadata = { title: "PI blocklist" };

export default function Page() {
  return <BlocklistPage />;
}
