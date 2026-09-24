import type { Metadata } from "next";
import { HandoffsPage } from "@/features/pi/workspace/handoffs-page";

export const metadata: Metadata = { title: "PI handoffs" };

export default function Page() {
  return <HandoffsPage />;
}
