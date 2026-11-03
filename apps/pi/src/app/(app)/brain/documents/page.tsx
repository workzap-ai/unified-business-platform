import { Suspense } from "react";

import { DocumentsQueuePage } from "@/features/brain";

export const metadata = { title: "Brain documents" };

export default function Page() {
  return (
    <Suspense>
      <DocumentsQueuePage />
    </Suspense>
  );
}
