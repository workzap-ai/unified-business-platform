import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import { pageMetadata } from "@/lib/seo";
import "@/features/workzap/home.css";

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
  themeColor: "#00a86b",
};

export default function WorkzapLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={inter.variable}>
      <body>{children}</body>
    </html>
  );
}
