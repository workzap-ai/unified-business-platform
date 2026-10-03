import { ModuleExplorer } from "./module-explorer";

// Replaces the old "modules" section. The heading, the Retail OS Core card and the
// Vision (CCTV) card keep their previous wording; the module cards are now the
// explorer below, built from the 2026-10-03 feature inventory.
export function ModulesSection() {
  return (
    <section
      id="modules"
      style={{ maxWidth: 1080, margin: "0 auto", padding: "56px 24px" }}
    >
      <div style={{ textAlign: "center", marginBottom: 34 }}>
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 8,
            fontSize: "12.5px",
            fontWeight: 700,
            letterSpacing: "0.5px",
            textTransform: "uppercase",
            color: "var(--accent-strong)",
            background: "var(--accent-soft)",
            border: "1px solid var(--border-accent)",
            padding: "6px 12px",
            borderRadius: 999,
          }}
        >
          One platform, your modules
        </span>
        <h2
          style={{
            fontSize: "clamp(24px, 3.5vw, 34px)",
            fontWeight: 820,
            letterSpacing: "-0.8px",
            margin: "16px 0 8px",
          }}
        >
          Everything in one platform.
        </h2>
        <p
          style={{
            color: "var(--text-secondary)",
            fontSize: 15,
            margin: "0 auto",
            maxWidth: 580,
          }}
        >
          The Retail OS Core and every module below come with every plan. Vision
          (CCTV) is coming soon.
        </p>
      </div>
      <ModuleExplorer />
      <div
        className="wz-card"
        style={{ padding: 18, marginTop: 18, borderColor: "var(--border)" }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "baseline",
            gap: 10,
            flexWrap: "wrap",
          }}
        >
          <span style={{ fontSize: 15, fontWeight: 750 }}>Vision (CCTV)</span>
          <span style={{ fontSize: "12.5px", color: "var(--text-muted)" }}>
            Coming soon
          </span>
        </div>
        <p
          style={{
            fontSize: "12.5px",
            color: "var(--text-secondary)",
            lineHeight: 1.55,
            margin: "4px 0 0",
          }}
        >
          Footfall, queue times, conversion and shrinkage from your existing
          cameras — the store floor, quantified.
        </p>
      </div>
      <p
        style={{
          textAlign: "center",
          fontSize: "12.5px",
          color: "var(--text-muted)",
          marginTop: 18,
        }}
      >
        New modules ship regularly. Your Retail OS grows without you switching
        tools.
      </p>
    </section>
  );
}
