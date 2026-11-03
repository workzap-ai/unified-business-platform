import { Suspense } from "react";

import { BrainHealthPage } from "@/features/brain";

export const metadata = { title: "Brain health" };

export default function Page() {
  return (
    <Suspense>
      <BrainHealthPage />
    </Suspense>
  );
}
