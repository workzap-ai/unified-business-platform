import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { HandoffsPage } from "@/features/pi/workspace/handoffs-page";
import { HANDOFF_SLUGS } from "@/features/pi/workspace/lib";

export const metadata: Metadata = { title: "PI handoffs" };

export default async function Page({
  params,
}: {
  params: Promise<{ status: string }>;
}) {
  const { status } = await params;
  if (!Object.hasOwn(HANDOFF_SLUGS, status)) notFound();
  return <HandoffsPage status={HANDOFF_SLUGS[status]} />;
}
