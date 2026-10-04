import type { Metadata, Viewport } from "next";
import Image from "next/image";
import Link from "next/link";
import { Inter } from "next/font/google";
import { PI, assertReadyToPublish } from "@/features/pi/config";
import { PiLauncher } from "@/components/pi-launcher";
import { WhatsAppButton } from "@/features/pi/client";
import { AiChip } from "@/features/pi/ui";
import { JsonLd, ORGANIZATION_LD } from "@/features/pi/meta";
import "@/features/pi/pi-tokens.css";
import "@/features/pi/pi.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = { metadataBase: new URL(PI.siteUrl) };

export const viewport: Viewport = { themeColor: "#5A47F5" };

const links = [
  { href: `${PI.base}/how-it-works`, label: "How pi works", gate: null },
  { href: `${PI.base}/dashboard`, label: "Your problems", gate: "dashboard" },
  {
    href: `${PI.base}/solutions`,
    label: "From problem to solution",
    gate: "solutions",
  },
  { href: `${PI.base}/who-its-for`, label: "Who it’s for", gate: null },
  { href: `${PI.base}/trust`, label: "Trust", gate: null },
  { href: `${PI.base}/faq`, label: "FAQ", gate: null },
] as const;

export default function PiLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  assertReadyToPublish();
  const visible = links.filter((l) => l.gate === null || PI.live[l.gate]);
  return (
    <html lang="en" className={inter.variable}>
      <body>
        <a className="pi-skip" href="#main">
          Skip to content
        </a>
        <div className="pi-bar">
          <div className="pi-wrap">
            <Link href="/">Workzap</Link>
            <Link href="/nori">nori by Workzap</Link>
          </div>
        </div>
        <header className="pi-header">
          <div className="pi-wrap pi-nav">
            <Link href={PI.base} className="pi-brand">
              <Image
                src="/pi-brand/pi-lockup-horizontal-color.svg"
                alt="pi by Workzap"
                width={76}
                height={40}
                priority
                unoptimized
              />
              <AiChip />
            </Link>
            <nav className="pi-links" aria-label="pi">
              {visible.map((l) => (
                <Link key={l.href} href={l.href}>
                  {l.label}
                </Link>
              ))}
            </nav>
            <WhatsAppButton page="layout" pos="nav" />
            <details className="pi-menu">
              <summary>Menu</summary>
              <nav aria-label="pi, menu">
                {visible.map((l) => (
                  <Link key={l.href} href={l.href}>
                    {l.label}
                  </Link>
                ))}
              </nav>
            </details>
          </div>
        </header>
        <main id="main">{children}</main>
        <footer className="pi-footer">
          <div className="pi-wrap">
            <p style={{ margin: 0 }}>
              pi is Workzap’s WhatsApp agent. pi is an AI. WhatsApp is a
              trademark of Meta; pi is not made, run or endorsed by WhatsApp or
              Meta.
            </p>
            <div className="pi-footer-links">
              <Link href={`${PI.base}/privacy`}>Privacy</Link>
              <Link href={`${PI.base}/terms`}>Terms</Link>
              <Link href={`${PI.base}/trust`}>Trust</Link>
              <Link href={`${PI.base}/talk-to-pi`}>Contact pi</Link>
            </div>
          </div>
        </footer>
        <JsonLd data={ORGANIZATION_LD} />
        <PiLauncher />
      </body>
    </html>
  );
}
