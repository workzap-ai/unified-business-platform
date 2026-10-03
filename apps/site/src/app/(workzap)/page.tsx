import type { Metadata } from "next";
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
    name: "WorkZap for retail",
    line: "The AI Operating System for Retail.",
    detail:
      "Plugs into your POS and sales data and works like an AI management team — what happened, why, what matters, and what to do next.",
    href: "/retail",
    cta: "See WorkZap for retail",
  },
  {
    name: "pi",
    line: "Workzap's WhatsApp agent.",
    detail:
      "Chat about the problems in your business. pi notes each one and sorts them. pi is an AI.",
    href: null,
    cta: "Coming soon",
  },
] as const;

export default function Home() {
  return (
    <div
      style={{
        background: "var(--bg-app)",
        color: "var(--text-primary)",
        minHeight: "100vh",
      }}
    >
      <header
        style={{
          borderBottom: "1px solid var(--border)",
          background: "var(--bg-app)",
        }}
      >
        <nav
          style={{
            maxWidth: 1080,
            margin: "0 auto",
            padding: "0 24px",
            display: "flex",
            alignItems: "center",
            height: 62,
          }}
        >
          <Link
            href="/"
            aria-label="Workzap home"
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              textDecoration: "none",
              color: "inherit",
            }}
          >
            <div className="wz-logo">W</div>
            <div style={{ fontWeight: 800, fontSize: 16 }}>Workzap</div>
          </Link>
        </nav>
      </header>
      <main style={{ maxWidth: 1080, margin: "0 auto", padding: "72px 24px" }}>
        <h1
          style={{
            fontSize: "clamp(32px, 5vw, 48px)",
            fontWeight: 800,
            letterSpacing: "-0.03em",
            margin: 0,
          }}
        >
          Workzap products
        </h1>
        <ul
          style={{
            listStyle: "none",
            padding: 0,
            margin: "40px 0 0",
            display: "grid",
            gap: 20,
            gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))",
          }}
        >
          {products.map((p) => (
            <li key={p.name} className="wz-card" style={{ padding: 28 }}>
              <h2 style={{ fontSize: 22, fontWeight: 800, margin: 0 }}>
                {p.name}
              </h2>
              <p
                style={{
                  margin: "6px 0 0",
                  fontWeight: 700,
                  color: "var(--accent-strong)",
                }}
              >
                {p.line}
              </p>
              <p
                style={{
                  margin: "12px 0 24px",
                  color: "var(--text-secondary)",
                }}
              >
                {p.detail}
              </p>
              {p.href ? (
                <Link href={p.href} className="wz-btn wz-btn-primary">
                  {p.cta}
                </Link>
              ) : (
                <span style={{ color: "var(--text-muted)", fontWeight: 600 }}>
                  {p.cta}
                </span>
              )}
            </li>
          ))}
        </ul>
      </main>
    </div>
  );
}
