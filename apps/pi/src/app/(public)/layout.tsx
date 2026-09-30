import Link from "next/link";
import { Suspense } from "react";

import { Wordmark } from "@/components/brand";
import s from "@/features/public/public.module.css";

export default function PublicLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className={s.publicShell}>
      <header className={s.publicHeader}>
        <Link href="/" aria-label="Pi home">
          <Wordmark />
        </Link>
        <nav aria-label="Account" className={s.publicNav}>
          <Link href="/#how-it-works">How it works</Link>
          <Link
            href="/#pricing"
            className="rounded-md px-3 py-2 text-foreground-secondary hover:bg-surface-muted"
          >
            Pricing
          </Link>
          <Link
            href="/sign-in"
            className="rounded-md px-3 py-2 text-foreground-secondary hover:bg-surface-muted"
          >
            Sign in
          </Link>
        </nav>
      </header>
      <main id="main" className={s.publicMain}>
        <Suspense>{children}</Suspense>
      </main>
      <footer className={s.publicFooter}>
        <p>
          Pi works with WhatsApp through official business APIs. WhatsApp is a
          trademark of its owner.
        </p>
        <nav aria-label="Footer" className={s.footerLinks}>
          <Link href="/#how-it-works">Meet Pi</Link>
          <Link href="/#pricing">Plans</Link>
          <Link href="/sign-in">Your workspace</Link>
        </nav>
      </footer>
    </div>
  );
}
