import { Suspense } from "react";

import { AppShell } from "@/components/shell";
import { InstallPrompt } from "@/features/pwa";
import { LiveEventsProvider } from "@/lib/live";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <Suspense>
      <LiveEventsProvider>
        <AppShell>{children}</AppShell>
      </LiveEventsProvider>
      <InstallPrompt appName="pi" />
    </Suspense>
  );
}
