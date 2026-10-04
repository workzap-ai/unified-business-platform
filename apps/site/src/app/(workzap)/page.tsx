import Link from "next/link";
import { JsonLd, ORGANIZATION, WEBSITE, pageMetadata } from "@/lib/seo";
import { AREAS, PRODUCTS, TALK } from "@/features/workzap/data";
import {
  ArrowLink,
  Button,
  CtaBand,
  Eyebrow,
  Lockup,
  NoriRead,
  PiChat,
  Principles,
  SectionHead,
} from "@/features/workzap/ui";

export const metadata = pageMetadata({
  path: "/",
  title: "Workzap: see what is going wrong, then fix it",
  description:
    "Workzap makes nori, which reads your sales and stock each morning, and pi, a WhatsApp agent that listens to what is going wrong in your business.",
  siteName: "Workzap",
  brand: "workzap",
});

const steps = [
  {
    who: "nori",
    title: "See the numbers",
    text: "nori reads your sales and stock and gives you a short read each morning. It picks out the one thing worth looking at today.",
    href: "/nori/how-it-works",
    link: "How nori works",
  },
  {
    who: "pi",
    title: "Say what is wrong",
    text: "Tell pi what is going wrong, the way you would tell a colleague. pi notes each problem and sorts them.",
    href: "/pi/how-it-works",
    link: "How pi works",
  },
  {
    who: "You",
    title: "Decide",
    text: "When you are ready, you get a solution document and a quote. You read them, then approve, ask for changes or say no.",
    href: "/pi/solutions",
    link: "From problem to solution",
  },
  {
    who: "Workzap",
    title: "Workzap builds it",
    text: "If you say yes, Workzap builds the solution. Payment never happens inside the chat.",
    href: "/pi/faq",
    link: "Questions about pi",
  },
];

export default function Home() {
  return (
    <>
      <JsonLd
        data={{
          "@context": "https://schema.org",
          "@graph": [ORGANIZATION, WEBSITE],
        }}
      />

      <section className="wz-hero">
        <div className="wz-wrap wz-hero-grid">
          <div>
            <Eyebrow>Workzap</Eyebrow>
            <h1 className="wz-h1">
              See what is going wrong in your business. Then fix it.
            </h1>
            <p className="wz-lead">
              Workzap makes software for finding problems and solving them. nori
              reads your sales and stock and picks out the one thing worth
              looking at today. pi is a WhatsApp agent that listens to what is
              going wrong.
            </p>
            <div className="wz-actions">
              <Button href="/products">Explore our products</Button>
              <Button href={TALK} variant="secondary">
                Talk to pi
              </Button>
            </div>
            <p className="wz-hero-note">
              pi is an AI and says so. pi is coming soon.
            </p>
          </div>

          <div className="wz-quick">
            <p className="wz-quick-label">Our products</p>
            <ul>
              <li>
                <Link href={PRODUCTS.nori.href} className="wz-quick-nori">
                  <span className="wz-quick-logo">
                    <Lockup product={PRODUCTS.nori} height={52} decorative />
                  </span>
                  <span>
                    <strong>nori</strong>
                    <small>{PRODUCTS.nori.line}</small>
                  </span>
                  <span className="wz-arrow" aria-hidden="true">
                    →
                  </span>
                </Link>
              </li>
              <li>
                <Link href={PRODUCTS.pi.href} className="wz-quick-pi">
                  <span className="wz-quick-logo">
                    <Lockup product={PRODUCTS.pi} height={60} decorative />
                  </span>
                  <span>
                    <strong>pi</strong>
                    <small>{PRODUCTS.pi.line} Coming soon.</small>
                  </span>
                  <span className="wz-arrow" aria-hidden="true">
                    →
                  </span>
                </Link>
              </li>
            </ul>
          </div>
        </div>
      </section>

      <section
        className="wz-section wz-soft"
        aria-labelledby="suite"
        id="products"
      >
        <div className="wz-wrap">
          <div className="wz-head">
            <Eyebrow>Products</Eyebrow>
            <h2 className="wz-h2" id="suite">
              Two products. One company.
            </h2>
            <p className="wz-sub">
              Each product has its own job and its own look. Both come from
              Workzap.
            </p>
          </div>
          <ul className="wz-suite">
            <li className="wz-panel wz-panel-nori">
              <div className="wz-panel-top">
                <h3>
                  <Lockup product={PRODUCTS.nori} height={64} />
                </h3>
                <span className="wz-tag">Daily read</span>
              </div>
              <p className="wz-panel-line">
                Know which shop is slipping before the week ends.
              </p>
              <p>
                nori reads sales and stock from every shop each night and gives
                you one short morning read: what changed, why, and what to look
                at. Every figure is checked against your own system.
              </p>
              <ul className="wz-ticks">
                <li>Seven areas, from stores and warehouse to finance</li>
                <li>Starter, Growth and Enterprise plans</li>
                <li>Vision (CCTV) is coming soon</li>
              </ul>
              <div className="wz-panel-links">
                <Button href="/nori">Explore nori</Button>
                <ArrowLink href="/nori/pricing">Plans and pricing</ArrowLink>
              </div>
              <div className="wz-panel-art">
                <NoriRead />
              </div>
            </li>
            <li className="wz-panel wz-panel-pi">
              <div className="wz-panel-top">
                <h3>
                  <Lockup product={PRODUCTS.pi} height={64} />
                </h3>
                <span className="wz-tag">Coming soon</span>
              </div>
              <p className="wz-panel-line">
                Tell pi what is going wrong. Workzap builds the solution.
              </p>
              <p>
                pi is Workzap’s WhatsApp agent. Chat about the problems in your
                business. pi notes each one and sorts them. When you are ready,
                you get a solution document and a quote.
              </p>
              <ul className="wz-ticks">
                <li>pi is an AI and says so in its first message</li>
                <li>You decide whether Workzap builds the solution</li>
                <li>Payment never happens inside the chat</li>
              </ul>
              <div className="wz-panel-links">
                <Button href="/pi">Learn about pi</Button>
                <ArrowLink href={TALK}>Talk to pi</ArrowLink>
              </div>
              <div className="wz-panel-art">
                <PiChat />
              </div>
            </li>
          </ul>
        </div>
      </section>

      <section className="wz-section" aria-labelledby="how">
        <div className="wz-wrap">
          <div className="wz-head">
            <Eyebrow>How Workzap works with you</Eyebrow>
            <h2 className="wz-h2" id="how">
              From the numbers to a solution.
            </h2>
            <p className="wz-sub">
              Start with nori, with pi, or with both. You stay in charge at
              every step.
            </p>
          </div>
          <ol className="wz-steps">
            {steps.map((s) => (
              <li key={s.title}>
                <span className="wz-step-who">{s.who}</span>
                <h3 className="wz-h3">{s.title}</h3>
                <p>{s.text}</p>
                <ArrowLink href={s.href}>{s.link}</ArrowLink>
              </li>
            ))}
          </ol>
          <div className="wz-note">
            <p>
              nori comes in three plans: Starter, Growth and Enterprise. They
              differ by size and support.
            </p>
            <ArrowLink href="/nori/pricing">See the plans</ArrowLink>
          </div>
        </div>
      </section>

      <section className="wz-section wz-dark" aria-labelledby="decide">
        <div className="wz-wrap">
          <div className="wz-head">
            <Eyebrow>Who it is for</Eyebrow>
            <h2 className="wz-h2" id="decide">
              Built for the people who decide.
            </h2>
            <p className="wz-sub">
              Owners and department heads. nori gives each of them the part of
              the numbers they answer for.
            </p>
          </div>
          <ul className="wz-roles">
            <li>
              <p className="wz-role">Owner</p>
              <h3 className="wz-h3">See every shop in one place.</h3>
              <p>
                A short read each morning, with sales against target for every
                shop. nori suggests. The owner decides.
              </p>
              <ul className="wz-chips" aria-label="nori areas for owners">
                <li className="wz-chip">Executive and control</li>
              </ul>
            </li>
            <li>
              <p className="wz-role">Operations</p>
              <h3 className="wz-h3">Know the checks were done.</h3>
              <p>
                Daily stock counts and store walks, done by phone with photos
                and location. Transfers sent but never received are flagged when
                stuck.
              </p>
              <ul className="wz-chips" aria-label="nori areas for operations">
                <li className="wz-chip">Stores and warehouse</li>
                <li className="wz-chip">Planning and buying</li>
              </ul>
            </li>
            <li>
              <p className="wz-role">Finance</p>
              <h3 className="wz-h3">Know the margin and the cash.</h3>
              <p>
                Gross margin for any period, with profit by shop. Cash collected
                compared with cash deposited, by shop.
              </p>
              <ul className="wz-chips" aria-label="nori areas for finance">
                <li className="wz-chip">Finance</li>
              </ul>
            </li>
          </ul>
          <div className="wz-areas">
            <div>
              <p>
                Seven areas in all. E-commerce, marketing and customers, and
                people have areas of their own.
              </p>
              <ul className="wz-chips" aria-label="All seven nori areas">
                {AREAS.map((a) => (
                  <li key={a} className="wz-chip">
                    {a}
                  </li>
                ))}
                <li className="wz-chip wz-chip-soon">
                  Vision (CCTV), coming soon
                </li>
              </ul>
            </div>
            <ArrowLink href="/nori/whats-inside">
              See what is inside nori
            </ArrowLink>
          </div>
        </div>
      </section>

      <section className="wz-section wz-soft">
        <div className="wz-wrap">
          <SectionHead
            eyebrow="How we work"
            title="Plain rules we keep."
            sub="What you can count on when you use a Workzap product."
          />
          <Principles />
        </div>
      </section>

      <CtaBand
        title="Tell pi what is going wrong."
        sub="Start a chat on WhatsApp. pi is an AI and says so in its first message. pi is coming soon."
      />
    </>
  );
}
