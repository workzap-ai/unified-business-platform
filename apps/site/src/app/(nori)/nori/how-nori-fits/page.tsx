import { NoriFits } from "@/features/nori/nori-page";
import { noriMetadata } from "@/features/nori/meta";
import { JsonLd, breadcrumbs } from "@/lib/seo";

export const metadata = noriMetadata({
  path: "/how-nori-fits",
  title: "How nori fits with Odoo, Tally, QuickBooks and your till",
  description:
    "What your till, accounting package, ERP and spreadsheets each do, what nori adds beside them, and when you still need each one.",
});

export default function Page() {
  return (
    <>
      <JsonLd
        data={breadcrumbs([
          { name: "Workzap", path: "/" },
          { name: "nori", path: "/nori" },
          { name: "How nori fits", path: "/nori/how-nori-fits" },
        ])}
      />
      <NoriFits />
    </>
  );
}
