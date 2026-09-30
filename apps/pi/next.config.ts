import type { NextConfig } from "next";

// The Pi app is its own origin. Browsers call same-origin /api/v1/pi-app, which is
// proxied to the shared API, so Pi's HttpOnly session cookie stays first-party and is
// never sent to the Owner OS origin. Only Pi app routes and public webhooks are proxied.
const apiTarget = (
  process.env.API_PROXY_TARGET ?? "http://127.0.0.1:8000"
).replace(/\/$/, "");

const nextConfig: NextConfig = {
  distDir: process.env.NEXT_DIST_DIR || ".next",
  output: "standalone",
  poweredByHeader: false,
  async rewrites() {
    return [
      {
        source: "/api/v1/pi-app/:path*",
        destination: `${apiTarget}/api/v1/pi-app/:path*`,
      },
    ];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-Frame-Options", value: "DENY" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(self), geolocation=()",
          },
        ],
      },
    ];
  },
};
export default nextConfig;
