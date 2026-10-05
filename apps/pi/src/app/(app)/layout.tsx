import { Suspense } from "react";

import { AppShell } from "@/components/shell";
import { InstallPrompt } from "@/features/pwa";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <Suspense>
      <AppShell>{children}</AppShell>
      <InstallPrompt appName="pi" />
    </Suspense>
  );
}
