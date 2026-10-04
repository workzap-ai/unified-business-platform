import type { Metadata, Viewport } from "next";
import { Inter, Jost } from "next/font/google";
import { PiLauncher } from "@/components/pi-launcher";
import { JsonLd, ORGANIZATION, WEBSITE } from "@/lib/seo";
import "@/features/nori/nori-tokens.css";
import "@/features/nori/nori.css";

const jost = Jost({
  subsets: ["latin"],
  variable: "--font-jost",
  display: "swap",
});
const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const isProduction = process.env.VERCEL_ENV === "production";

export const metadata: Metadata = {
  metadataBase: new URL("https://workzap.ai"),
  title: "nori by Workzap",
  description:
    "nori reads your shop’s sales and stock and picks out the one thing worth looking at today.",
  // Previews and staging are never indexed; only a production deploy is.
  robots: isProduction ? undefined : { index: false, follow: false },
};

export const viewport: Viewport = { themeColor: "#F7F1E6" };

export default function NoriLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${jost.variable} ${inter.variable}`}>
      <body>
        <JsonLd
          data={{
            "@context": "https://schema.org",
            "@graph": [ORGANIZATION, WEBSITE],
          }}
        />
        {children}
        <PiLauncher />
      </body>
    </html>
  );
}
