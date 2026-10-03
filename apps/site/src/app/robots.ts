import type { MetadataRoute } from "next";
import { IS_PRODUCTION, PI } from "@/features/pi/config";

// Previews and staging are never indexed; only a production deploy is.
export default function robots(): MetadataRoute.Robots {
  if (!IS_PRODUCTION) return { rules: { userAgent: "*", disallow: "/" } };
  return {
    rules: { userAgent: "*", allow: "/" },
    sitemap: `${PI.siteUrl}/sitemap.xml`,
  };
}
