import type { Metadata } from "next";
import { OnboardingReviewPage } from "@/features/hr/onboarding-review-page";

export const metadata: Metadata = { title: "Review onboarding" };

export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <OnboardingReviewPage id={id} />;
}
