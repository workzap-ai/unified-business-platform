import { ModuleExplorer } from "./module-explorer";

export function ModulesSection() {
  return (
    <section className="nx-section">
      <div className="nx-wrap">
        <h2 className="nx-sr">The seven areas nori covers</h2>
        <ModuleExplorer />
        <div className="nxe-soon">
          <strong>Vision (CCTV)</strong>
          <span className="nx-label">Coming soon</span>
          <p className="nx-small">
            Footfall, queue times, conversion and shrinkage from your existing
            cameras.
          </p>
        </div>
      </div>
    </section>
  );
}
