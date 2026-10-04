import { NoriHow } from "@/features/nori/nori-page";
import { noriMetadata } from "@/features/nori/meta";
import { JsonLd, breadcrumbs } from "@/lib/seo";

export const metadata = noriMetadata({
  path: "/how-it-works",
  title: "How nori works: from your data to a decision",
  description:
    "Connect your data once. nori reads every shop, item and day, and gives you a short read each morning with the one thing worth looking at.",
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
