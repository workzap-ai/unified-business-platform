import Image from "next/image";
import Link from "next/link";
import type { ReactNode } from "react";
import { APP_URL, PRINCIPLES, TALK } from "./data";

export type SlotKind = "WORKZAP";

/**
 * An answer that is not decided or not yet true. It shows as a dashed marker in
 * previews, and a production deploy refuses to build while any exist, so nothing
 * unfinished can go live looking finished.
 */
export function Slot({
  kind,
  children,
}: {
  kind: SlotKind;
  children: ReactNode;
}) {
  if (process.env.VERCEL_ENV === "production") {
    throw new Error(
      `workzap: unfinished ${kind} slot still on the page. Resolve it before a production deploy.`,
    );
  }
  return (
    <span className="wz-slot" data-slot={kind}>
      <b>{kind}</b> {children}
    </span>
  );
}

/** The W tile and the name. Drawn once, here, and nowhere else. */
export function Logo({ className }: { className?: string }) {
  return (
    <span className={className ? `wz-logo ${className}` : "wz-logo"}>
      <span className="wz-tile" aria-hidden="true">
        W
      </span>
      <span className="wz-wordmark">Workzap</span>
    </span>
  );
}

export function Eyebrow({ children }: { children: ReactNode }) {
  return <p className="wz-eyebrow">{children}</p>;
}

export function ArrowLink({
  href,
  children,
  external = false,
}: {
  href: string;
  children: ReactNode;
  external?: boolean;
}) {
  const inner = (
    <>
      {children}
      <span aria-hidden="true" className="wz-arrow">
        →
      </span>
    </>
  );
  return external ? (
    <a className="wz-arrow-link" href={href}>
      {inner}
    </a>
  ) : (
    <Link className="wz-arrow-link" href={href}>
      {inner}
    </Link>
  );
}

export function Button({
  href,
  children,
  variant = "primary",
  external = false,
}: {
  href: string;
  children: ReactNode;
  variant?: "primary" | "secondary" | "light";
  external?: boolean;
}) {
  const cls = `wz-btn wz-btn-${variant}`;
  return external ? (
    <a className={cls} href={href}>
      {children}
    </a>
  ) : (
    <Link className={cls} href={href}>
      {children}
    </Link>
  );
}

/** Page opening: eyebrow, the one h1, a lead, optional actions. */
export function PageHero({
  eyebrow,
  title,
  lead,
  children,
}: {
  eyebrow: string;
  title: string;
  lead: ReactNode;
  children?: ReactNode;
}) {
  return (
    <section className="wz-hero wz-page-hero">
      <div className="wz-wrap">
        <Eyebrow>{eyebrow}</Eyebrow>
        <h1 className="wz-h1">{title}</h1>
        <p className="wz-lead">{lead}</p>
        {children}
      </div>
    </section>
  );
}

export function SectionHead({
  eyebrow,
  title,
  sub,
}: {
  eyebrow: string;
  title: string;
  sub?: ReactNode;
}) {
  return (
    <div className="wz-head">
      <Eyebrow>{eyebrow}</Eyebrow>
      <h2 className="wz-h2">{title}</h2>
      {sub ? <p className="wz-sub">{sub}</p> : null}
    </div>
  );
}

/** The product lockup, exactly as supplied. Decorative when the link text names it. */
export function Lockup({
  product,
  height,
  decorative = false,
}: {
  product: { full: string; logo: string; width: number; height: number };
  height: number;
  decorative?: boolean;
}) {
  return (
    <Image
      src={product.logo}
      alt={decorative ? "" : product.full}
      width={product.width}
      height={product.height}
      className="wz-lockup"
      style={{ height, width: "auto" }}
      unoptimized
      loading="eager"
    />
  );
}

/** Six plain rules, in a hairline grid. */
export function Principles() {
  return (
    <ul className="wz-principles">
      {PRINCIPLES.map((p) => (
        <li key={p.lead}>
          <span className="wz-mark" aria-hidden="true" />
          <h3 className="wz-h3">{p.lead}</h3>
          <p>{p.text}</p>
        </li>
      ))}
    </ul>
  );
}

/** nori's daily read, as a made-up example. One coral bar, as in the brand. */
export function NoriRead() {
  const bars = [38, 52, 44, 61, 100, 47, 56];
  const days = ["M", "T", "W", "T", "F", "S", "S"];
  return (
    <figure className="wz-read">
      <div className="wz-read-card">
        <div className="wz-read-top">
          <span className="wz-read-kind">Daily read</span>
          <span className="wz-tag wz-tag-ink">Illustrative</span>
        </div>
        <p className="wz-read-title">
          Two best-sellers are running low in one shop.
        </p>
        <div className="wz-read-bars" aria-hidden="true">
          {bars.map((h, i) => (
            <span key={i} className="wz-read-col">
              <span
                className={
                  h === 100 ? "wz-read-bar wz-read-hot" : "wz-read-bar"
                }
                style={{ height: `${h}%` }}
              />
              <span className="wz-read-day">{days[i]}</span>
            </span>
          ))}
        </div>
        <p className="wz-read-foot">
          One thing to look at today. The rest can wait.
        </p>
      </div>
      <figcaption className="wz-cap">
        Illustrative. A real read comes from the business’s own numbers.
      </figcaption>
    </figure>
  );
}

/** pi in a WhatsApp-style chat, as a made-up example. */
export function PiChat() {
  return (
    <figure className="wz-chat">
      <div className="wz-chat-card">
        <div className="wz-chat-head">
          <span className="wz-chat-avatar">
            <Image
              src="/pi-brand/pi-rest-color.svg"
              alt="pi, a violet speech-bubble character with a small amber spark on its head"
              width={34}
              height={34}
              unoptimized
              loading="eager"
            />
          </span>
          <span>
            <strong>pi</strong> <span className="wz-ai">AI</span>
            <span className="wz-chat-sub">by Workzap</span>
          </span>
        </div>
        <div className="wz-chat-body">
          <p className="wz-bub wz-bub-pi">
            <span className="wz-sr">pi says: </span>
            Hi, I’m pi, an AI from Workzap. Tell me what’s going wrong in your
            business.
          </p>
          <p className="wz-bub wz-bub-you">
            <span className="wz-sr">You say: </span>
            We keep running out of our best-selling items.
          </p>
          <p className="wz-bub wz-bub-pi">
            <span className="wz-sr">pi says: </span>
            Noted: stock running out. Anything else?
          </p>
        </div>
      </div>
      <figcaption className="wz-cap">Illustrative conversation.</figcaption>
    </figure>
  );
}

export function CtaBand({
  title,
  sub,
  secondary = { href: "/products", label: "Explore our products" },
}: {
  title: string;
  sub: ReactNode;
  secondary?: { href: string; label: string } | null;
}) {
  return (
    <section className="wz-cta wz-dark" aria-labelledby="wz-cta-title">
      <div className="wz-wrap wz-cta-inner">
        <div>
          <h2 className="wz-h2" id="wz-cta-title">
            {title}
          </h2>
          <p className="wz-sub">{sub}</p>
        </div>
        <div className="wz-actions">
          <Button href={TALK}>Talk to pi</Button>
          {secondary ? (
            <Button href={secondary.href} variant="light">
              {secondary.label}
            </Button>
          ) : null}
        </div>
        <p className="wz-cta-note">
          Already use nori? <a href={APP_URL}>Sign in</a>
        </p>
      </div>
    </section>
  );
}

export function SiteFooter() {
  return (
    <footer className="wz-footer">
      <div className="wz-wrap">
        <div className="wz-foot-grid">
          <div className="wz-foot-brand">
            <Link href="/" aria-label="Workzap, home">
              <Logo />
            </Link>
            <p>
              Workzap makes nori, a daily read for the shop, and pi, a WhatsApp
              agent.
            </p>
          </div>
          <nav aria-label="Products" className="wz-foot-col">
            <h2>Products</h2>
            <ul>
              <li>
                <Link href="/products">All products</Link>
              </li>
              <li>
                <Link href="/nori">nori</Link>
              </li>
              <li>
                <Link href="/pi">pi</Link>
              </li>
            </ul>
          </nav>
          <nav aria-label="nori" className="wz-foot-col">
            <h2>nori</h2>
            <ul>
              <li>
                <Link href="/nori/whats-inside">What’s inside</Link>
              </li>
              <li>
                <Link href="/nori/how-it-works">How it works</Link>
              </li>
              <li>
                <Link href="/nori/pricing">Pricing</Link>
              </li>
              <li>
                <Link href="/nori/faq">FAQ</Link>
              </li>
            </ul>
          </nav>
          <nav aria-label="pi" className="wz-foot-col">
            <h2>pi</h2>
            <ul>
              <li>
                <Link href="/pi/how-it-works">How pi works</Link>
              </li>
              <li>
                <Link href="/pi/who-its-for">Who it’s for</Link>
              </li>
              <li>
                <Link href="/pi/trust">Trust</Link>
              </li>
              <li>
                <Link href="/pi/faq">FAQ</Link>
              </li>
              <li>
                <Link href="/pi/privacy">Privacy</Link>
              </li>
              <li>
                <Link href="/pi/terms">Terms</Link>
              </li>
            </ul>
          </nav>
          <nav aria-label="Company" className="wz-foot-col">
            <h2>Company</h2>
            <ul>
              <li>
                <Link href="/company">About</Link>
              </li>
              <li>
                <Link href="/contact">Contact</Link>
              </li>
            </ul>
            <h2 className="wz-foot-sub">Get started</h2>
            <ul>
              <li>
                <a href={APP_URL}>Sign in</a>
              </li>
            </ul>
          </nav>
        </div>
        <div className="wz-foot-bar">
          <p>© 2026 Workzap</p>
          <p>
            WhatsApp is a trademark of Meta. pi is not made, run or endorsed by
            WhatsApp or Meta.
          </p>
        </div>
      </div>
    </footer>
  );
}
