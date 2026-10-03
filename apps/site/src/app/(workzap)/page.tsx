import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Workzap",
  description: "Workzap products.",
  alternates: { canonical: "/" },
};

// Draft parent page: only facts already published on the previous site and in the
// pi content document. The owner supplies the final company wording.
const products = [
  {
    key: "nori",
    name: "nori by Workzap",
    logo: "/nori-brand/nori-lockup-horizontal-color.svg",
    width: 300.77,
    height: 103.1,
    line: "The daily read for the shop.",
    detail:
      "nori reads your shop’s sales and stock and picks out the one thing worth looking at today.",
    href: "/nori",
    cta: "See nori",
  },
  {
    key: "pi",
    name: "pi by Workzap",
    logo: "/pi-brand/pi-lockup-horizontal-color.svg",
    width: 285.8,
    height: 149.8,
    line: "Workzap's WhatsApp agent.",
    detail:
      "Chat about the problems in your business. pi notes each one and sorts them. pi is an AI.",
    href: null,
    cta: "Coming soon",
  },
] as const;

export default function Home() {
  return (
    <div className="hm-page">
      <header className="hm-header">
        <nav className="hm-wrap hm-nav" aria-label="Workzap">
          <Link href="/" aria-label="Workzap home" className="hm-brand">
            <div className="hm-logo">W</div>
            <div className="hm-brand-name">Workzap</div>
          </Link>
        </nav>
      </header>
      <main className="hm-main">
        <div className="hm-wrap">
          <div className="hm-statement">
            <h1>Workzap products</h1>
            <p className="hm-lead">Two products from Workzap: nori and pi.</p>
          </div>
          <ul className="hm-cards">
            {products.map((p) => (
              <li key={p.key} className={`hm-card hm-${p.key}`}>
                <h2>
                  <span className="hm-logo-wrap">
                    <Image
                      src={p.logo}
                      alt={p.name}
                      width={p.width}
                      height={p.height}
                      priority
                      unoptimized
                    />
                    {p.key === "pi" ? (
                      <span className="hm-pi-chip" title="pi is an AI">
                        AI
                      </span>
                    ) : null}
                  </span>
                </h2>
                <p className="hm-line">{p.line}</p>
                <p className="hm-detail">{p.detail}</p>
                {p.href ? (
                  <Link href={p.href} className="hm-action">
                    {p.cta}
                  </Link>
                ) : (
                  <span className="hm-action hm-status">{p.cta}</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      </main>
    </div>
  );
}
