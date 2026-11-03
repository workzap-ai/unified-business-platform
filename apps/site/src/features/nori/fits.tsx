import Link from "next/link";
import { Closing, Head, PageHead, Shell, Shot, TALK } from "./chrome";
import { Badge, Icon, type IconName } from "./icons";
import { LogoChip, LogoNote, type LogoId } from "./logos";

// Named products appear only with narrow, dated facts or plain descriptions. Nothing
// here says a named product cannot do something. Checked 3 Nov 2026.
const RECORDS: {
  icon: IconName;
  kind: string;
  job: string;
  logos?: LogoId[];
  names?: string[];
}[] = [
  { icon: "till", kind: "Till or POS", job: "Takes the sale", names: ["Any till"], logos: ["shopify"] },
  { icon: "book", kind: "Accounting", job: "Keeps the books", logos: ["tally", "quickbooks", "zoho"] },
  {
    icon: "grid",
    kind: "ERP",
    job: "Records stock and orders",
    logos: ["odoo"],
    names: ["SAP Business One", "Dynamics 365 Business Central", "NetSuite"],
  },
  { icon: "warehouse", kind: "Warehouse system", job: "Receives and ships stock" },
  {
    icon: "chat",
    kind: "Excel and WhatsApp",
    job: "Your own way to chase shops",
    logos: ["excel", "sheets"],
    names: ["WhatsApp"],
  },
];

const NORI_DOES = [
  "Daily shop checks, with photos.",
  "Figures that do not tie, with the gap.",
  "Stock to restock, move or clear.",
  "Requests with a recorded yes or no.",
  "Urdu on the shop floor, and a phone app.",
];

const KEEP = ["Keep your till.", "Keep your accountant.", "Keep your ERP."];

const REACH: { icon: IconName; text: React.ReactNode }[] = [
  { icon: "file", text: "Sales and stock files: CSV, Excel, Google Sheets." },
  { icon: "swap", text: "Shopify sync for online orders." },
  { icon: "phone", text: "Cash, counts and walks recorded by staff." },
  {
    icon: "plug",
    text: (
      <>
        <strong>A connector for your POS?</strong> Ask us. We build connectors on
        request.
      </>
    ),
  },
];

export function NoriFits() {
  return (
    <Shell current="/nori/how-nori-fits">
      <PageHead
        label="How nori fits"
        title="How nori fits with the software you already use."
        lead="Keep your till and your accounts. nori sits beside them."
      />

      <section className="nx-section">
        <div className="nx-wrap">
          <Head title="Your software records. nori reads it and checks the shops." />
          <div className="nv-fitmap">
            <div className="nv-panel nv-records">
              <h3>Your software records the business</h3>
              <ul>
                {RECORDS.map((r) => (
                  <li key={r.kind}>
                    <Badge name={r.icon} size={22} />
                    <div className="nv-rec-text">
                      <strong>{r.kind}</strong>
                      <span>{r.job}</span>
                    </div>
                    <div className="nv-rec-names">
                      {r.logos?.map((id) => <LogoChip key={id} id={id} />)}
                      {r.names?.map((n) => (
                        <span key={n} className="nv-name">
                          {n}
                        </span>
                      ))}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
            <div className="nv-reads" aria-hidden="true">
              <span>
                reads
                <Icon name="arrow" size={18} />
              </span>
            </div>
            <div className="nv-panel nv-nori">
              <h3>nori checks the shops and shows you one page</h3>
              <ul className="nv-ticks">
                {NORI_DOES.map((d) => (
                  <li key={d}>
                    <Icon name="checkCircle" size={22} />
                    {d}
                  </li>
                ))}
              </ul>
              <div className="nv-peek nv-peek-wide">
                <Shot name="war-room-top" alt="The War Room: one page of what needs the owner today" crop sizes="(max-width: 880px) 100vw, 560px" />
              </div>
            </div>
          </div>
          <ul className="nv-keep" aria-label="You keep what you have">
            {KEEP.map((k) => (
              <li key={k}>
                <Icon name="check" size={18} />
                {k}
              </li>
            ))}
          </ul>
          <p className="nv-tiny">
            nori works beside your till, your accounts and your warehouse system, and
            does not replace them. It is not an ERP. Product names belong to their
            owners.
          </p>
          <LogoNote />
        </div>
      </section>

      <section className="nx-section nx-white">
        <div className="nx-wrap nv-two">
          <div className="nv-panel">
            <h2>How figures reach nori</h2>
            <ul className="nv-rows">
              {REACH.map((r, i) => (
                <li key={i}>
                  <Badge name={r.icon} size={20} />
                  <span>{r.text}</span>
                </li>
              ))}
            </ul>
          </div>
          <div className="nv-panel">
            <h2>Do I still need…</h2>
            <ul className="nv-qa">
              <li>
                <strong>A till?</strong>
                <span>Yes. nori does not take payments.</span>
              </li>
              <li>
                <strong>An accountant?</strong>
                <span>Yes. nori is not your books of record.</span>
              </li>
              <li>
                <strong>Odoo or another ERP?</strong>
                <span>
                  Not to use nori. If you have one, keep it. Odoo lists 77 partners in
                  Pakistan on its own site (seen 3 Nov 2026).
                </span>
              </li>
            </ul>
          </div>
        </div>
        <div className="nx-wrap">
          <div className="nv-note-row">
            <p className="nv-plainp">
              <strong>A note on FBR.</strong> Some retailers need to connect their till
              to FBR. Ask your tax adviser if that is you. nori is not a till and is not
              connected to FBR. Check the current rules at fbr.gov.pk.
            </p>
            <Link className="nv-link" href={TALK}>
              Ask us how it fits yours
              <Icon name="arrow" size={16} />
            </Link>
          </div>
        </div>
      </section>

      <Closing />
    </Shell>
  );
}
