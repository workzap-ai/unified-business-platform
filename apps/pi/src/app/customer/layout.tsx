import Link from "next/link";
import { Suspense } from "react";

import { Wordmark } from "@/components/brand";

export const metadata = {
  title: { default: "PI Customer", template: "%s · PI Customer" },
  robots: { index: false },
};

export default function CustomerLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-dvh flex-col bg-background">
      <header className="border-b border-border bg-surface/80 backdrop-blur">
        <div className="mx-auto flex h-14 w-full max-w-2xl items-center justify-between px-4">
          <Link
            href="/customer"
            aria-label="PI Customer home"
            className="flex items-center gap-2"
          >
            <Wordmark />
            <span className="rounded-full bg-accent-soft px-2 py-0.5 text-xs font-medium text-accent-soft-foreground">
              Customer
            </span>
          </Link>
        </div>
      </header>
      <main id="main" className="flex-1 px-4 py-8 sm:py-10">
        <Suspense>{children}</Suspense>
      </main>
      <footer className="px-4 pb-8 text-center text-xs text-muted-foreground">
        Your conversations are private. Businesses can turn PI Customer off for
        their chats.
      </footer>
    </div>
  );
}
