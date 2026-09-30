import type { Metadata } from "next";
import { SetupCenterPage } from "@/features/pi/setup/setup-center-page";

export const metadata: Metadata = { title: "Setup" };

export default function Page() {
  return <SetupCenterPage />;
}
