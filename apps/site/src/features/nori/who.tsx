import { Closing, PageHead, Shell, Shot } from "./chrome";

const BEST = [
  { t: "Clothing and fashion chains", l: "Styles, sizes, seasons and many shops. Where nori was shaped." },
  { t: "Footwear", l: "Sizes and styles spread across shops." },
  { t: "Bags and accessories", l: "Fast-moving items, shop by shop." },
  { t: "Kids’ wear and home textiles", l: "Same pattern: many styles, many shops." },
];

const GOOD_WHEN = [
  "You have two or more shops.",
  "Someone else counts the cash.",
  "Stock sits in the wrong shop.",
  "You chase managers on WhatsApp.",
  "Your staff read Urdu.",
];

const ASK_FIRST = [
  "One small shop where you do everything yourself.",
  "Restaurants, salons and clinics. nori is for shops that sell goods.",
  "Items that expire or are sold by weight. Ask us first.",
];

const ROLES = [
  {
    who: "Owner",
    line: "One page each morning.",
    points: ["Which shops are behind", "What does not tie", "What waits for your yes"],
    shot: "war-room-top",
  },
  {
    who: "Head of operations",
    line: "Proof the daily jobs were done.",
    points: ["Store walks with photos", "Daily stock counts", "Stock sent, never received"],
    shot: "store-walk-zoom",
  },
  {
    who: "Head of finance",
    line: "Cash and margin that tie.",
    points: ["Drawer, deposit, bank", "Till discounts by shop", "P&L on one screen"],
    shot: "finance-today",
  },
  {
    who: "Store and area managers",
    line: "Small daily jobs on a phone.",
    points: ["Count the drawer", "Walk the shop", "Ask the warehouse for stock"],
    shot: "stock-audit-zoom",
  },
];

export function NoriWho() {
  return (
    <Shell current="/nori/who-its-for">
      <PageHead
        label="Who it’s for"
        title="Who nori is for."
        lead="Retail chains that sell goods, and the people who run them."
      />

      <section className="nx-section">
        <div className="nx-wrap">
          <div className="nx-head">
            <span className="nx-label">Industries</span>
            <h2>Best for shops that sell by style and size.</h2>
          </div>
          <ul className="nv-grid4">
            {BEST.map((b) => (
              <li key={b.t} className="nv-tile">
                <h3>{b.t}</h3>
                <p>{b.l}</p>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="nx-section nx-white">
        <div className="nx-wrap nv-two">
          <div>
            <span className="nx-label">A good fit when</span>
            <ul className="nv-ticks">
              {GOOD_WHEN.map((g) => (
                <li key={g}>{g}</li>
              ))}
            </ul>
          </div>
          <div>
            <span className="nx-label">Talk to us first if</span>
            <ul className="nv-plain">
              {ASK_FIRST.map((g) => (
                <li key={g}>{g}</li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      <section className="nx-section">
        <div className="nx-wrap">
          <div className="nx-head">
            <span className="nx-label">Roles</span>
            <h2>Each person sees the part they answer for.</h2>
          </div>
          <ul className="nv-roles">
            {ROLES.map((r) => (
              <li key={r.who}>
                <Shot name={r.shot} alt={`${r.who}: a nori screen`} sizes="(max-width: 880px) 100vw, 480px" tag={false} />
                <span className="nx-label">{r.who}</span>
                <h3>{r.line}</h3>
                <ul className="nv-plain">
                  {r.points.map((p) => (
                    <li key={p}>{p}</li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <Closing title="Not sure nori fits?" text="Tell us what you sell and how many shops you run. We will say so plainly." />
    </Shell>
  );
}
