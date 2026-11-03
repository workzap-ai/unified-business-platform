import Link from "next/link";
import { Closing, Head, PageHead, PI_CONTACT, Shell, TALK } from "./chrome";
import { Badge, type IconName } from "./icons";

const INCLUDED: { icon: IconName; t: string; l: string }[] = [
  { icon: "grid", t: "Every module", l: "All 24 modules, from shop cash to the War Room." },
  { icon: "translate", t: "Urdu and phone", l: "Urdu on the shop floor. Installs on a phone." },
  { icon: "plug", t: "POS connectors", l: "Tell us your POS. We build the connector." },
  { icon: "people", t: "Your people", l: "Owners, admins, members and viewers, each with a role." },
];

const BRAND: { icon: IconName; t: string; l: string }[] = [
  { icon: "palette", t: "Your brand", l: "Change the logo, name, colours and sign-in page in Settings." },
  { icon: "globe", t: "Your domain", l: "Run nori on your own domain." },
  { icon: "server", t: "Your hosting", l: "You host it and run it day to day." },
  { icon: "database", t: "Your data", l: "You put in your own data." },
];

export function NoriPricing() {
  return (
    <Shell current="/nori/pricing">
      <PageHead
        label="Pricing"
        title="One product. One monthly fee."
        lead="Everything is included. We give you the price on a 30-minute call, once we know your shops."
      />

      <section className="nx-section">
        <div className="nx-wrap nv-offer">
          <div className="nv-offer-card nx-on-ink">
            <span className="nx-label">One monthly fee</span>
            <h2>All of nori, for every shop.</h2>
            <p>Price on a 30-minute call, once we know your shops.</p>
            <div className="nx-btn-row">
              <Link className="nx-btn nx-btn-primary" href={TALK}>
                Book a meeting
              </Link>
              <Link className="nx-btn nx-btn-secondary" href={PI_CONTACT}>
                Message pi on WhatsApp
              </Link>
            </div>
          </div>
          <ul className="nv-included">
            {INCLUDED.map((b) => (
              <li key={b.t}>
                <Badge name={b.icon} size={24} />
                <div>
                  <h3>{b.t}</h3>
                  <p>{b.l}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section id="your-brand" className="nx-section nx-white">
        <div className="nx-wrap">
          <Head label="White-label" title="Your brand, your data." lead="We sell nori as it is. You make it yours." />
          <ul className="nv-grid4">
            {BRAND.map((b) => (
              <li key={b.t} className="nv-tile">
                <Badge name={b.icon} size={28} />
                <h3>{b.t}</h3>
                <p>{b.l}</p>
              </li>
            ))}
          </ul>
          <p className="nv-tiny">
            You pay Workzap a service fee every month to use it.
          </p>
        </div>
      </section>

      <Closing />
    </Shell>
  );
}
