import type { Metadata } from "next";
import { EnrollForm } from "@/features/auth/enroll-form";

export const metadata: Metadata = { title: "Add your face or phone lock" };

export default async function EnrollPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  return <EnrollForm token={token} />;
}
