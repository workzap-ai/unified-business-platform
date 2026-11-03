import Link from "next/link";
import { Closing, PageHead, Shell, TALK } from "./chrome";

// Named products appear only with narrow, dated facts or plain descriptions. Nothing
// here says a named product cannot do something. Checked 3 Nov 2026.
const ROWS = [
  {
    kind: "Your till or POS",
    names: "Any till, Shopify",
    does: "Takes the sale.",
    nori: "Keeps ringing sales. nori reads the sales files.",
  },
  {
    kind: "Accounting software",
    names: "Tally, QuickBooks, Zoho Books",
    does: "Keeps the books and tax records.",
    nori: "Your accountant keeps the books. nori’s finance pages are for you to read.",
  },
  {
    kind: "An ERP",
    names: "Odoo, SAP Business One, Dynamics 365 Business Central, NetSuite",
    does: "Records sales, purchases, accounts and stock in one system.",
    nori: "Keep it. nori adds the daily shop checks and the owner’s page.",
  },
  {
    kind: "A warehouse system",
    names: "",
    does: "Receives, stores and dispatches stock.",
    nori: "Stays as it is. nori carries the shops’ demands and receipts.",
  },
  {
    kind: "Excel and WhatsApp",
    names: "",
    does: "Your own way to chase the shops.",
    nori: "Keep your sheets. Shops’ updates get one place to land.",
  },
];

const ADDS = [
  "A morning list of what needs you.",
  "Proof the shops did their daily jobs.",
  "Figures that do not tie, with the gap.",
  "Requests that end in a recorded yes or no.",
  "Stock planning: restock, move, clear.",
  "Urdu for the shop floor, and a phone app.",
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
          <div className="nx-head">
            <span className="nx-label">What each kind is for</span>
            <h2>Each tool does its own job.</h2>
          </div>
          <div className="nv-table-wrap">
            <table className="nv-table">
              <caption className="nx-sr">
                What each kind of software is for, and how nori sits beside it
              </caption>
              <thead>
                <tr>
                  <th scope="col">Software</th>
                  <th scope="col">What it is for</th>
                  <th scope="col">With nori</th>
                </tr>
              </thead>
              <tbody>
                {ROWS.map((r) => (
                  <tr key={r.kind}>
                    <th scope="row">
                      {r.kind}
                      {r.names ? <span>{r.names}</span> : null}
                    </th>
                    <td>{r.does}</td>
                    <td>{r.nori}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="nv-tiny">
            nori works beside your till, your accounts and your warehouse system, and
            does not replace them. It is not an ERP. Product names belong to their
            owners.
          </p>
        </div>
      </section>

      <section className="nx-section nx-white">
        <div className="nx-wrap nv-two">
          <div>
            <span className="nx-label">What nori adds</span>
            <ul className="nv-ticks">
              {ADDS.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          </div>
          <div>
            <span className="nx-label">How figures reach nori</span>
            <ul className="nv-plain">
              <li>Sales and stock files: CSV, Excel, Google Sheets.</li>
              <li>Shopify sync for online orders.</li>
              <li>Cash, counts and walks recorded by staff.</li>
              <li>
                <strong>A connector for your POS?</strong> Ask us. We build
                connectors on request.
              </li>
            </ul>
          </div>
        </div>
      </section>

      <section className="nx-section">
        <div className="nx-wrap nv-two">
          <div>
            <span className="nx-label">Do I still need…</span>
            <ul className="nv-plain">
              <li>
                <strong>A till?</strong> Yes. nori does not take payments.
              </li>
              <li>
                <strong>An accountant?</strong> Yes. nori is not your books of record.
              </li>
              <li>
                <strong>Odoo or another ERP?</strong> Not to use nori. If you have
                one, keep it. Odoo lists 77 partners in Pakistan on its own site
                (seen 3 Nov 2026).
              </li>
            </ul>
          </div>
          <div>
            <span className="nx-label">A note on FBR</span>
            <p className="nv-plainp">
              Some retailers need to connect their till to FBR. Ask your tax adviser if
              that is you. nori is not a till and is not connected to FBR. Check the
              current rules at fbr.gov.pk.
            </p>
          </div>
        </div>
        <div className="nx-wrap">
          <p className="nv-more">
            <Link href={TALK}>Ask us how it fits yours →</Link>
          </p>
        </div>
      </section>

      <Closing />
    </Shell>
  );
}
