import { ImageResponse } from "next/og";
import { readFile } from "node:fs/promises";
import path from "node:path";

export const alt = "nori by Workzap";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

// The brand pack's own stacked lockup on Nori Paper. The lockup is drawn, never retyped,
// and keeps its true proportions (173.6 x 209).
export default async function Image() {
  const svg = await readFile(
    path.join(
      process.cwd(),
      "public",
      "nori-brand",
      "nori-lockup-stacked-color.svg",
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
        background: "#F7F1E6",
      }}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={src} width={432} height={520} alt="" />
    </div>,
    size,
  );
}
