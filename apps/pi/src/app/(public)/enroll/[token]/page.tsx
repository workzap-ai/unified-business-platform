import { EnrollForm } from "@/features/enroll";

export const metadata = { title: "Add your face or phone lock" };

export default async function Page({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  return <EnrollForm token={token} />;
}
