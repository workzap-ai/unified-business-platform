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
    <div className="nxe">
      <div
        className="nxe-tabs"
        role="tablist"
        aria-label="What nori covers"
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
            id={`nxe-tab-${t.id}`}
            aria-selected={t.id === active}
            aria-controls={`nxe-panel-${t.id}`}
            tabIndex={t.id === active ? 0 : -1}
            className="nxe-tab"
            onClick={() => setActive(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>
      {MODULE_TABS.map((t) => (
        <div
          key={t.id}
          role="tabpanel"
          id={`nxe-panel-${t.id}`}
          aria-labelledby={`nxe-tab-${t.id}`}
          tabIndex={0}
          hidden={t.id !== active}
          className="nxe-panel"
        >
          <div className="nxe-copy">
            <h3>{t.headline}</h3>
            <p className="nxe-summary">{t.summary}</p>
            <ul className="nxe-features">
              {t.features.map((f) => (
                <li key={f.title}>
                  <strong>{f.title}</strong>
                  <span>{f.text}</span>
                </li>
              ))}
            </ul>
          </div>
          <ModuleVisual id={t.id} />
        </div>
      ))}
    </div>
  );
}
