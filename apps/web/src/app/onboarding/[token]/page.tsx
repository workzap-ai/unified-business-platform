import type { Metadata } from "next";
import { OnboardingFormPage } from "@/features/hr/onboarding-form-page";

export const metadata: Metadata = {
  title: "New employee details",
  robots: { index: false, follow: false },
  referrer: "no-referrer",
};

export default async function Page({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  return <OnboardingFormPage token={token} />;
}
