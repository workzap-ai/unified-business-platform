import { NoriInside } from "@/features/nori/nori-page";
import { noriMetadata } from "@/features/nori/meta";
import { JsonLd, breadcrumbs } from "@/lib/seo";

export const metadata = noriMetadata({
  path: "/whats-inside",
  title: "What’s inside nori: shops, money, stock and more",
  description:
    "Shops, money, stock, online, marketing and people. Each area of nori comes with the numbers, the reasons and the next step.",
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
