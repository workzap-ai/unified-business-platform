import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "@/features/workzap/home.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL("https://workzap.ai"),
  title: "Workzap",
  description: "Workzap products: nori and pi.",
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
