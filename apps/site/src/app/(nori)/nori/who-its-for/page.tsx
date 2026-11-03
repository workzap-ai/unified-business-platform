import { NoriWho } from "@/features/nori/nori-page";
import { noriMetadata } from "@/features/nori/meta";
import { JsonLd, breadcrumbs } from "@/lib/seo";

export const metadata = noriMetadata({
  path: "/who-its-for",
  title: "Who nori is for: retail chains that sell by style and size",
  description:
    "nori is built for shops and chains, best for clothing, footwear and fashion retail with two or more shops. See the fit by industry and by role.",
});

export default function Page() {
  return (
    <>
      <JsonLd
        data={breadcrumbs([
          { name: "Workzap", path: "/" },
          { name: "nori", path: "/nori" },
          { name: "Who it’s for", path: "/nori/who-its-for" },
        ])}
      />
      <NoriWho />
    </>
  );
}
