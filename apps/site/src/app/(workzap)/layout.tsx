import type { Metadata, Viewport } from "next";
import { JetBrains_Mono, Plus_Jakarta_Sans } from "next/font/google";
import "@/features/retail/retail.css";

const jakarta = Plus_Jakarta_Sans({
  subsets: ["latin"],
  variable: "--font-jakarta",
  display: "swap",
});
const jbmono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jbmono",
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL("https://workzap.ai"),
  title: "WorkZap — The AI Operating System for Retail",
  description:
    "WorkZap plugs into your POS and sales data and works like an AI management team — what happened, why, what matters, and what to do next. A decision engine for your whole retail business.",
};

export const viewport: Viewport = {
  themeColor: "#00a86b",
};

export default function WorkzapLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      data-theme="light"
      className={`${jakarta.variable} ${jbmono.variable}`}
    >
      <body>{children}</body>
    </html>
  );
}
