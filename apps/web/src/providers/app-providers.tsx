"use client";

import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "sonner";
import { ApiError } from "@/services/api-client";
import { TooltipProvider } from "@/components/ui/overlays";
import { ThemeProvider } from "@/components/shell/theme";
import { SessionProvider } from "@/features/auth/session-provider";

export function AppProviders({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            refetchOnWindowFocus: false,
            // Never retry authorization or not-found responses.
            retry: (count, error) =>
              !(
                error instanceof ApiError &&
                [401, 403, 404, 409, 422].includes(error.status)
              ) && count < 1,
          },
          mutations: { retry: false },
        },
      }),
  );
  return (
    <QueryClientProvider client={client}>
      <ThemeProvider>
        <TooltipProvider delayDuration={250}>
          <SessionProvider>{children}</SessionProvider>
        </TooltipProvider>
      </ThemeProvider>
      <Toaster richColors position="bottom-right" closeButton />
    </QueryClientProvider>
  );
}
