import { APP, Closing, Head, PageHead, Shell, Shot } from "./chrome";
import { Badge, Icon, type IconName } from "./icons";

const STEPS: { n: string; icon: IconName; title: string; line: string; shot: string; alt: string }[] = [
  {
    n: "1",
    icon: "phone",
    title: "Shops record it",
    line: "Staff count the drawer, walk the shop and count stock on a phone. Photos and location are the proof.",
    shot: "store-walk-zoom",
    alt: "Store Walk on a shop phone",
  },
  {
    n: "2",
    icon: "file",
    title: "Files come in",
    line: "Sales and stock load from CSV, Excel or Google Sheets. Shopify online orders sync if you use it.",
    shot: "stock-find-urdu-zoom",
    alt: "Products and stock import and find",
  },
  {
    n: "3",
    icon: "tie",
    title: "nori checks the numbers",
    line: "Sales against stock. Cash against deposits. Deposits against the bank. PASS or FLAG, with the gap in rupees.",
    shot: "war-room-top",
    alt: "War Room numbers-disagree checks",
  },
  {
    n: "4",
    icon: "page",
    title: "You read one page",
    line: "What needs you today. Assign a task, approve a request. The decision is yours.",
    shot: "approvals",
    alt: "Approvals waiting for the owner",
  },
];

const START = [
  "Sign in and install nori on your phone.",
  "Load your items and stock from a file.",
  "Load your sales from a file.",
  "Invite your team, each with a role.",
  "Do today’s stock count.",
];

const ROLES = [
  ["Owner", "Everything, including billing."],
  ["Admin", "Manages people. Sees all data."],
  ["Member", "Works in the modules switched on for them."],
  ["Viewer", "Reads only."],
];

export function NoriHow() {
  return (
    <Shell current="/nori/how-it-works">
      <PageHead
        label="How it works"
        title="From the shop floor to the owner’s page."
        lead="Four steps. No new till. No new hardware."
      />

      <section className="nx-section">
        <div className="nx-wrap">
          <ol className="nv-flow">
            {STEPS.map((s) => (
              <li key={s.n} className="nv-card">
                <div className="nv-peek nv-peek-16x10">
                  <Shot name={s.shot} alt={s.alt} crop sizes="(max-width: 880px) 100vw, 540px" />
                </div>
                <div className="nv-card-body">
                  <div className="nv-step-top">
                    <Badge name={s.icon} size={24} />
                    <span className="nv-step-n" aria-hidden="true">
                      {s.n}
                    </span>
                  </div>
                  <h2>{s.title}</h2>
                  <p>{s.line}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="nx-section nx-white">
        <div className="nx-wrap nv-two nv-two-center">
          <div>
            <Head label="For your staff" title="Urdu on the shop floor. A phone app, no app store." lead="Shop-floor pages have an Urdu switch. nori installs on a phone like an app. The Help Center understands Roman Urdu." />
          </div>
          <div className="nv-stagebg nv-stagebg-phone">
            <Shot name="store-walk-zoom" alt="Store Walk with the Urdu switch on" sizes="(max-width: 880px) 100vw, 460px" />
          </div>
        </div>
      </section>

      <section className="nx-section">
        <div className="nx-wrap nv-two">
          <div className="nv-panel">
            <h2>Getting started</h2>
            <ol className="nv-checklist">
              {START.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ol>
            <p className="nv-more">
              <a className="nv-link" href={APP}>
                Sign in
                <Icon name="arrow" size={16} />
              </a>
            </p>
          </div>
          <div className="nv-panel">
            <h2>Who sees what</h2>
            <dl className="nv-roles-list">
              {ROLES.map(([r, d]) => (
                <div key={r}>
                  <dt>{r}</dt>
                  <dd>{d}</dd>
                </div>
              ))}
            </dl>
          </div>
        </div>
      </section>

      <Closing />
    </Shell>
  );
}
