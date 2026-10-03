import Image from "next/image";
import Link from "next/link";
import { ModulesSection } from "./explorer/modules-section";

const APP = "https://app.workzap.ai";
// Every contact touch point goes to pi (owner decision, 3 Oct 2026).
const PI_CONTACT = "/pi/talk-to-pi";

const NAV = [
  { href: "/nori/whats-inside", label: "What’s inside" },
  { href: "/nori/how-it-works", label: "How it works" },
  { href: "/nori/pricing", label: "Pricing" },
];

function Header({ current }: { current?: string }) {
  return (
    <header className="nx-header">
      <div className="nx-wrap nx-nav">
        <Link
          href="/nori"
          className="nx-brand"
          aria-label="nori by Workzap, home"
        >
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
        <a className="nx-btn nx-btn-primary" href={APP}>
          Get started
        </a>
        <details className="nx-menu">
          <summary>Menu</summary>
          <nav aria-label="nori, menu">
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
            <a href={APP}>Get started</a>
          </nav>
        </details>
      </div>
    </header>
  );
}

// Seven made-up days of sales, in rupees. The last one is yesterday (Tuesday) and carries
// the single coral bar. It is also named in words, never by colour alone.
const WEEK = [
  { day: "Wed", value: 41800, look: false },
  { day: "Thu", value: 44300, look: false },
  { day: "Fri", value: 49600, look: false },
  { day: "Sat", value: 58100, look: false },
  { day: "Sun", value: 55200, look: false },
  { day: "Mon", value: 46900, look: false },
  { day: "Tue", value: 52400, look: true },
];
const WEEK_MAX = 60000;
const WEEK_LABEL = `Sales per day for the last 7 days, in rupees. ${WEEK.map(
  (d) =>
    `${d.day} ${d.value.toLocaleString("en-US")}${d.look ? ", yesterday, marked" : ""}`,
).join(". ")}.`;

// Decorative barcode strip: a chart device, not the mark. Widths only, ink on paper.
const STRIP = [
  8, 4, 16, 4, 4, 8, 16, 4, 8, 4, 4, 16, 8, 4, 8, 16, 4, 4, 8, 4, 16, 8, 4, 4,
  16, 8, 4, 8, 4, 16, 4, 8, 8, 4, 16, 4, 4, 8, 16, 4,
];

function BarcodeStrip() {
  return (
    <div className="nx-strip" aria-hidden="true">
      {[...STRIP, ...STRIP, ...STRIP].map((w, i) => (
        <span key={i} style={{ width: w }} />
      ))}
    </div>
  );
}

function Hero() {
  return (
    <section className="nx-hero">
      <div className="nx-wrap nx-hero-grid">
        <div>
          <span className="nx-label">The daily read for the shop</span>
          <h1 className="nx-display">One thing worth looking at.</h1>
          <p className="nx-lead">
            A shop throws off more numbers than anyone can read. nori reads them
            all and picks out the one that matters today.
          </p>
          <div className="nx-btn-row">
            <a className="nx-btn nx-btn-primary" href={APP}>
              Get started
            </a>
            <Link className="nx-btn nx-btn-secondary" href={PI_CONTACT}>
              Book a demo
            </Link>
          </div>
        </div>
        <div
          className="nx-dash nx-on-ink"
          role="group"
          aria-label="A sample nori screen (illustrative)"
        >
          <div className="nx-dash-head">
            <div className="nx-dash-tabs">
              <span>Today</span>
              <span>Shops</span>
              <span>Stock</span>
              <span>Money</span>
            </div>
            <span className="nx-tag">Illustrative</span>
          </div>
          <div className="nx-dash-main">
            <span className="nx-label">Yesterday</span>
            <span className="nx-figure">Rs 52,400</span>
            <span className="nx-dash-sub">
              71 sales · Rs 4,600 more than last Tuesday
            </span>
          </div>
          <figure className="nx-chart">
            <div className="nx-chart-plot" role="img" aria-label={WEEK_LABEL}>
              <div className="nx-chart-bars" aria-hidden="true">
                {WEEK.map((d) => (
                  <span
                    key={d.day}
                    className={d.look ? "is-look" : undefined}
                    style={{ height: `${(d.value / WEEK_MAX) * 100}%` }}
                  />
                ))}
              </div>
              <div className="nx-chart-days" aria-hidden="true">
                {WEEK.map((d) => (
                  <span key={d.day}>{d.day}</span>
                ))}
              </div>
            </div>
            <figcaption>
              Sales per day, last 7 days. The coral bar is yesterday, Tuesday.
            </figcaption>
          </figure>
          <div className="nx-dash-tiles">
            <div className="nx-dash-tile">
              <span className="nx-label">Running low</span>
              <ul>
                <li>Detergent 1 kg · 2 days</li>
                <li>Biscuits 200 g · 3 days</li>
                <li>Rice 5 kg · 5 days</li>
              </ul>
            </div>
            <div className="nx-dash-tile">
              <span className="nx-label">Look at this</span>
              <span className="nx-dash-look">
                Shop D is behind target this week
              </span>
              <span className="nx-dash-sub">
                A suggestion is ready when you want it.
              </span>
            </div>
          </div>
        </div>
      </div>
      <BarcodeStrip />
    </section>
  );
}

const PROBLEMS = [
  {
    title: "Numbers sit in five places.",
    text: "Sales are in the till, stock is in a sheet, and the shops send updates by message. Nothing adds up in one view.",
  },
  {
    title: "The report arrives after the week.",
    text: "By the time it lands, the week is over. You see what already happened.",
  },
  {
    title: "Margin is hard to see.",
    text: "Sales are easy to see. Margin after discounts, tax and cost is harder, and rarely live.",
  },
  {
    title: "Decisions rest on a feeling.",
    text: "Which shop to push, what to reorder and where margin leaks are mostly guesses.",
  },
];

function Problems() {
  return (
    <section className="nx-section nx-white">
      <div className="nx-wrap nx-split">
        <div className="nx-head">
          <span className="nx-label">Why nori</span>
          <h2>A shop has more numbers than time.</h2>
          <p className="nx-lead">
            You have more data than ever and less time to read it.
          </p>
        </div>
        <ul className="nx-problems">
          {PROBLEMS.map((p) => (
            <li key={p.title}>
              <h3>{p.title}</h3>
              <p>{p.text}</p>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

const READS = [
  {
    title: "What happened",
    text: "Every figure for every shop and channel, checked against your own system and refreshed nightly.",
  },
  {
    title: "Why it moved",
    text: "The shop, item, discount or day behind the change, in plain words.",
  },
  {
    title: "What matters",
    text: "The one thing worth looking at today. The rest stays quiet.",
  },
  {
    title: "Your call",
    text: "A suggestion you can take or leave. The owner decides.",
  },
];

function Reads() {
  return (
    <section className="nx-section nx-band nx-on-ink">
      <div className="nx-wrap">
        <div className="nx-head">
          <span className="nx-label">How nori reads</span>
          <h2>A number, why it moved, and what to look at.</h2>
        </div>
        <div className="nx-cards">
          {READS.map((r, i) => (
            <div key={r.title} className="nx-card">
              <span
                className="nx-card-num"
                aria-hidden="true"
              >{`0${i + 1}`}</span>
              <h3>{r.title}</h3>
              <p>{r.text}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

const STEPS = [
  {
    title: "Connect your data",
    text: "Upload a sales file, or connect your till system so it syncs every night. nori matches the columns for you.",
  },
  {
    title: "nori reads it all",
    text: "It goes through every shop, item and day. It picks out margin leaks, shops behind target, dead stock and odd figures.",
  },
  {
    title: "You get the read",
    text: "A short read each morning, and tasks your team can own. Everything works from a phone or a desk.",
  },
];

function How() {
  return (
    <section className="nx-section nx-white">
      <div className="nx-wrap">
        <ol className="nx-steps">
          {STEPS.map((s, i) => (
            <li key={s.title}>
              <span className="nx-stepbars" aria-hidden="true">
                {[0, 1, 2].map((n) => (
                  <i key={n} className={n <= i ? "on" : undefined} />
                ))}
              </span>
              <span className="nx-sr">{`Step ${i + 1} of ${STEPS.length}`}</span>
              <h3>{s.title}</h3>
              <p>{s.text}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

const QUESTIONS = [
  "Which shop is behind target, and why?",
  "What is my real margin after discounts, tax and cost?",
  "What should I reorder this week, and what is dead stock?",
  "Why did profit fall last month when sales went up?",
  "Are my discounts winning sales, or just cutting margin?",
  "Which categories are slowing before it hurts?",
];

function Questions() {
  return (
    <section className="nx-section">
      <div className="nx-wrap nx-split nx-ask">
        <div>
          <div className="nx-head">
            <span className="nx-label">Ask in plain words</span>
            <h2>
              The questions you already ask, answered from your own numbers.
            </h2>
            <p className="nx-lead">
              Each answer comes with the figure and what it is compared with.
            </p>
          </div>
          <ul className="nx-questions">
            {QUESTIONS.map((q, i) => (
              <li key={q}>
                “{q}”
                {i === 0 ? (
                  <span className="nx-small"> Example answer shown.</span>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
        <div
          className="nx-msg"
          role="group"
          aria-label="A sample answer from nori (illustrative)"
        >
          <div className="nx-msg-head">
            <span className="nx-msg-name">
              nori <span>· by Workzap</span>
            </span>
            <span className="nx-tag">Illustrative</span>
          </div>
          <p className="nx-msg-q">Which shop is behind target, and why?</p>
          <div className="nx-msg-a">
            <p>
              <b>Shop D</b> has sold <b className="nx-num">Rs 96,000</b> this
              week against a target of Rs 140,000. That is Rs 44,000 short with
              two days left.
            </p>
            <p className="nx-look">
              <span className="nx-coral-mark" aria-hidden="true" />
              <span>
                <b>Look at this:</b> Thursday and Friday had 22 fewer sales than
                the same days last week.
              </span>
            </p>
            <p>A suggestion is ready when you want it.</p>
          </div>
        </div>
      </div>
    </section>
  );
}

const PLANS = [
  {
    name: "Starter",
    who: "Single store getting started",
    items: [
      "Everything in nori (Vision coming soon)",
      "Nightly data sync",
      "Email support",
    ],
  },
  {
    name: "Growth",
    who: "Multi-outlet retailers",
    items: [
      "Everything in nori (Vision coming soon)",
      "Up to 10 outlets",
      "Questions in plain words, without a limit",
      "Priority support",
    ],
  },
  {
    name: "Enterprise",
    who: "Chains and groups",
    items: [
      "Everything in Growth",
      "Unlimited outlets and seats",
      "Custom connectors",
      "Dedicated onboarding",
    ],
  },
];

function Pricing() {
  return (
    <section className="nx-section nx-white">
      <div className="nx-wrap">
        <div className="nx-plans">
          {PLANS.map((p) => (
            <div key={p.name} className="nx-plan">
              <div>
                <h3>{p.name}</h3>
                <p className="nx-small">{p.who}</p>
              </div>
              <ul>
                {p.items.map((i) => (
                  <li key={i}>{i}</li>
                ))}
              </ul>
              <Link className="nx-btn nx-btn-secondary" href={PI_CONTACT}>
                Book a demo
              </Link>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

// Decorative chart: seven bars, one coral. Not the mark, and it carries no data.
const CLOSE_BARS = [35, 55, 45, 70, 60, 100, 50];

function Closing() {
  return (
    <section className="nx-cta nx-on-ink">
      <div className="nx-wrap nx-cta-grid">
        <div>
          <h2>See nori on your own numbers.</h2>
          <p>
            Create your workspace, upload a sales file, and get your first read.
          </p>
          <div className="nx-btn-row">
            <a className="nx-btn nx-btn-primary" href={APP}>
              Get started
            </a>
            <Link className="nx-btn nx-btn-secondary" href={PI_CONTACT}>
              Book a demo
            </Link>
          </div>
        </div>
        <figure className="nx-cta-chart">
          <div className="nx-cta-bars" aria-hidden="true">
            {CLOSE_BARS.map((h, i) => (
              <span
                key={i}
                className={i === 5 ? "is-look" : undefined}
                style={{ height: `${h}%` }}
              />
            ))}
          </div>
          <figcaption>Seven days. One bar to look at.</figcaption>
        </figure>
      </div>
    </section>
  );
}

function PageHead({
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

const EXPLORE = [
  {
    href: "/nori/whats-inside",
    title: "What’s inside",
    text: "Shops, money, stock, online, marketing and people. Seven areas, each with the numbers and the next step.",
  },
  {
    href: "/nori/how-it-works",
    title: "How it works",
    text: "Connect your data, let nori read it, and get a short read each morning.",
  },
  {
    href: "/nori/pricing",
    title: "Pricing",
    text: "One setup, then a simple monthly plan. Every plan has everything. You choose the size and the support.",
  },
];

function Explore() {
  return (
    <section className="nx-section">
      <div className="nx-wrap">
        <div className="nx-head">
          <span className="nx-label">Look around</span>
          <h2>Where to next.</h2>
        </div>
        <ul className="nx-explore">
          {EXPLORE.map((e) => (
            <li key={e.href}>
              <Link href={e.href} className="nx-explore-card">
                <h3>{e.title}</h3>
                <p>{e.text}</p>
                <span className="nx-explore-go">Open →</span>
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="nx-footer nx-on-ink">
      <div className="nx-wrap">
        <span>nori by Workzap · © 2026 Workzap</span>
        <div className="nx-footer-links">
          {NAV.map((l) => (
            <Link key={l.href} href={l.href}>
              {l.label}
            </Link>
          ))}
          <a href={APP}>Sign in</a>
          <Link href={PI_CONTACT}>Contact</Link>
          <Link href="/">Workzap</Link>
        </div>
      </div>
    </footer>
  );
}

function Shell({
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

export function NoriHome() {
  return (
    <Shell>
      <Hero />
      <Problems />
      <Reads />
      <Explore />
      <Closing />
    </Shell>
  );
}

export function NoriInside() {
  return (
    <Shell current="/nori/whats-inside">
      <PageHead
        label="What’s inside"
        title="Your whole retail business, run from one place."
        lead="Shops, money, stock, online, marketing and people. Each comes with the numbers, the reasons and the next step."
      />
      <ModulesSection />
      <Closing />
    </Shell>
  );
}

export function NoriHow() {
  return (
    <Shell current="/nori/how-it-works">
      <PageHead
        label="How it works"
        title="From your data to a decision in three steps."
        lead="Connect your data once. nori does the reading and brings you the one thing worth looking at."
      />
      <How />
      <Questions />
      <Closing />
    </Shell>
  );
}

export function NoriPricing() {
  return (
    <Shell current="/nori/pricing">
      <PageHead
        label="Pricing"
        title="The whole platform, sized to your business."
        lead="A one-time setup to connect your data, then a simple monthly subscription. Every plan has everything. You choose the size and the support."
      />
      <Pricing />
      <Closing />
    </Shell>
  );
}
