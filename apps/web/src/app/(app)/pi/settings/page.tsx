import type { Metadata } from "next";
import { PiSettingsOverviewPage } from "@/features/pi/config/settings/settings-pages";

export const metadata: Metadata = { title: "PI settings" };

export default function Page() {
  return <PiSettingsOverviewPage />;
}
