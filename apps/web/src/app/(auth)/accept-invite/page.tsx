import { Suspense } from "react";
import type { Metadata } from "next";
import { AcceptInviteForm } from "@/features/auth/accept-invite-form";

export const metadata: Metadata = { title: "Join workspace" };

export default function AcceptInvitePage() {
  return (
    <Suspense>
      <AcceptInviteForm />
    </Suspense>
  );
}
