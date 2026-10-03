"use client";

import { useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { MODULE_TABS, type TabId } from "./data";
import { ModuleVisual } from "./visuals";
import "./explorer.css";

export function ModuleExplorer() {
  const [active, setActive] = useState<TabId>("stores");
  const refs = useRef<Partial<Record<TabId, HTMLButtonElement | null>>>({});
  const count = MODULE_TABS.length;
  const index = MODULE_TABS.findIndex((t) => t.id === active);
  const tab = MODULE_TABS[index];

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    let next = index;
    if (e.key === "ArrowRight") next = (index + 1) % count;
    else if (e.key === "ArrowLeft") next = (index - 1 + count) % count;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = count - 1;
    else return;
    e.preventDefault();
    const id = MODULE_TABS[next].id;
    setActive(id);
    refs.current[id]?.focus();
  }

  return (
    <div className="wzx">
      <div
        className="wzx-tabs"
        role="tablist"
        aria-label="Retail OS modules"
        onKeyDown={onKeyDown}
      >
        {MODULE_TABS.map((t) => (
          <button
            key={t.id}
            ref={(el) => {
              refs.current[t.id] = el;
            }}
            type="button"
            role="tab"
            id={`wzx-tab-${t.id}`}
            aria-selected={t.id === active}
            aria-controls={`wzx-panel-${t.id}`}
            tabIndex={t.id === active ? 0 : -1}
            className="wzx-tab"
            onClick={() => setActive(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div
        key={tab.id}
        role="tabpanel"
        id={`wzx-panel-${tab.id}`}
        aria-labelledby={`wzx-tab-${tab.id}`}
        tabIndex={0}
        className="wzx-panel"
      >
        <div className="wzx-copy">
          <span className="wzx-module-pill">{tab.pill}</span>
          <h3>{tab.headline}</h3>
          <p className="wzx-summary">{tab.summary}</p>
          <ul className="wzx-features">
            {tab.features.map((f) => (
              <li key={f.title}>
                <strong>{f.title}</strong>
                <span>{f.text}</span>
              </li>
            ))}
          </ul>
        </div>
        <ModuleVisual id={tab.id} />
      </div>
    </div>
  );
}
