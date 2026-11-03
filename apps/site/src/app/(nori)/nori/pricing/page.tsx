import { NoriPricing } from "@/features/nori/nori-page";
import { noriMetadata } from "@/features/nori/meta";
import { JsonLd, breadcrumbs } from "@/lib/seo";

export const metadata = noriMetadata({
  path: "/pricing",
  title: "nori pricing: one product, one monthly fee, your own brand",
  description:
    "nori is one product with every module and one monthly service fee. Rebrand it, run it on your own domain, and we build connectors for your POS.",
});

export default function Page() {
  return (
    <>
      <JsonLd
        data={breadcrumbs([
          { name: "Workzap", path: "/" },
          { name: "nori", path: "/nori" },
          { name: "Pricing", path: "/nori/pricing" },
        ])}
      />
      <NoriPricing />
    </>
  );
}
