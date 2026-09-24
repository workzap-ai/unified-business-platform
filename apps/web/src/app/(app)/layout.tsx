import { Suspense } from "react";
import { AppShell } from "@/components/shell/app-shell";
import { PageSkeleton } from "@/components/app/page-skeleton";

export default function AuthenticatedLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AppShell>
      <Suspense fallback={<PageSkeleton />}>{children}</Suspense>
    </AppShell>
  );
}
