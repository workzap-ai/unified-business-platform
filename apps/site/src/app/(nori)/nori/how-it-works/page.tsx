import { NoriHow } from "@/features/nori/nori-page";
import { noriMetadata } from "@/features/nori/meta";
import { JsonLd, breadcrumbs } from "@/lib/seo";

export const metadata = noriMetadata({
  path: "/how-it-works",
  title: "How nori works: from the shop floor to the owner’s page",
  description:
    "Staff record cash, counts and store walks on a phone. Sales load from files. nori checks the figures and the owner reads one page.",
});

export default function Page() {
  return (
    <>
      <JsonLd
        data={breadcrumbs([
          { name: "Workzap", path: "/" },
          { name: "nori", path: "/nori" },
          { name: "How it works", path: "/nori/how-it-works" },
        ])}
      />
      <NoriHow />
    </>
  );
}
