import type { Metadata } from "next";
import { ReviewPage } from "@/features/pi/workspace/review-page";

export const metadata: Metadata = { title: "Conversation review" };

export default function Page() {
  return <ReviewPage />;
}
