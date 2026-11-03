import { APP, Closing, PageHead, Shell, Shot } from "./chrome";

const STEPS = [
  {
    n: "1",
    title: "Shops record it",
    line: "Staff count the drawer, walk the shop and count stock on a phone. Photos and location are the proof.",
    shot: "store-walk-zoom",
    alt: "Store Walk on a shop phone",
  },
  {
    n: "2",
    title: "Files come in",
    line: "Sales and stock load from CSV, Excel or Google Sheets. Shopify online orders sync if you use it.",
    shot: "stock-find-urdu-zoom",
    alt: "Products and stock import and find",
  },
  {
    n: "3",
    title: "nori checks the numbers",
    line: "Sales against stock. Cash against deposits. Deposits against the bank. PASS or FLAG, with the gap in rupees.",
    shot: "war-room-top",
    alt: "War Room numbers-disagree checks",
  },
  {
    n: "4",
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
              <li key={s.n}>
                <div>
                  <span className="nv-step-n" aria-hidden="true">
                    {s.n}
                  </span>
                  <h2>{s.title}</h2>
                  <p>{s.line}</p>
                </div>
                <Shot name={s.shot} alt={s.alt} sizes="(max-width: 880px) 100vw, 520px" />
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="nx-section nx-white">
        <div className="nx-wrap nv-two">
          <div>
            <span className="nx-label">For your staff</span>
            <h2>Urdu on the shop floor. A phone app, no app store.</h2>
            <p className="nx-lead">
              Shop-floor pages have an Urdu switch. nori installs on a phone like an
              app. The Help Center understands Roman Urdu.
            </p>
          </div>
          <Shot name="store-walk-zoom" alt="Store Walk with the Urdu switch on" sizes="(max-width: 880px) 100vw, 480px" />
        </div>
      </section>

      <section className="nx-section">
        <div className="nx-wrap nv-two">
          <div>
            <span className="nx-label">Getting started</span>
            <ol className="nv-ticks nv-ordered">
              {START.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ol>
            <p className="nv-more">
              <a href={APP}>Sign in →</a>
            </p>
          </div>
          <div>
            <span className="nx-label">Who sees what</span>
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
