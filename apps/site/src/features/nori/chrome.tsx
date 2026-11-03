import Image from "next/image";
import Link from "next/link";
import { Icon } from "./icons";

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
        <Link className="nx-btn nx-btn-primary nx-nav-cta" href={TALK}>
          Book a meeting
        </Link>
        <details className="nx-menu">
          <summary>
            <span>Menu</span>
            <Icon name="menu" size={20} className="nx-menu-open" />
            <Icon name="close" size={20} className="nx-menu-close" />
          </summary>
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
            <Link className="nx-btn nx-btn-primary" href={TALK}>
              Book a meeting
            </Link>
          </nav>
        </details>
      </div>
    </header>
  );
}

export function Footer() {
  return (
    <footer className="nx-footer nx-on-ink">
      <div className="nx-wrap nx-foot-grid">
        <div className="nx-foot-brand">
          <span className="nx-foot-mark">nori</span>
          <span className="nx-foot-by">by Workzap</span>
          <Link className="nx-btn nx-btn-primary" href={TALK}>
            Book a meeting
          </Link>
        </div>
        <nav aria-label="nori, footer">
          <p className="nx-foot-h">nori</p>
          <ul>
            {FOOT.map((l) => (
              <li key={l.href}>
                <Link href={l.href}>{l.label}</Link>
              </li>
            ))}
          </ul>
        </nav>
        <nav aria-label="nori, contact">
          <p className="nx-foot-h">Contact</p>
          <ul>
            <li>
              <Link href={TALK}>Book a meeting</Link>
            </li>
            <li>
              <Link href={PI_CONTACT}>Talk to pi</Link>
            </li>
            <li>
              <a href={APP}>Sign in</a>
            </li>
            <li>
              <Link href="/">Workzap</Link>
            </li>
          </ul>
        </nav>
      </div>
      <div className="nx-wrap nx-foot-base">
        <span>© 2026 Workzap</span>
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

// One section header for every page: a small label, the heading, an optional lead.
export function Head({
  label,
  title,
  lead,
}: {
  label?: string;
  title: string;
  lead?: string;
}) {
  return (
    <div className="nx-head">
      {label ? <span className="nx-label">{label}</span> : null}
      <h2>{title}</h2>
      {lead ? <p className="nx-lead">{lead}</p> : null}
    </div>
  );
}

// A real screen from the product. Wide screens get a slim window bar. The shop-floor pages
// are a narrow column, kept as a phone-shaped crop (names ending "-zoom"). `crop` fills
// its parent and shows the top left of the screen, for tiles of a fixed shape.
export function Shot({
  name,
  alt,
  priority,
  sizes,
  crop,
}: {
  name: string;
  alt: string;
  priority?: boolean;
  sizes?: string;
  crop?: boolean;
}) {
  const phone = name.endsWith("-zoom");
  const cls = ["nv-shot", phone ? "nv-shot-phone" : "", crop ? "nv-shot-crop" : ""]
    .filter(Boolean)
    .join(" ");
  return (
    <figure className={cls}>
      {!phone && !crop ? (
        <div className="nv-bar" aria-hidden="true">
          <i />
          <i />
          <i />
        </div>
      ) : null}
      <Image
        src={`/nori-screens/${name}.v3.webp`}
        alt={alt}
        width={phone ? 700 : 1288}
        height={phone ? 640 : 690}
        sizes={sizes ?? "(max-width: 880px) 100vw, 1080px"}
        quality={90}
        priority={priority}
      />
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
      <div className="nx-wrap nx-cta-grid">
        <div>
          <h2>{title}</h2>
          <p>{text}</p>
        </div>
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
