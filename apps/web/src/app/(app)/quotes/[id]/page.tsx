import type { Metadata } from "next";
import { QuoteDetailPage } from "@/features/documents/quote-detail-page";

export const metadata: Metadata = { title: "Quote" };

export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <QuoteDetailPage id={id} />;
}
