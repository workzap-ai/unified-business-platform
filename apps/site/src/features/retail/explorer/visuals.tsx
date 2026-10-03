"use client";

import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import type { TabId } from "./data";

// Every figure in these panels is made-up sample data, and the panel says so.

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div
      className="wzx-visual"
      role="group"
      aria-label={`${title} (illustrative)`}
    >
      <div className="wzx-visual-head">
        <span>{title}</span>
        <span className="wzx-tag">Illustrative sample data</span>
      </div>
      {children}
    </div>
  );
}

function Bar({
  label,
  value,
  flag,
  suffix = "%",
}: {
  label: string;
  value: number;
  flag?: boolean;
  suffix?: string;
}) {
  return (
    <div className="wzx-bar-row">
      <span className="wzx-bar-label">{label}</span>
      <span className="wzx-bar-track" aria-hidden="true">
        <span
          className={`wzx-bar-fill${flag ? " wzx-bar-flag" : ""}`}
          style={{ width: `${value}%` }}
        />
      </span>
      <span className="wzx-bar-value">
        {value}
        {suffix}
        {flag ? <span className="wzx-sr"> — needs attention</span> : null}
      </span>
    </div>
  );
}

function Pill({ tone, children }: { tone: string; children: ReactNode }) {
  return <span className={`wzx-pill wzx-pill-${tone}`}>{children}</span>;
}

function StoresVisual() {
  return (
    <Panel title="Network overview · sales against target">
      <Bar label="Shop A" value={92} />
      <Bar label="Shop B" value={81} />
      <Bar label="Shop C" value={74} />
      <Bar label="Shop E" value={68} />
      <Bar label="Shop D" value={46} flag />
      <div className="wzx-note">
        <Pill tone="warn">Needs attention</Pill>
        <span>Shop D is well behind target this week.</span>
      </div>
      <div className="wzx-subhead">Store walk · today</div>
      <ul className="wzx-checks">
        <li>
          <span className="wzx-check wzx-check-ok" aria-hidden="true">
            ✓
          </span>
          Washroom <Pill tone="good">Photo added</Pill>
        </li>
        <li>
          <span className="wzx-check wzx-check-ok" aria-hidden="true">
            ✓
          </span>
          Counter <Pill tone="good">Photo added</Pill>
        </li>
        <li>
          <span className="wzx-check wzx-check-open" aria-hidden="true">
            !
          </span>
          Stock room <Pill tone="warn">Defect open</Pill>
        </li>
      </ul>
      <p className="wzx-fine">
        The defect stays open until a photo shows it fixed.
      </p>
    </Panel>
  );
}

function FinanceVisual() {
  const weeks = [62, 48, 71, 55];
  return (
    <Panel title="Finance desk · this month">
      <div className="wzx-kpis">
        <div>
          <span>Net sales</span>
          <strong>PKR 4.7M</strong>
        </div>
        <div>
          <span>Gross margin</span>
          <strong>52.1%</strong>
        </div>
        <div>
          <span>Avg. transaction</span>
          <strong>PKR 3,150</strong>
        </div>
      </div>
      <div className="wzx-subhead">Internal auditor · latest findings</div>
      <ul className="wzx-findings">
        <li>
          <Pill tone="bad">Critical</Pill> Courier cash not received for 9 days
        </li>
        <li>
          <Pill tone="warn">Warning</Pill> Discounts above normal on one till
        </li>
        <li>
          <Pill tone="info">Info</Pill> Stock count differs by 2 items in Shop C
        </li>
        <li>
          <Pill tone="good">Positive</Pill> All cash deposits matched this week
        </li>
      </ul>
      <div className="wzx-subhead">Four-week cash forecast</div>
      <div className="wzx-columns" aria-hidden="true">
        {weeks.map((h, i) => (
          <span key={i} style={{ height: `${h}%` }}>
            <i>W{i + 1}</i>
          </span>
        ))}
      </div>
    </Panel>
  );
}

function PlanningVisual() {
  const dots: { x: number; y: number }[] = [
    { x: 78, y: 18 },
    { x: 66, y: 30 },
    { x: 85, y: 76 },
    { x: 70, y: 62 },
    { x: 22, y: 24 },
    { x: 30, y: 36 },
    { x: 16, y: 78 },
    { x: 34, y: 70 },
  ];
  return (
    <Panel title="Margin × velocity · every product">
      <div
        className="wzx-matrix"
        role="img"
        aria-label="A four-box chart. Top right: stars, high margin and fast selling. Bottom right: cash cows, lower margin but fast selling. Top left: traps, high margin but slow selling. Bottom left: dogs, low margin and slow selling."
      >
        <span className="wzx-q wzx-q-tl">Traps</span>
        <span className="wzx-q wzx-q-tr">Stars</span>
        <span className="wzx-q wzx-q-bl">Dogs</span>
        <span className="wzx-q wzx-q-br">Cash cows</span>
        {dots.map((d, i) => (
          <i key={i} style={{ left: `${d.x}%`, top: `${d.y}%` }} />
        ))}
        <b className="wzx-axis wzx-axis-y">Higher margin ↑</b>
        <b className="wzx-axis wzx-axis-x">Faster selling →</b>
      </div>
      <div className="wzx-subhead">One stock ledger</div>
      <div className="wzx-ledger">
        <div>
          <strong>Item 1204 · 6 units</strong>
          <span>Reserved for Shop B</span>
        </div>
        <Pill tone="good">Not available to any other transfer</Pill>
      </div>
    </Panel>
  );
}

function EcommerceVisual() {
  return (
    <Panel title="Ads against target · this week">
      <Bar label="Meta" value={82} />
      <Bar label="Google" value={64} />
      <Bar label="TikTok" value={47} />
      <Bar label="Snapchat" value={31} />
      <div className="wzx-subhead">Orders today</div>
      <div className="wzx-chips">
        <span>
          <strong>142</strong> Dispatched
        </span>
        <span>
          <strong>96</strong> Delivered
        </span>
        <span>
          <strong>38</strong> Pending
        </span>
        <span>
          <strong>7</strong> Need a fix
        </span>
      </div>
    </Panel>
  );
}

function MarketingVisual() {
  return (
    <Panel title="Recommended by the AI · waiting for you">
      <ul className="wzx-queue">
        <li>
          <div>
            <strong>Pause “Summer sale” ad set</strong>
            <span>Performance has been fading for 5 days</span>
          </div>
          <Pill tone="bad">High</Pill>
        </li>
        <li>
          <div>
            <strong>Refresh the creative on “New arrivals”</strong>
            <span>Same image has run for 3 weeks</span>
          </div>
          <Pill tone="warn">Medium</Pill>
        </li>
      </ul>
      <p className="wzx-fine">You edit and approve before anything changes.</p>
      <div className="wzx-subhead">Did the SMS really work?</div>
      <div className="wzx-lift" aria-hidden="true">
        <span style={{ height: "82%" }}>
          <i>Messaged group</i>
        </span>
        <span className="wzx-lift-hold" style={{ height: "48%" }}>
          <i>Holdout group</i>
        </span>
      </div>
      <p className="wzx-fine">
        The holdout group shows what would have happened with no message, so you
        see the real lift.
      </p>
    </Panel>
  );
}

function Reveal({ value }: { value: string }) {
  const [shown, setShown] = useState(false);
  return (
    <span className="wzx-reveal">
      <span className={shown ? "" : "wzx-blur"} aria-hidden={!shown}>
        {value}
      </span>
      <button
        type="button"
        aria-pressed={shown}
        onClick={() => setShown((s) => !s)}
      >
        {shown ? "Hide" : "Reveal"}
        <span className="wzx-sr"> ID number</span>
      </button>
    </span>
  );
}

function PeopleVisual() {
  return (
    <Panel title="Workforce explorer">
      <div className="wzx-table" role="table" aria-label="Sample staff table">
        <div role="row" className="wzx-table-head">
          <span role="columnheader">Staff</span>
          <span role="columnheader">Branch</span>
          <span role="columnheader">ID number</span>
        </div>
        <div role="row">
          <span role="cell">Staff member 1</span>
          <span role="cell">Shop A</span>
          <span role="cell">
            <Reveal value="12345-6789012-3" />
          </span>
        </div>
        <div role="row">
          <span role="cell">Staff member 2</span>
          <span role="cell">Shop C</span>
          <span role="cell">
            <Reveal value="12345-2109876-5" />
          </span>
        </div>
      </div>
      <p className="wzx-fine">
        Try it: private details stay blurred until you choose.
      </p>
      <div className="wzx-subhead">Red flags</div>
      <ul className="wzx-findings">
        <li>
          <Pill tone="bad">High</Pill> Overtime well above average at one branch
        </li>
        <li>
          <Pill tone="warn">Medium</Pill> Several low leave balances in one team
        </li>
      </ul>
    </Panel>
  );
}

function TypeLine({ text }: { text: string }) {
  const [n, setN] = useState(0);
  useEffect(() => {
    const reduce = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;
    if (reduce) {
      const t = window.setTimeout(() => setN(text.length), 0);
      return () => window.clearTimeout(t);
    }
    const id = window.setInterval(() => {
      setN((v) => {
        if (v >= text.length) {
          window.clearInterval(id);
          return v;
        }
        return v + 1;
      });
    }, 16);
    return () => window.clearInterval(id);
  }, [text]);
  return (
    <>
      <span className="wzx-sr">{text}</span>
      <span aria-hidden="true">
        {text.slice(0, n)}
        {n < text.length ? <span className="wzx-caret" /> : null}
      </span>
    </>
  );
}

function ExecutiveVisual() {
  return (
    <Panel title="Company control tower">
      <div className="wzx-tiles">
        {[
          "Revenue",
          "Gross profit",
          "E-commerce",
          "Cash on delivery",
          "Dead stock",
        ].map((t, i) => (
          <div key={t}>
            <span>{t}</span>
            <i
              className={i === 4 ? "wzx-dot-warn" : "wzx-dot-ok"}
              aria-hidden="true"
            />
          </div>
        ))}
      </div>
      <div className="wzx-subhead">Controllable money · ranked</div>
      <ol className="wzx-ranked">
        <li>
          Collect courier cash <Pill tone="info">Owner: Finance</Pill>
        </li>
        <li>
          Clear slow stock <Pill tone="info">Owner: Planning</Pill>
        </li>
        <li>
          Return unsold seasonal lines <Pill tone="info">Owner: Buying</Pill>
        </li>
      </ol>
      <div className="wzx-chat">
        <p className="wzx-chat-q">Where is our cash stuck?</p>
        <p className="wzx-chat-a">
          <TypeLine text="Most of the cash tied up in slow stock sits in two shops. Moving it to the shops that sell it fastest would free the most." />
        </p>
      </div>
    </Panel>
  );
}

export function ModuleVisual({ id }: { id: TabId }) {
  switch (id) {
    case "stores":
      return <StoresVisual />;
    case "finance":
      return <FinanceVisual />;
    case "planning":
      return <PlanningVisual />;
    case "ecommerce":
      return <EcommerceVisual />;
    case "marketing":
      return <MarketingVisual />;
    case "people":
      return <PeopleVisual />;
    case "executive":
      return <ExecutiveVisual />;
  }
}
