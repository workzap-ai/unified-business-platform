import { DocumentPage } from "@/features/public/document";

export const metadata = { title: "Your document", robots: { index: false } };

export default async function Page({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  return <DocumentPage token={token} />;
}
