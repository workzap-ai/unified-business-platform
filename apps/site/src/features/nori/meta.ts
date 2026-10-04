import type { Metadata } from "next";
import { pageMetadata } from "@/lib/seo";

export function noriMetadata({
  path,
  title,
  description,
}: {
  path: string;
  title: string;
  description: string;
}): Metadata {
  return pageMetadata({
    path: `/nori${path}`,
    title,
    description,
    siteName: "nori by Workzap",
    brand: "nori",
  });
}
