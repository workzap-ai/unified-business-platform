"use client";

import { useState } from "react";
import type { ReactNode } from "react";
import type { TabId } from "./data";

// Every figure in these panels is made up, and each panel says so. By the nori rule
// each panel carries exactly one coral fill: the one thing to look at, always named in
// words as well, never by colour alone.

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div
      className="nxe-visual"
      role="group"
      aria-label={`${title} (illustrative)`}
    >
      <div className="nxe-visual-head">
        <span>{title}</span>
        <span className="nx-tag">Illustrative</span>
      </div>
      {children}
    </div>
  );
}

function Look({
  children,
  mark = true,
}: {
  children: ReactNode;
  mark?: boolean;
}) {
  return (
    <div className="nx-look">
      {mark ? <span className="nx-coral-mark" aria-hidden="true" /> : null}
      <span>
        <b>Look at this:</b> {children}
      </span>
    </div>
  );
}

function Bar({
  label,
  value,
  look,
}: {
  label: string;
  value: number;
  look?: boolean;
}) {
  return (
    <div className="nxe-bar-row">
      <span className="nxe-bar-label">{label}</span>
      <span className="nxe-bar-track" aria-hidden="true">
        <span
          className={`nxe-bar-fill${look ? " is-look" : ""}`}
          style={{ width: `${value}%` }}
        />
      </span>
      <span className="nxe-bar-value nx-num">
        {value}%{look ? <span className="nx-sr"> — look at this</span> : null}
      </span>
    </div>
  );
}

function Chip({ children }: { children: ReactNode }) {
  return <span className="nxe-chip">{children}</span>;
}

function StoresVisual() {
  return (
    <Panel title="Sales against target · this week">
      <Bar label="Shop A" value={92} />
      <Bar label="Shop B" value={81} />
      <Bar label="Shop C" value={74} />
      <Bar label="Shop E" value={68} />
      <Bar label="Shop D" value={46} look />
      <Look mark={false}>Shop D is well behind target this week.</Look>
      <div className="nxe-subhead">Store walk · today</div>
      <ul className="nxe-list">
        <li>
          Washroom <Chip>Photo added</Chip>
        </li>
        <li>
          Counter <Chip>Photo added</Chip>
        </li>
        <li>
          Stock room <Chip>Defect open</Chip>
        </li>
      </ul>
      <p className="nx-small">
        A defect stays open until a photo shows it fixed.
      </p>
    </Panel>
  );
}

function FinanceVisual() {
  const weeks = [62, 48, 71, 55];
  return (
    <Panel title="Finance desk · this month">
      <div className="nxe-kpis">
        <div>
          <span>Net sales</span>
          <strong className="nx-num">Rs 4,720,000</strong>
        </div>
        <div>
          <span>Gross margin</span>
          <strong className="nx-num">52.1%</strong>
        </div>
        <div>
          <span>Average sale</span>
          <strong className="nx-num">Rs 3,150</strong>
        </div>
      </div>
      <div className="nxe-subhead">Internal auditor · latest findings</div>
      <ul className="nxe-list">
        <li>
          <Look>Courier cash not received for 9 days.</Look>
        </li>
        <li>
          <Chip>Worth a check</Chip> Discounts above normal on one till
        </li>
        <li>
          <Chip>For information</Chip> Stock count differs by 2 items in Shop C
        </li>
        <li>
          <Chip>Going well</Chip> All cash deposits matched this week
        </li>
      </ul>
      <div className="nxe-subhead">Four-week cash forecast</div>
      <div className="nxe-columns" aria-hidden="true">
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
  const dots: { x: number; y: number; look?: boolean }[] = [
    { x: 78, y: 18 },
    { x: 66, y: 30 },
    { x: 85, y: 76 },
    { x: 70, y: 62 },
    { x: 22, y: 24, look: true },
    { x: 30, y: 36 },
    { x: 16, y: 78 },
    { x: 34, y: 70 },
  ];
  return (
    <Panel title="Margin and speed · every product">
      <div
        className="nxe-matrix"
        role="img"
        aria-label="A four-box chart. Top right: stars, high margin and fast selling. Bottom right: cash cows, lower margin but fast selling. Top left: traps, high margin but slow selling. Bottom left: dogs, low margin and slow selling. One product in traps is marked to look at."
      >
        <span className="nxe-q nxe-q-tl">Traps</span>
        <span className="nxe-q nxe-q-tr">Stars</span>
        <span className="nxe-q nxe-q-bl">Dogs</span>
        <span className="nxe-q nxe-q-br">Cash cows</span>
        {dots.map((d, i) => (
          <i
            key={i}
            className={d.look ? "is-look" : undefined}
            style={{ left: `${d.x}%`, top: `${d.y}%` }}
          />
        ))}
        <b className="nxe-axis nxe-axis-y">Higher margin ↑</b>
        <b className="nxe-axis nxe-axis-x">Faster selling →</b>
      </div>
      <div className="nxe-gap" />
      <Look mark={false}>One product is a trap: good margin, slow sales.</Look>
      <div className="nxe-subhead">One stock ledger</div>
      <div className="nxe-ledger">
        <div>
          <strong className="nx-num">Item 1204 · 6 units</strong>
          <span>Reserved for Shop B</span>
        </div>
        <Chip>Not available to any other transfer</Chip>
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
      <Bar label="Snapchat" value={31} look />
      <Look mark={false}>Snapchat is furthest behind its target.</Look>
      <div className="nxe-subhead">Orders today</div>
      <div className="nxe-chips">
        <span>
          <strong className="nx-num">142</strong> Dispatched
        </span>
        <span>
          <strong className="nx-num">96</strong> Delivered
        </span>
        <span>
          <strong className="nx-num">38</strong> Pending
        </span>
        <span>
          <strong className="nx-num">7</strong> Need a fix
        </span>
      </div>
    </Panel>
  );
}

function MarketingVisual() {
  return (
    <Panel title="Suggested by nori · waiting for you">
      <ul className="nxe-queue">
        <li>
          <div>
            <Look>Pause the “Summer sale” ad set.</Look>
            <span>Results have been fading for 5 days.</span>
          </div>
          <Chip>High priority</Chip>
        </li>
        <li>
          <div>
            <strong>Refresh the creative on “New arrivals”</strong>
            <span>The same image has run for 3 weeks.</span>
          </div>
          <Chip>Medium priority</Chip>
        </li>
      </ul>
      <p className="nx-small">You edit and approve before anything changes.</p>
      <div className="nxe-subhead">Did the SMS really work?</div>
      <div className="nxe-lift" aria-hidden="true">
        <span style={{ height: "82%" }}>
          <i>Messaged group</i>
        </span>
        <span className="is-hold" style={{ height: "48%" }}>
          <i>Holdout group</i>
        </span>
      </div>
      <p className="nx-small">
        The holdout group shows what would have happened with no message, so you
        see the real lift.
      </p>
    </Panel>
  );
}

function Reveal({ value }: { value: string }) {
  const [shown, setShown] = useState(false);
  return (
    <span className="nxe-reveal">
      <span
        className={shown ? "nx-num" : "nx-num nxe-blur"}
        aria-hidden={!shown}
      >
        {value}
      </span>
      <button
        type="button"
        aria-pressed={shown}
        onClick={() => setShown((s) => !s)}
      >
        {shown ? "Hide" : "Reveal"}
        <span className="nx-sr"> ID number</span>
      </button>
    </span>
  );
}

function PeopleVisual() {
  return (
    <Panel title="Workforce explorer">
      <div className="nxe-table" role="table" aria-label="Sample staff table">
        <div role="row" className="nxe-table-head">
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
      <p className="nx-small">
        Try it: private details stay blurred until you choose.
      </p>
      <div className="nxe-subhead">Odd figures</div>
      <ul className="nxe-list">
        <li>
          <Look>Overtime is well above average at one branch.</Look>
        </li>
        <li>
          <Chip>Worth a check</Chip> Several low leave balances in one team
        </li>
      </ul>
    </Panel>
  );
}

function ExecutiveVisual() {
  const tiles: [string, string][] = [
    ["Revenue", "On track"],
    ["Gross profit", "On track"],
    ["E-commerce", "On track"],
    ["Cash on delivery", "On track"],
    ["Dead stock", "Look at this"],
  ];
  return (
    <Panel title="The company on one screen">
      <div className="nxe-tiles">
        {tiles.map(([name, state]) => {
          const look = state === "Look at this";
          return (
            <div key={name} className={look ? "is-look" : undefined}>
              <span>{name}</span>
              <strong>
                {look ? (
                  <i className="nx-coral-mark" aria-hidden="true" />
                ) : null}
                {state}
              </strong>
            </div>
          );
        })}
      </div>
      <div className="nxe-subhead">Cash you can free up · ranked</div>
      <ol className="nxe-ranked">
        <li>
          Collect courier cash <Chip>Owner: Finance</Chip>
        </li>
        <li>
          Clear slow stock <Chip>Owner: Planning</Chip>
        </li>
        <li>
          Return unsold seasonal lines <Chip>Owner: Buying</Chip>
        </li>
      </ol>
      <div className="nxe-chat">
        <p className="nxe-chat-q">Where is our cash tied up?</p>
        <p className="nxe-chat-a">
          Most of the cash in slow stock sits in two shops. Moving it to the
          shops that sell it fastest would free the most.
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
