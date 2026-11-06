import type { NextConfig } from "next";

// Server-side proxy target for /api/v1 (live data mode). Browsers call same-origin
// /api/v1 so the HttpOnly session cookie is first-party. Evaluated at build time.
const apiTarget = (
  process.env.API_PROXY_TARGET ?? "http://127.0.0.1:8000"
).replace(/\/$/, "");

const nextConfig: NextConfig = {
  // A separate build directory lets test builds run next to a running `next dev`.
  distDir: process.env.NEXT_DIST_DIR || ".next",
  output: "standalone",
  poweredByHeader: false,
  async rewrites() {
    return [
      { source: "/api/v1/:path*", destination: `${apiTarget}/api/v1/:path*` },
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
            value:
              "camera=(self), microphone=(), display-capture=(), geolocation=()",
          },
        ],
      },
      {
        // A meeting link records the visitor's own microphone; the link is the only key, so it is
        // never sent on as a referrer. Listed after the global entry so it wins.
        source: "/join/:path*",
        headers: [
          { key: "Referrer-Policy", value: "no-referrer" },
          {
            key: "Permissions-Policy",
            value:
              "camera=(), microphone=(self), display-capture=(), geolocation=()",
          },
        ],
      },
      {
        // Only the meetings page records audio. Listed last: when two entries set the same
        // header for a path, the later one wins. The browser still asks the person each time.
        source: "/pi/meeting-intel/:path*",
        headers: [
          {
            key: "Permissions-Policy",
            value:
              "camera=(self), microphone=(self), display-capture=(self), geolocation=()",
          },
        ],
      },
    ];
  },
};
export default nextConfig;
