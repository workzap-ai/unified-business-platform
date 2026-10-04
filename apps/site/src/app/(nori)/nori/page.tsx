import { NoriHome } from "@/features/nori/nori-page";
import { noriMetadata } from "@/features/nori/meta";
import { JsonLd, ORG_ID, SITE_URL, breadcrumbs } from "@/lib/seo";

export const metadata = noriMetadata({
  path: "",
  title: "nori by Workzap: the daily read for your shop",
  description:
    "nori reads your shop’s sales and stock and picks out the one thing worth looking at today. A short read each morning, from your own numbers.",
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
          description:
            "nori reads your shop’s sales and stock and picks out the one thing worth looking at today.",
          applicationCategory: "BusinessApplication",
          operatingSystem: "Web",
          inLanguage: "en",
          publisher: { "@id": ORG_ID },
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
