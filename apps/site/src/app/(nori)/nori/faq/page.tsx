import { NORI_FAQ, NoriFaq } from "@/features/nori/nori-page";
import { noriMetadata } from "@/features/nori/meta";
import { JsonLd, breadcrumbs, faqPage } from "@/lib/seo";

export const metadata = noriMetadata({
  path: "/faq",
  title: "nori FAQ: tills, POS connectors, Urdu, branding and plans",
  description:
    "Short answers about nori: what it is, who it is for, how your numbers get in, POS connectors, Urdu, your own brand and domain, and plans.",
});

export default function Page() {
  return (
    <>
      <JsonLd
        data={breadcrumbs([
          { name: "Workzap", path: "/" },
          { name: "nori", path: "/nori" },
          { name: "FAQ", path: "/nori/faq" },
        ])}
      />
      <JsonLd data={faqPage(NORI_FAQ)} />
      <NoriFaq />
    </>
  );
}
