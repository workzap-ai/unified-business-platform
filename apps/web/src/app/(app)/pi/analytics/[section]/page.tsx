import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { AnalyticsPage } from "@/features/pi/config/analytics/analytics-page";
import {
  ANALYTICS_SECTIONS,
  isAnalyticsSection,
} from "@/features/pi/config/sections";

type Props = { params: Promise<{ section: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { section } = await params;
  const label = ANALYTICS_SECTIONS.find((s) => s.slug === section)?.label;
  return { title: label ? `PI analytics · ${label}` : "PI analytics" };
}

export default async function Page({ params }: Props) {
  const { section } = await params;
  if (!isAnalyticsSection(section)) notFound();
  return <AnalyticsPage section={section} />;
}
