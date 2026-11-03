import { NoriVideos } from "@/features/nori/nori-page";
import { noriMetadata } from "@/features/nori/meta";
import { FILMS } from "@/features/nori/videos-data";
import { JsonLd, SITE_URL, breadcrumbs } from "@/lib/seo";

export const metadata = noriMetadata({
  path: "/videos",
  title: "nori videos: a morning with nori, stock and shop checks",
  description:
    "Short silent films recorded from the real nori screens: what an owner sees in the morning, where stock is stuck, and how shops do their checks.",
});

export default function Page() {
  return (
    <>
      <JsonLd
        data={breadcrumbs([
          { name: "Workzap", path: "/" },
          { name: "nori", path: "/nori" },
          { name: "Videos", path: "/nori/videos" },
        ])}
      />
      {FILMS.map((f) => (
        <JsonLd
          key={f.slug}
          data={{
            "@context": "https://schema.org",
            "@type": "VideoObject",
            name: f.title,
            description: f.line,
            thumbnailUrl: `${SITE_URL}${f.poster}`,
            contentUrl: `${SITE_URL}${f.file}`,
            uploadDate: "2026-11-03",
            duration: `PT${f.seconds}S`,
            ...(f.transcript.length ? { transcript: f.transcript.join(" ") } : {}),
          }}
        />
      ))}
      <NoriVideos />
    </>
  );
}
