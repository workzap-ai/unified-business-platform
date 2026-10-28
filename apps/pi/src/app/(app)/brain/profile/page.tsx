import { Suspense } from "react";

import { BusinessProfilePage } from "@/features/business-profile";

export const metadata = { title: "Business profile" };

export default function Page() {
  return (
    <Suspense>
      <BusinessProfilePage />
    </Suspense>
  );
}
