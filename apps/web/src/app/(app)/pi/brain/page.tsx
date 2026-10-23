import type { Metadata } from "next";
import { BrainLearningPage } from "@/features/pi/workspace/brain-learning-page";

export const metadata: Metadata = { title: "pi brain" };

export default function Page() {
  return <BrainLearningPage />;
}
