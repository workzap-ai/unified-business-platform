import type { Metadata } from "next";
import { IS_PRODUCTION, PI } from "./config";

export function piMetadata({
  path,
  title,
  description,
}: {
  path: string;
  title: string;
  description: string;
}): Metadata {
  const url = `${PI.base}${path}`;
  return {
    metadataBase: new URL(PI.siteUrl),
    title: { absolute: title },
    description,
    alternates: { canonical: url },
    // Previews and staging must never be indexed; only a production deploy is.
    robots: IS_PRODUCTION ? undefined : { index: false, follow: false },
    openGraph: {
      title,
      description,
      url,
      siteName: "pi by Workzap",
      type: "website",
    },
  };
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
  "@type": "Organization",
  name: "Workzap",
  url: PI.siteUrl,
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
