import { Suspense } from "react";

import { ReviewQueuePage } from "@/features/brain";

export const metadata = { title: "Review queue" };

export default function Page() {
  return (
    <Suspense>
      <ReviewQueuePage />
    </Suspense>
  );
}
