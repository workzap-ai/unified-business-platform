import type { Viewport } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { Wordmark } from "@/components/brand";

export const metadata = {
  title: { default: "pi Customer", template: "%s · pi Customer" },
  robots: { index: false },
};

// Edge to edge on phones with a notch; the bottom action bar pads for the home bar.
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function CustomerLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-dvh flex-col bg-background">
      <header className="sticky top-0 z-30 border-b border-border bg-surface/90 pt-[env(safe-area-inset-top)] backdrop-blur">
        <div className="mx-auto flex h-14 w-full max-w-6xl items-center justify-between px-4 sm:h-16">
          <Link
            href="/customer"
            aria-label="pi Customer home"
            className="flex min-h-11 items-center gap-2"
          >
            <Wordmark />
            <span className="rounded-full bg-accent-soft px-2 py-0.5 text-xs font-medium text-accent-soft-foreground">
              Customer
            </span>
          </Link>
        </div>
      </header>
      <main
        id="main"
        className="flex-1 px-[max(1rem,env(safe-area-inset-left))] py-5 sm:px-6 sm:py-10"
      >
        <Suspense>{children}</Suspense>
      </main>
      <footer className="hidden px-4 pb-8 text-center text-xs text-muted-foreground sm:block">
        Your conversations are private. Businesses can turn pi Customer off for
        their chats.
      </footer>
    </div>
  );
}
