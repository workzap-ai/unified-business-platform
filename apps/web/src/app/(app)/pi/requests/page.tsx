import type { Metadata } from "next";
import { RequestsPage } from "@/features/pi/workspace/requests-page";

export const metadata: Metadata = { title: "PI requests" };

export default function Page() {
  return <RequestsPage />;
}
