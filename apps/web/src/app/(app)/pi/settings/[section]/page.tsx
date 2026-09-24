import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { PiSettingsSectionPage } from "@/features/pi/config/settings/settings-pages";
import {
  SETTINGS_SECTIONS,
  isSettingsSection,
} from "@/features/pi/config/sections";

type Props = { params: Promise<{ section: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { section } = await params;
  const label = SETTINGS_SECTIONS.find((s) => s.slug === section)?.label;
  return { title: label ? `PI settings · ${label}` : "PI settings" };
}

export default async function Page({ params }: Props) {
  const { section } = await params;
  if (!isSettingsSection(section)) notFound();
  return <PiSettingsSectionPage section={section} />;
}
