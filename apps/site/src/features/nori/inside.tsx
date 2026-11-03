import { Closing, PageHead, Shell, Shot } from "./chrome";
import { Badge, Icon, type IconName } from "./icons";

interface Group {
  id: string;
  icon: IconName;
  title: string;
  line: string;
  shot: string;
  alt: string;
  modules: { name: string; benefit: string }[];
}

// 24 modules in the product's own seven headings (six groups of work plus "More").
const GROUPS: Group[] = [
  {
    id: "stores",
    icon: "store",
    title: "Stores",
    line: "Every shop on a phone. Head office sees all of them.",
    shot: "store-walk-zoom",
    alt: "Store Walk: a daily photo checklist, with an Urdu switch",
    modules: [
      { name: "Outlets", benefit: "Every shop’s sales against target." },
      { name: "Shop Cash", benefit: "Cash counted, banked and written down." },
      { name: "Returns & Discounts", benefit: "See where discounts leave the shop." },
      { name: "Demands", benefit: "Shops ask, the warehouse answers." },
      { name: "Store Walk", benefit: "A photo walk in every shop, every day." },
      { name: "Store Visits", benefit: "Area managers visit, and you can see it." },
      { name: "Complaints", benefit: "Each complaint worked to an end." },
    ],
  },
  {
    id: "stock",
    icon: "box",
    title: "Stock & Planning",
    line: "Know what to buy, move and clear.",
    shot: "planning-overview",
    alt: "Planning: where the stock money is and what to do first",
    modules: [
      { name: "Products & Stock", benefit: "Find any item in any shop." },
      { name: "Stock Audit", benefit: "Daily counts, with photo proof of differences." },
      { name: "Planning", benefit: "Restock, move or clear: what first." },
      { name: "E-commerce", benefit: "Online orders next to the shops." },
    ],
  },
  {
    id: "finance",
    icon: "coins",
    title: "Finance",
    line: "Read the money without waiting for a pack.",
    shot: "finance-today",
    alt: "Finance: profit, cash and what is owed on one screen",
    modules: [
      { name: "Finance", benefit: "Profit, cash and what is owed." },
      { name: "Rewards", benefit: "Commission worked out from sales, by your rules." },
    ],
  },
  {
    id: "people",
    icon: "people",
    title: "People",
    line: "Work, requests and staff records in one place.",
    shot: "approvals",
    alt: "Approvals: every yes or no on record",
    modules: [
      { name: "HR", benefit: "Staff, leave and payroll." },
      { name: "Tasks", benefit: "Give a job, see when it is done." },
      { name: "Approvals", benefit: "Every yes or no on record." },
    ],
  },
  {
    id: "customers",
    icon: "megaphone",
    title: "Customers & Marketing",
    line: "Know who buys, and what your marketing earns.",
    shot: "customers",
    alt: "Customers: find a customer by phone number",
    modules: [
      { name: "Customers & Loyalty", benefit: "Know buyers by phone, message the right ones." },
      { name: "Marketing", benefit: "See what your ad spend earns." },
    ],
  },
  {
    id: "oversight",
    icon: "eye",
    title: "Oversight",
    line: "What needs the owner today.",
    shot: "consultant-view",
    alt: "Consultant view: operations only, never sales or profit",
    modules: [
      { name: "War Room", benefit: "One page of what needs you today." },
      { name: "Consultant view", benefit: "Auditors see operations, never money." },
      { name: "Policies & SOPs", benefit: "Every written rule in one place." },
      { name: "AI Assistant", benefit: "Ask about your own figures. It answers only from data you can see." },
    ],
  },
  {
    id: "more",
    icon: "plus",
    title: "More",
    line: "Two extras.",
    shot: "sales-crm",
    alt: "Sales CRM: a deal pipeline board",
    modules: [
      { name: "Owner’s WhatsApp assistant", benefit: "Tell it what to chase. You approve the replies." },
      { name: "Sales CRM", benefit: "Leads and deals on one board." },
    ],
  },
];

export function NoriInside() {
  return (
    <Shell current="/nori/whats-inside">
      <PageHead
        label="What’s inside"
        title="What is inside nori."
        lead="24 modules in six groups, plus a few extras. All are included."
      />
      <div className="nv-jump">
        <div className="nx-wrap">
          <nav aria-label="Jump to a group">
            {GROUPS.map((g) => (
              <a key={g.id} href={`#${g.id}`}>
                <Icon name={g.icon} size={18} />
                {g.title}
              </a>
            ))}
          </nav>
        </div>
      </div>
      {GROUPS.map((g, i) => (
        <section
          key={g.id}
          id={g.id}
          aria-labelledby={`${g.id}-h`}
          className={`nx-section nv-group${i % 2 ? " nx-white" : ""}`}
        >
          <div className="nx-wrap nv-group-grid">
            <div className="nv-group-head">
              <Badge name={g.icon} size={28} />
              <h2 id={`${g.id}-h`}>{g.title}</h2>
              <p className="nx-lead">{g.line}</p>
              <span className="nv-count">
                {g.modules.length} {g.modules.length === 1 ? "module" : "modules"}
              </span>
            </div>
            <div className="nv-group-body">
              <div className="nv-stagebg">
                <Shot name={g.shot} alt={g.alt} sizes="(max-width: 880px) 100vw, 600px" />
              </div>
              <ul className="nv-modules">
                {g.modules.map((m) => (
                  <li key={m.name}>
                    <strong>{m.name}</strong>
                    <span>{m.benefit}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </section>
      ))}
      <section className="nx-section">
        <div className="nx-wrap">
          <div className="nv-soon">
            <Badge name="eye" size={24} />
            <div>
              <h3>Coming soon: Vision (CCTV)</h3>
              <p>Footfall and queue times from your existing cameras. Not available yet.</p>
            </div>
          </div>
        </div>
      </section>
      <Closing />
    </Shell>
  );
}
