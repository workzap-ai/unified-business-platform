import Image from "next/image";

// Official logos of software nori works beside (files in public/nori-logos, sources in
// SOURCES.md there). Shown as "works beside", never as a partner or certification.
const LOGOS = {
  tally: { name: "TallyPrime", file: "tally.svg", w: 114, h: 26, show: 24 },
  quickbooks: { name: "QuickBooks", file: "quickbooks.svg", w: 111, h: 30, show: 28 },
  zoho: { name: "Zoho Books", file: "zoho-books.svg", w: 860, h: 296, show: 32 },
  odoo: { name: "Odoo", file: "odoo.svg", w: 621, h: 196, show: 28 },
  excel: { name: "Microsoft Excel", file: "excel.svg", w: 48, h: 48, show: 28, label: true },
  sheets: { name: "Google Sheets", file: "google-sheets.svg", w: 192, h: 192, show: 28, label: true },
  shopify: { name: "Shopify", file: "shopify.svg", w: 304, h: 87, show: 28 },
} as const;

export type LogoId = keyof typeof LOGOS;

const STRIP: LogoId[] = ["tally", "quickbooks", "zoho", "odoo", "excel", "sheets", "shopify"];

// One logo in a white tile. Icon-only logos carry their product name beside them.
export function LogoChip({ id }: { id: LogoId }) {
  const l = LOGOS[id];
  const label = "label" in l && l.label;
  return (
    <span className="nv-logo">
      <Image
        src={`/nori-logos/${l.file}`}
        alt={label ? "" : l.name}
        width={Math.round((l.w / l.h) * l.show)}
        height={l.show}
        unoptimized
      />
      {label ? <span>{l.name}</span> : null}
    </span>
  );
}

export function LogoNote() {
  return (
    <p className="nv-tiny nv-logos-note">
      Logos belong to their owners. nori works beside this software and is not
      affiliated with or endorsed by these companies.
    </p>
  );
}

export function Logos() {
  return (
    <div>
      <ul className="nv-logos" aria-label="Software nori works beside">
        {STRIP.map((id) => (
          <li key={id}>
            <LogoChip id={id} />
          </li>
        ))}
      </ul>
      <LogoNote />
    </div>
  );
}
