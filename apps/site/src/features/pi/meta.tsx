import type { Metadata } from "next";
import { ORGANIZATION, WEBSITE, pageMetadata } from "@/lib/seo";
import { PI } from "./config";

export function piMetadata({
  path,
  title,
  description,
}: {
  path: string;
  title: string;
  description: string;
}): Metadata {
  return pageMetadata({
    path: `${PI.base}${path}`,
    title,
    description,
    siteName: "pi by Workzap",
    brand: "pi",
  });
}

export function JsonLd({ data }: { data: unknown }) {
  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{
        __html: JSON.stringify(data).replace(/</g, "\\u003c"),
      }}
    />
  );
}

export const ORGANIZATION_LD = {
  "@context": "https://schema.org",
  "@graph": [ORGANIZATION, WEBSITE],
};

export function Breadcrumbs({ path, name }: { path: string; name?: string }) {
  const items = [
    { name: "Workzap", url: PI.siteUrl },
    { name: "pi", url: `${PI.siteUrl}${PI.base}` },
  ];
  if (name) items.push({ name, url: `${PI.siteUrl}${PI.base}${path}` });
  return (
    <JsonLd
      data={{
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        itemListElement: items.map((it, i) => ({
          "@type": "ListItem",
          position: i + 1,
          name: it.name,
          item: it.url,
        })),
      }}
    />
  );
}
