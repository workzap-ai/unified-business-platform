import { ModuleExplorer } from "./module-explorer";

export function ModulesSection() {
  return (
    <section id="inside" className="nx-section">
      <div className="nx-wrap">
        <div className="nx-head">
          <span className="nx-label">What’s inside</span>
          <h2>Your whole retail business, run from one place.</h2>
          <p className="nx-lead">
            Shops, money, stock, online, marketing and people. Each comes with
            the numbers, the reasons and the next step.
          </p>
        </div>
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
