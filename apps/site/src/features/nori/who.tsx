import { Closing, Head, PageHead, Shell, Shot } from "./chrome";
import { Badge, Icon, type IconName } from "./icons";

const BEST: { t: string; l: string; icon: IconName }[] = [
  { t: "Clothing and fashion chains", l: "Styles, sizes, seasons and many shops. Where nori was shaped.", icon: "shirt" },
  { t: "Footwear", l: "Sizes and styles spread across shops.", icon: "shoe" },
  { t: "Bags and accessories", l: "Fast-moving items, shop by shop.", icon: "bag" },
  { t: "Kids’ wear and home textiles", l: "Same pattern: many styles, many shops.", icon: "kids" },
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

const ROLES: { who: string; line: string; points: string[]; shot: string; icon: IconName }[] = [
  {
    who: "Owner",
    line: "One page each morning.",
    points: ["Which shops are behind", "What does not tie", "What waits for your yes"],
    shot: "war-room-top",
    icon: "user",
  },
  {
    who: "Head of operations",
    line: "Proof the daily jobs were done.",
    points: ["Store walks with photos", "Daily stock counts", "Stock sent, never received"],
    shot: "store-walk-zoom",
    icon: "clipboard",
  },
  {
    who: "Head of finance",
    line: "Cash and margin that tie.",
    points: ["Drawer, deposit, bank", "Till discounts by shop", "P&L on one screen"],
    shot: "finance-today",
    icon: "coins",
  },
  {
    who: "Store and area managers",
    line: "Small daily jobs on a phone.",
    points: ["Count the drawer", "Walk the shop", "Ask the warehouse for stock"],
    shot: "stock-audit-zoom",
    icon: "phone",
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
          <Head label="Industries" title="Best for shops that sell by style and size." />
          <ul className="nv-grid4">
            {BEST.map((b) => (
              <li key={b.t} className="nv-tile">
                <Badge name={b.icon} size={28} />
                <h3>{b.t}</h3>
                <p>{b.l}</p>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="nx-section nx-white">
        <div className="nx-wrap nv-fitpair">
          <div className="nv-panel nv-panel-yes">
            <h2>A good fit when</h2>
            <ul className="nv-ticks">
              {GOOD_WHEN.map((g) => (
                <li key={g}>
                  <Icon name="checkCircle" size={22} />
                  {g}
                </li>
              ))}
            </ul>
          </div>
          <div className="nv-panel">
            <h2>Talk to us first if</h2>
            <ul className="nv-ticks nv-ticks-quiet">
              {ASK_FIRST.map((g) => (
                <li key={g}>
                  <Icon name="info" size={22} />
                  {g}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      <section className="nx-section">
        <div className="nx-wrap">
          <Head label="Roles" title="Each person sees the part they answer for." />
          <ul className="nv-roles">
            {ROLES.map((r) => (
              <li key={r.who} className="nv-card">
                <div className="nv-peek nv-peek-16x10">
                  <Shot name={r.shot} alt={`${r.who}: a nori screen`} crop sizes="(max-width: 880px) 100vw, 540px" />
                </div>
                <div className="nv-card-body">
                  <span className="nv-role-tag">
                    <Icon name={r.icon} size={18} />
                    {r.who}
                  </span>
                  <h3>{r.line}</h3>
                  <ul className="nv-points">
                    {r.points.map((p) => (
                      <li key={p}>
                        <Icon name="check" size={16} />
                        {p}
                      </li>
                    ))}
                  </ul>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <Closing title="Not sure nori fits?" text="Tell us what you sell and how many shops you run. We will say so plainly." />
    </Shell>
  );
}
