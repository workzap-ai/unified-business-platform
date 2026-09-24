"use client";

import Link from "next/link";
import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function ErrorPage({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  // Never render error details: they may contain internal information.
  return (
    <div className="flex min-h-[70dvh] items-center justify-center p-6">
      <div className="max-w-sm text-center" role="alert">
        <div className="mx-auto flex size-11 items-center justify-center rounded-xl bg-danger-soft text-danger">
          <AlertTriangle className="size-5" aria-hidden="true" />
        </div>
        <h1 className="mt-4 text-lg font-semibold">Something went wrong</h1>
        <p className="mt-1.5 text-sm text-muted-foreground">
          This page hit an unexpected problem. Your data is safe. Try again, or go back to the
          overview.
        </p>
        <div className="mt-5 flex justify-center gap-2">
          <Button variant="secondary" asChild>
            <Link href="/">Overview</Link>
          </Button>
          <Button onClick={reset}>Try again</Button>
        </div>
      </div>
    </div>
  );
}
