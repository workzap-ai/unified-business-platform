import Link from "next/link";
import { Closing, PI_CONTACT, Shell, Shot, TALK } from "./chrome";
import { VideoCard } from "./video-card";
import { FILMS } from "./videos-data";

const OUTCOMES = [
  {
    title: "See which shop is slipping",
    line: "Sales, cash and daily checks, shop by shop.",
    shot: "war-room-top",
    alt: "The War Room: one page of what needs the owner today",
  },
  {
    title: "Stop cash and discounts leaking",
    line: "Counts, deposits and till discounts, side by side.",
    shot: "returns-discounts",
    alt: "Returns and discounts compared across shops",
  },
  {
    title: "Find stock that is stuck",
    line: "What to restock, move or clear first.",
    shot: "planning-margin-map",
    alt: "Planning: every style sorted by margin and sales speed",
  },
];

const FIT = [
  "Clothing and fashion chains",
  "Footwear",
  "Bags and accessories",
  "Kids’ wear",
  "Home textiles",
];

const BESIDE = ["Your till or POS", "Tally", "QuickBooks", "Zoho Books", "Odoo", "Excel"];

const STEPS = [
  { n: "1", title: "Shops record", line: "Cash, stock and store walks, on a phone, with photos." },
  { n: "2", title: "Files come in", line: "Sales and stock from CSV, Excel or Google Sheets." },
  { n: "3", title: "You read one page", line: "What needs you today. You decide." },
];

export function NoriHome() {
  const morning = FILMS[0];
  return (
    <Shell>
      <section className="nx-hero nv-hero">
        <div className="nx-wrap">
          <div className="nv-hero-copy">
            <span className="nx-label">nori by Workzap · for retail chains</span>
            <h1 className="nx-display">
              Know which shop is slipping before the week ends.
            </h1>
            <p className="nx-lead">
              One page for owners of shops: sales, cash, stock and daily checks.
            </p>
            <div className="nx-btn-row">
              <Link className="nx-btn nx-btn-primary" href={TALK}>
                Book a meeting
              </Link>
              <Link className="nx-btn nx-btn-secondary" href={PI_CONTACT}>
                Message pi on WhatsApp
              </Link>
            </div>
          </div>
          <Shot
            name="war-room-top"
            alt="The nori War Room: one page showing what needs the owner today"
            priority
          />
        </div>
      </section>

      <section className="nx-section nv-fit">
        <div className="nx-wrap nv-fit-grid">
          <div>
            <span className="nx-label">Who it is for</span>
            <h2>Built for shops that sell by style and size.</h2>
          </div>
          <div>
            <ul className="nv-chips">
              {FIT.map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ul>
            <p className="nv-note">
              Best with two or more shops and managers you cannot watch daily.
            </p>
            <Link href="/nori/who-its-for">See if nori fits you →</Link>
          </div>
        </div>
      </section>

      <section className="nx-section nx-white">
        <div className="nx-wrap">
          <div className="nx-head">
            <span className="nx-label">What owners get</span>
            <h2>Three worries, answered on one page.</h2>
          </div>
          <ul className="nv-trio">
            {OUTCOMES.map((o) => (
              <li key={o.title}>
                <Shot name={o.shot} alt={o.alt} sizes="(max-width: 880px) 100vw, 340px" tag={false} />
                <h3>{o.title}</h3>
                <p>{o.line}</p>
              </li>
            ))}
          </ul>
          <p className="nv-more">
            <Link href="/nori/whats-inside">See all 24 modules →</Link>
          </p>
        </div>
      </section>

      <section className="nx-section">
        <div className="nx-wrap">
          <div className="nx-head">
            <span className="nx-label">Watch</span>
            <h2>A morning with nori, in under a minute.</h2>
          </div>
          <VideoCard film={morning} />
          <p className="nv-more">
            <Link href="/nori/videos">More films →</Link>
          </p>
        </div>
      </section>

      <section className="nx-section nx-white">
        <div className="nx-wrap">
          <div className="nx-head">
            <span className="nx-label">How it works</span>
            <h2>From the shop floor to your phone.</h2>
          </div>
          <ol className="nv-steps">
            {STEPS.map((s) => (
              <li key={s.n}>
                <span className="nv-step-n" aria-hidden="true">
                  {s.n}
                </span>
                <h3>{s.title}</h3>
                <p>{s.line}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="nx-section">
        <div className="nx-wrap nv-beside">
          <div>
            <span className="nx-label">Alongside your software</span>
            <h2>Keep your till and your accounts.</h2>
            <p className="nx-lead">
              nori sits beside them and reads what they record. Need a connector for
              your POS? We build it.
            </p>
            <p className="nv-more">
              <Link href="/nori/how-nori-fits">How nori fits with what you use →</Link>
            </p>
          </div>
          <ul className="nv-chips nv-chips-quiet">
            {BESIDE.map((b) => (
              <li key={b}>{b}</li>
            ))}
          </ul>
        </div>
        <div className="nx-wrap">
          <p className="nv-tiny">
            nori works beside your till, your accounts and your warehouse system. It
            is not an ERP.
          </p>
        </div>
      </section>

      <section className="nx-section nx-white">
        <div className="nx-wrap nv-beside">
          <div>
            <span className="nx-label">Make it yours</span>
            <h2>Your logo, your name, your colours.</h2>
            <p className="nx-lead">
              Rebrand nori in Settings, run it on your own domain, and pay one
              monthly service fee.
            </p>
            <p className="nv-more">
              <Link href="/nori/pricing#your-brand">Your brand, your data →</Link>
            </p>
          </div>
        </div>
      </section>

      <Closing />
    </Shell>
  );
}
