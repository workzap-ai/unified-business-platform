"use client";

import { useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { toast } from "sonner";
import { RefreshCw } from "lucide-react";
import { apiGet } from "@/services/api-client";
import { Button } from "@/components/ui/button";

const healthSchema = z.object({ status: z.literal("ok") });

export function ConnectionStatus() {
  const status = useQuery({
    queryKey: ["system", "readiness"],
    queryFn: ({ signal }) => apiGet("/health/ready", healthSchema, signal),
  });
  async function refresh() {
    const result = await status.refetch();
    if (result.isSuccess) toast.success("Connection restored");
    else toast.error("Unable to connect. Please try again shortly.");
  }
  return (
    <section
      aria-label="Connection status"
      className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-border bg-card p-6"
    >
      <div role="status" aria-live="polite">
        <p className="font-medium">
          {status.isPending
            ? "Connecting to your workspace…"
            : status.isError
              ? "Connection unavailable"
              : "Connected"}
        </p>
        <p className="mt-1 text-sm text-muted-foreground">
          {status.isError
            ? "We couldn’t reach the service. Please try again shortly."
            : status.isPending
              ? "Checking service availability."
              : "The service is ready."}
        </p>
      </div>
      <Button variant="outline" onClick={refresh} disabled={status.isFetching}>
        <RefreshCw size={16} aria-hidden="true" />
        {status.isFetching ? "Checking…" : "Check connection"}
      </Button>
    </section>
  );
}
