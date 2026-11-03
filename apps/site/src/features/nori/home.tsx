import Link from "next/link";
import { Closing, Head, PI_CONTACT, Shell, Shot, TALK } from "./chrome";
import { Badge, Icon, type IconName } from "./icons";
import { Logos } from "./logos";
import { VideoCard } from "./video-card";
import { FILMS } from "./videos-data";

const PROOF = [
  "24 modules in one product",
  "Urdu on the shop floor",
  "Works beside your till",
];

const OUTCOMES = [
  {
    icon: "store" as IconName,
    title: "See which shop is slipping",
    line: "Sales, cash and daily checks, shop by shop.",
    shot: "war-room-top",
    alt: "The War Room: one page of what needs the owner today",
  },
  {
    icon: "coins" as IconName,
    title: "Stop cash and discounts leaking",
    line: "Counts, deposits and till discounts, side by side.",
    shot: "returns-discounts",
    alt: "Returns and discounts compared across shops",
  },
  {
    icon: "box" as IconName,
    title: "Find stock that is stuck",
    line: "What to restock, move or clear first.",
    shot: "planning-margin-map",
    alt: "Planning: every style sorted by margin and sales speed",
  },
];

const FIT: { label: string; icon: IconName }[] = [
  { label: "Clothing and fashion chains", icon: "shirt" },
  { label: "Footwear", icon: "shoe" },
  { label: "Bags and accessories", icon: "bag" },
  { label: "Kids’ wear", icon: "kids" },
  { label: "Home textiles", icon: "bed" },
];

const STEPS: { n: string; icon: IconName; title: string; line: string }[] = [
  { n: "1", icon: "phone", title: "Shops record", line: "Cash, stock and store walks, on a phone, with photos." },
  { n: "2", icon: "file", title: "Files come in", line: "Sales and stock from CSV, Excel or Google Sheets." },
  { n: "3", icon: "page", title: "You read one page", line: "What needs you today. You decide." },
];

const BRAND: { label: string; icon: IconName }[] = [
  { label: "Your logo", icon: "image" },
  { label: "Your name", icon: "type" },
  { label: "Your colours", icon: "palette" },
  { label: "Your domain", icon: "globe" },
];

export function NoriHome() {
  const morning = FILMS[0];
  return (
    <Shell>
      <section className="nv-hero">
        <div className="nx-wrap nv-hero-grid">
          <div className="nv-hero-copy">
            <span className="nx-label">nori by Workzap, for retail chains</span>
            <h1 className="nx-display">
              See what is going wrong in your business. Then fix it.
            </h1>
            <p className="nx-lead">
              nori puts sales, cash, stock and daily shop checks on one page. You see the slip early, and you act on it.
            </p>
            <div className="nx-btn-row">
              <Link className="nx-btn nx-btn-primary" href={TALK}>
                Book a meeting
              </Link>
              <Link className="nx-btn nx-btn-secondary" href={PI_CONTACT}>
                Message pi on WhatsApp
              </Link>
            </div>
            <ul className="nv-proof">
              {PROOF.map((p) => (
                <li key={p}>
                  <Icon name="check" size={16} />
                  {p}
                </li>
              ))}
            </ul>
          </div>
          <div className="nv-stage">
            <Shot
              name="war-room-top"
              alt="The nori War Room: one page showing what needs the owner today"
              sizes="(max-width: 960px) 100vw, 720px"
              priority
            />
            <div className="nv-stage-phone">
              <Shot
                name="store-walk-zoom"
                alt="Store Walk on a shop phone: the daily photo checklist"
                sizes="(max-width: 960px) 45vw, 280px"
              />
            </div>
          </div>
        </div>
      </section>

      <section className="nx-section nx-band nx-on-ink">
        <div className="nx-wrap">
          <Head label="What owners get" title="Three worries, answered on one page." />
          <ul className="nv-bento">
            {OUTCOMES.map((o, i) => (
              <li key={o.title} className={`nv-bento-${i + 1}`}>
                <div className="nv-bento-text">
                  <Badge name={o.icon} />
                  <h3>{o.title}</h3>
                  <p>{o.line}</p>
                </div>
                <div className="nv-peek">
                  <Shot
                    name={o.shot}
                    alt={o.alt}
                    crop
                    sizes={i === 1 ? "(max-width: 880px) 100vw, 460px" : "(max-width: 880px) 100vw, 640px"}
                  />
                </div>
              </li>
            ))}
          </ul>
          <p className="nv-more">
            <Link className="nv-link" href="/nori/whats-inside">
              See all 24 modules
              <Icon name="arrow" size={16} />
            </Link>
          </p>
        </div>
      </section>

      <section className="nx-section nx-white">
        <div className="nx-wrap nv-fit-grid">
          <div>
            <Head label="Who it is for" title="Built for shops that sell by style and size." />
            <p className="nv-note">
              Best with two or more shops and managers you cannot watch daily.
            </p>
            <p className="nv-more">
              <Link className="nv-link" href="/nori/who-its-for">
                See if nori fits you
                <Icon name="arrow" size={16} />
              </Link>
            </p>
          </div>
          <ul className="nv-chips">
            {FIT.map((f) => (
              <li key={f.label}>
                <Badge name={f.icon} size={20} />
                {f.label}
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="nx-section">
        <div className="nx-wrap nv-watch">
          <VideoCard film={morning} />
          <div>
            <Head label="Watch" title="A morning with nori, in under a minute." />
            <p className="nv-more">
              <Link className="nv-link" href="/nori/videos">
                More films
                <Icon name="arrow" size={16} />
              </Link>
            </p>
          </div>
        </div>
      </section>

      <section className="nx-section nx-white">
        <div className="nx-wrap">
          <Head label="How it works" title="From the shop floor to your phone." />
          <ol className="nv-steps">
            {STEPS.map((s) => (
              <li key={s.n}>
                <div className="nv-step-top">
                  <Badge name={s.icon} size={28} />
                  <span className="nv-step-n" aria-hidden="true">
                    {s.n}
                  </span>
                </div>
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
            <Head label="Alongside your software" title="Keep your till and your accounts." lead="nori sits beside them and reads what they record. Need a connector for your POS? We build it." />
            <p className="nv-more">
              <Link className="nv-link" href="/nori/how-nori-fits">
                How nori fits with what you use
                <Icon name="arrow" size={16} />
              </Link>
            </p>
          </div>
          <Logos />
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
            <Head label="Make it yours" title="Your logo, your name, your colours." lead="Rebrand nori in Settings, run it on your own domain, and pay one monthly service fee." />
            <p className="nv-more">
              <Link className="nv-link" href="/nori/pricing#your-brand">
                Your brand, your data
                <Icon name="arrow" size={16} />
              </Link>
            </p>
          </div>
          <ul className="nv-mini">
            {BRAND.map((b) => (
              <li key={b.label}>
                <Badge name={b.icon} size={22} />
                {b.label}
              </li>
            ))}
          </ul>
        </div>
      </section>

      <Closing />
    </Shell>
  );
}
