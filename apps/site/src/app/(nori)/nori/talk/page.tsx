import { NoriTalk } from "@/features/nori/nori-page";
import { noriMetadata } from "@/features/nori/meta";
import { JsonLd, ORG_ID, SITE_URL, breadcrumbs } from "@/lib/seo";

export const metadata = noriMetadata({
  path: "/talk",
  title: "Talk to us: book a 30-minute nori meeting or message pi",
  description:
    "Book a 30-minute meeting about nori, pick a day and time, or message pi on WhatsApp. Tell us how many shops you run.",
});

export default function Page() {
  return (
    <>
      <JsonLd
        data={{
          "@context": "https://schema.org",
          "@type": "ContactPage",
          "@id": `${SITE_URL}/nori/talk#page`,
          url: `${SITE_URL}/nori/talk`,
          name: "Talk to the nori team",
          isPartOf: { "@id": ORG_ID },
        }}
      />
      <JsonLd
        data={breadcrumbs([
          { name: "Workzap", path: "/" },
          { name: "nori", path: "/nori" },
          { name: "Talk to us", path: "/nori/talk" },
        ])}
      />
      <NoriTalk />
    </>
  );
}
