import Image from "next/image";
import Link from "next/link";

export const APP = "https://app.workzap.ai";
// Every contact touch point goes to pi (owner decision, 3 Oct 2026).
export const PI_CONTACT = "/pi/talk-to-pi";
export const TALK = "/nori/talk";

export const NAV = [
  { href: "/nori/whats-inside", label: "What’s inside" },
  { href: "/nori/who-its-for", label: "Who it’s for" },
  { href: "/nori/how-it-works", label: "How it works" },
  { href: "/nori/how-nori-fits", label: "How nori fits" },
  { href: "/nori/pricing", label: "Pricing" },
  { href: "/nori/videos", label: "Videos" },
];

const FOOT = [...NAV, { href: "/nori/faq", label: "FAQ" }];

function Header({ current }: { current?: string }) {
  return (
    <header className="nx-header">
      <div className="nx-wrap nx-nav">
        <Link href="/nori" className="nx-brand">
          <Image
            src="/nori-brand/nori-lockup-horizontal-color.svg"
            alt="nori by Workzap"
            width={163}
            height={56}
            priority
            unoptimized
          />
        </Link>
        <nav className="nx-links" aria-label="nori">
          {NAV.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              aria-current={l.href === current ? "page" : undefined}
            >
              {l.label}
            </Link>
          ))}
          <a href={APP}>Sign in</a>
        </nav>
        <Link className="nx-btn nx-btn-primary" href={TALK}>
          Book a meeting
        </Link>
        <details className="nx-menu">
          <summary>Menu</summary>
          <nav aria-label="nori, menu">
            {FOOT.map((l) => (
              <Link
                key={l.href}
                href={l.href}
                aria-current={l.href === current ? "page" : undefined}
              >
                {l.label}
              </Link>
            ))}
            <a href={APP}>Sign in</a>
            <Link href={TALK}>Book a meeting</Link>
          </nav>
        </details>
      </div>
    </header>
  );
}

export function Footer() {
  return (
    <footer className="nx-footer nx-on-ink">
      <div className="nx-wrap">
        <span>nori by Workzap · © 2026 Workzap</span>
        <div className="nx-footer-links">
          {FOOT.map((l) => (
            <Link key={l.href} href={l.href}>
              {l.label}
            </Link>
          ))}
          <a href={APP}>Sign in</a>
          <Link href={PI_CONTACT}>Talk to pi</Link>
          <Link href="/">Workzap</Link>
        </div>
        <p className="nv-foot-note">
          Screens on this site come from a demo workspace with dummy data.
        </p>
      </div>
    </footer>
  );
}

export function Shell({
  current,
  children,
}: {
  current?: string;
  children: React.ReactNode;
}) {
  return (
    <>
      <a className="nx-skip" href="#main">
        Skip to content
      </a>
      <Header current={current} />
      <main id="main">{children}</main>
      <Footer />
    </>
  );
}

export function PageHead({
  label,
  title,
  lead,
}: {
  label: string;
  title: string;
  lead: string;
}) {
  return (
    <section className="nx-pagehead">
      <div className="nx-wrap">
        <nav className="nx-crumb" aria-label="Breadcrumb">
          <Link href="/nori">nori</Link>
          <span aria-hidden="true">/</span>
          <span>{label}</span>
        </nav>
        <h1 className="nx-display">{title}</h1>
        <p className="nx-lead">{lead}</p>
      </div>
    </section>
  );
}

// A real screen from the demo workspace, in a plain frame. Dummy data, labelled.
export function Shot({
  name,
  alt,
  priority,
  sizes,
  tag = true,
}: {
  name: string;
  alt: string;
  priority?: boolean;
  sizes?: string;
  tag?: boolean;
}) {
  return (
    <figure className="nv-shot">
      <Image
        src={`/nori-screens/${name}.webp`}
        alt={alt}
        width={1352}
        height={778}
        sizes={sizes ?? "(max-width: 880px) 100vw, 1080px"}
        priority={priority}
      />
      {tag ? <figcaption>Demo workspace · dummy data</figcaption> : null}
    </figure>
  );
}

export function Closing({
  title = "Talk to us for 30 minutes.",
  text = "Tell us how many shops you run. We show you the screens for your role.",
}: {
  title?: string;
  text?: string;
}) {
  return (
    <section className="nx-cta nx-on-ink">
      <div className="nx-wrap">
        <h2>{title}</h2>
        <p>{text}</p>
        <div className="nx-btn-row">
          <Link className="nx-btn nx-btn-primary" href={TALK}>
            Book a meeting
          </Link>
          <Link className="nx-btn nx-btn-secondary" href={PI_CONTACT}>
            Message pi on WhatsApp
          </Link>
        </div>
      </div>
    </section>
  );
}
