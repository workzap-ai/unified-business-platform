import { NoriPricing } from "@/features/nori/nori-page";
import { noriMetadata } from "@/features/nori/meta";
import { JsonLd, breadcrumbs } from "@/lib/seo";

export const metadata = noriMetadata({
  path: "/pricing",
  title: "nori plans: Starter, Growth and Enterprise",
  description:
    "nori has three plans: Starter for one store, Growth for up to 10 outlets, Enterprise for chains. Every module is included. Rebrand it as your own.",
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
