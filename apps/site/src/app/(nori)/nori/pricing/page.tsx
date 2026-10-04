import { NoriPricing } from "@/features/nori/nori-page";
import { noriMetadata } from "@/features/nori/meta";
import { JsonLd, breadcrumbs } from "@/lib/seo";

export const metadata = noriMetadata({
  path: "/pricing",
  title: "nori plans: Starter, Growth and Enterprise",
  description:
    "A one-time setup, then a simple monthly plan. Every plan has everything. You choose the size and the support.",
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
