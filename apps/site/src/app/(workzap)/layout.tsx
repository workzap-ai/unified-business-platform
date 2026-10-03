import type { Metadata, Viewport } from "next";
import { JetBrains_Mono, Plus_Jakarta_Sans } from "next/font/google";
import "@/features/workzap/workzap.css";

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
    <html
      lang="en"
      data-theme="light"
      className={`${jakarta.variable} ${jbmono.variable}`}
    >
      <body>{children}</body>
    </html>
  );
}
