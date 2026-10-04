import { ImageResponse } from "next/og";
import { readFile } from "node:fs/promises";
import path from "node:path";

// One stable share-image address per brand (/og/nori, /og/pi, /og/workzap), so every
// page, not only each section's first page, can name its image in its own metadata.
export const dynamic = "force-static";
export const dynamicParams = false;

const SIZE = { width: 1200, height: 630 };

export function generateStaticParams() {
  return [{ brand: "nori" }, { brand: "pi" }, { brand: "workzap" }];
}

async function lockup(file: string) {
  const svg = await readFile(path.join(process.cwd(), "public", file));
  return `data:image/svg+xml;base64,${svg.toString("base64")}`;
}

const frame = (background: string) =>
  ({
    width: "100%",
    height: "100%",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    background,
  }) as const;

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ brand: string }> },
) {
  const { brand } = await params;

  if (brand === "nori") {
    // The brand pack's own stacked lockup on Nori Paper, drawn and never retyped.
    const src = await lockup("nori-brand/nori-lockup-stacked-color.svg");
    return new ImageResponse(
      <div style={frame("#F7F1E6")}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={src} width={432} height={520} alt="" />
      </div>,
      SIZE,
    );
  }

  if (brand === "pi") {
    // pi (Resting) on Violet-50 with the wordmark and "BY WORKZAP", from the pack.
    const src = await lockup("pi-brand/pi-lockup-stacked-color.svg");
    return new ImageResponse(
      <div style={frame("#EEEBFE")}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={src} width={320} height={560} alt="" />
      </div>,
      SIZE,
    );
  }

  // The parent site: the W tile, the name and the two products.
  return new ImageResponse(
    <div
      style={{
        ...frame("#FAFAF7"),
        flexDirection: "column",
        alignItems: "flex-start",
        padding: "0 96px",
        color: "#0C1114",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 28 }}>
        <div
          style={{
            width: 96,
            height: 96,
            borderRadius: 24,
            background: "#00A86B",
            color: "#FFFFFF",
            fontSize: 64,
            fontWeight: 800,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          W
        </div>
        <div style={{ fontSize: 84, fontWeight: 800 }}>Workzap</div>
      </div>
      <div style={{ marginTop: 40, fontSize: 44, color: "#3A4A52" }}>
        Software that shows what is going wrong. nori and pi.
      </div>
    </div>,
    SIZE,
  );
}
