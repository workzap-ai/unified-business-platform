import type { Metadata } from "next";
import { OperatorReviewsPage } from "@/features/operator/control-pages";

export const metadata: Metadata = { title: "Business reviews" };

export default function Page() {
  return <OperatorReviewsPage />;
}
