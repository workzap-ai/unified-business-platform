import type { Metadata } from "next";
import { OnboardingListPage } from "@/features/hr/onboarding-list-page";

export const metadata: Metadata = { title: "Onboarding" };

export default function Page() {
  return <OnboardingListPage />;
}
