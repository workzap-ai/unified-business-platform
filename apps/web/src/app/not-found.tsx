import Link from "next/link";
import { Compass } from "lucide-react";

export default function NotFound() {
  return (
    <div className="flex min-h-[70dvh] items-center justify-center p-6">
      <div className="max-w-sm text-center">
        <div className="mx-auto flex size-11 items-center justify-center rounded-xl bg-surface-muted text-muted-foreground">
          <Compass className="size-5" aria-hidden="true" />
        </div>
        <h1 className="mt-4 text-lg font-semibold">Page not found</h1>
        <p className="mt-1.5 text-sm text-muted-foreground">
          The page may have moved, or the link is incomplete. Use search (Ctrl K) to find what
          you need.
        </p>
        <Link href="/" className="mt-5 inline-block text-sm font-medium text-primary hover:underline">
          Return home
        </Link>
      </div>
    </div>
  );
}
