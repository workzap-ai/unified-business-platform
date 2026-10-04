import { NORI_FAQ, NoriFaq } from "@/features/nori/nori-page";
import { noriMetadata } from "@/features/nori/meta";
import { JsonLd, breadcrumbs, faqPage } from "@/lib/seo";

export const metadata = noriMetadata({
  path: "/faq",
  title: "nori FAQ: what it reads, how it connects, what it covers",
  description:
    "Short answers about nori: what it reads, how your data gets in, who decides, which areas it covers and how the plans differ.",
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
