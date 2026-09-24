import type { Metadata } from "next";
import { EditQuotePage } from "@/features/documents/builder-pages";

export const metadata: Metadata = { title: "Edit quote" };

export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <EditQuotePage id={id} />;
}
