import { NoriInside } from "@/features/nori/nori-page";
import { noriMetadata } from "@/features/nori/meta";
import { JsonLd, breadcrumbs } from "@/lib/seo";

export const metadata = noriMetadata({
  path: "/whats-inside",
  title: "What is inside nori: 24 modules for shops and chains",
  description:
    "The 24 nori modules in plain words: shop cash, store walks, stock audit, planning, finance, people, customers and the owner’s War Room.",
});

export default function Page() {
  return (
    <>
      <JsonLd
        data={breadcrumbs([
          { name: "Workzap", path: "/" },
          { name: "nori", path: "/nori" },
          { name: "What’s inside", path: "/nori/whats-inside" },
        ])}
      />
      <NoriInside />
    </>
  );
}
