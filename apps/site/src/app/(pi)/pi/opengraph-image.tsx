import { ImageResponse } from "next/og";
import { readFile } from "node:fs/promises";
import path from "node:path";

export const alt = "pi by Workzap — talk about your problems on WhatsApp";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

// pi (Resting) on Violet-50 with the wordmark and "BY WORKZAP", from the brand
// pack's own stacked lockup. The wordmark is never retyped.
export default async function Image() {
  const svg = await readFile(
    path.join(
      process.cwd(),
      "public",
      "pi-brand",
      "pi-lockup-stacked-color.svg",
    ),
  );
  const src = `data:image/svg+xml;base64,${svg.toString("base64")}`;
  return new ImageResponse(
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "#EEEBFE",
      }}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={src} width={320} height={560} alt="" />
    </div>,
    size,
  );
}
