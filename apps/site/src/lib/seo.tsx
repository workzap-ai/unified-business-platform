import type { Metadata } from "next";

// Shared search and AI-answer markup for every Workzap page (home, nori, pi).
// Rule: only mark up what the page itself says. No prices, ratings, reviews, addresses
// or social profiles are invented here.

export const SITE_URL = "https://workzap.ai";

// Previews and staging are never indexed; only a production deploy is.
export const IS_PRODUCTION = process.env.VERCEL_ENV === "production";

export const ORG_ID = `${SITE_URL}/#organization`;
export const WEBSITE_ID = `${SITE_URL}/#website`;

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

export const ORGANIZATION = {
  "@type": "Organization",
  "@id": ORG_ID,
  name: "Workzap",
  url: SITE_URL,
  logo: `${SITE_URL}/workzap-brand/workzap-logo.svg`,
  description:
    "Workzap makes nori, a daily read for the shop, and pi, a WhatsApp agent.",
  contactPoint: {
    "@type": "ContactPoint",
    contactType: "customer support",
    telephone: "+1-201-471-3467",
    url: "https://wa.me/12014713467?text=Hi%20pi",
    availableLanguage: "English",
  },
};

export const WEBSITE = {
  "@type": "WebSite",
  "@id": WEBSITE_ID,
  url: SITE_URL,
  name: "Workzap",
  inLanguage: "en",
  publisher: { "@id": ORG_ID },
};

export function breadcrumbs(items: { name: string; path: string }[]) {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: items.map((it, i) => ({
      "@type": "ListItem",
      position: i + 1,
      name: it.name,
      item: `${SITE_URL}${it.path}`,
    })),
  };
}

export function faqPage(items: { question: string; answer: string }[]) {
  return {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: items.map((q) => ({
      "@type": "Question",
      name: q.question,
      acceptedAnswer: { "@type": "Answer", text: q.answer },
    })),
  };
}

// One metadata shape for every page: absolute title, description, canonical, Open Graph
// and the Twitter card. The share image comes from the section's opengraph-image file.
export function pageMetadata({
  path,
  title,
  description,
  siteName,
  brand,
}: {
  path: string;
  title: string;
  description: string;
  siteName: string;
  brand: "workzap" | "nori" | "pi";
}): Metadata {
  const image = {
    url: `/og/${brand}`,
    width: 1200,
    height: 630,
    alt: siteName,
  };
  return {
    metadataBase: new URL(SITE_URL),
    title: { absolute: title },
    description,
    alternates: { canonical: path },
    robots: IS_PRODUCTION ? undefined : { index: false, follow: false },
    openGraph: {
      title,
      description,
      url: path,
      siteName,
      type: "website",
      locale: "en_US",
      images: [image],
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
      images: [image.url],
    },
  };
}
