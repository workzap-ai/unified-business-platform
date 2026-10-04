import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import { JsonLd, ORGANIZATION, WEBSITE, pageMetadata } from "@/lib/seo";
import { PiLauncher } from "@/components/pi-launcher";
import { SiteNav } from "@/features/workzap/client";
import { Logo, SiteFooter } from "@/features/workzap/ui";
import "@/features/workzap/site.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  ...pageMetadata({
    path: "/",
    title: "Workzap: nori and pi",
    description:
      "Workzap makes nori, a daily read for the shop, and pi, a WhatsApp agent for talking through the problems in your business.",
    siteName: "Workzap",
    brand: "workzap",
  }),
};

export const viewport: Viewport = {
  themeColor: "#ffffff",
};

export default function WorkzapLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="wz">
        <a className="wz-skip" href="#main">
          Skip to content
        </a>
        <SiteNav logo={<Logo />} />
        <main id="main" tabIndex={-1}>
          {children}
        </main>
        <SiteFooter />
        <JsonLd
          data={{
            "@context": "https://schema.org",
            "@graph": [ORGANIZATION, WEBSITE],
          }}
        />
        <PiLauncher />
      </body>
    </html>
  );
}
