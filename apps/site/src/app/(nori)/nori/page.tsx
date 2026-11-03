import { NoriHome } from "@/features/nori/nori-page";
import { noriMetadata } from "@/features/nori/meta";
import { JsonLd, ORG_ID, SITE_URL, breadcrumbs } from "@/lib/seo";

const DEFINITION =
  "nori is a retail operations app for shops and chains. Shop staff record cash, stock counts and store walks on their phones, with photos as proof, and the owner sees one page of what needs them today.";

export const metadata = noriMetadata({
  path: "",
  title: "nori by Workzap: see what is going wrong in your shops",
  description:
    "nori shows owners of shops and chains which outlets are behind, where cash does not tie and where stock is stuck. Built for clothing and fashion retail.",
});

export default function Page() {
  return (
    <>
      <JsonLd
        data={{
          "@context": "https://schema.org",
          "@type": "SoftwareApplication",
          "@id": `${SITE_URL}/nori#software`,
          name: "nori",
          alternateName: "nori by Workzap",
          url: `${SITE_URL}/nori`,
          description: DEFINITION,
          applicationCategory: "BusinessApplication",
          operatingSystem: "Web",
          inLanguage: ["en", "ur"],
          publisher: { "@id": ORG_ID },
          sameAs: ["https://www.wikidata.org/wiki/Q141644274"],
        }}
      />
      <JsonLd
        data={breadcrumbs([
          { name: "Workzap", path: "/" },
          { name: "nori", path: "/nori" },
        ])}
      />
      <NoriHome />
    </>
  );
}
