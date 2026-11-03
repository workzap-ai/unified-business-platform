import Link from "next/link";
import { Closing, PageHead, Shell, TALK } from "./chrome";

const PLANS = [
  {
    name: "Starter",
    who: "One store",
    items: ["Every module", "Email support"],
  },
  {
    name: "Growth",
    who: "Up to 10 outlets",
    items: ["Every module", "Priority support"],
  },
  {
    name: "Enterprise",
    who: "Chains and groups",
    items: ["Everything in Growth", "Unlimited outlets and seats", "Connectors built for your POS", "Dedicated onboarding"],
  },
];

const BRAND = [
  { t: "Your brand", l: "Change the logo, name, colours and sign-in page in Settings." },
  { t: "Your domain", l: "Run nori on your own domain." },
  { t: "Your hosting", l: "You host it and run it day to day." },
  { t: "Your data", l: "You put in your own data." },
  { t: "One monthly fee", l: "You pay Workzap a service fee every month." },
];

export function NoriPricing() {
  return (
    <Shell current="/nori/pricing">
      <PageHead
        label="Pricing"
        title="Plans sized to your shops."
        lead="Every plan has every module. You choose the size and the support."
      />

      <section className="nx-section">
        <div className="nx-wrap">
          <ul className="nv-plans">
            {PLANS.map((p) => (
              <li key={p.name} className="nv-plan">
                <h2>{p.name}</h2>
                <p className="nv-plan-who">{p.who}</p>
                <ul className="nv-plain">
                  {p.items.map((i) => (
                    <li key={i}>{i}</li>
                  ))}
                </ul>
                <Link className="nx-btn nx-btn-secondary" href={TALK}>
                  Book a meeting
                </Link>
              </li>
            ))}
          </ul>
          <p className="nv-tiny">
            We give you the price on a 30-minute call, once we know your shops. Vision
            (CCTV) is coming soon.
          </p>
        </div>
      </section>

      <section id="your-brand" className="nx-section nx-white">
        <div className="nx-wrap">
          <div className="nx-head">
            <span className="nx-label">White-label</span>
            <h2>Your brand, your data.</h2>
            <p className="nx-lead">
              We sell nori as it is. You make it yours.
            </p>
          </div>
          <ul className="nv-grid5">
            {BRAND.map((b) => (
              <li key={b.t} className="nv-tile">
                <h3>{b.t}</h3>
                <p>{b.l}</p>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <Closing />
    </Shell>
  );
}
