import { ModuleExplorer } from "./module-explorer";

export function ModulesSection() {
  return (
    <section className="nx-section">
      <div className="nx-wrap">
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
