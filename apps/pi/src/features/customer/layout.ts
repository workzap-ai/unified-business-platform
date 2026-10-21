/** Shared by the dashboard visuals and the WhatsApp card images (server-safe). */

import type { CustomerIssue } from "@/lib/customer-api";

/** Data colours from the brief (never used for text). */
export const MARK = {
  us: "#3b82f6",
  you: "#f5a524",
  ready: "#1f9d63",
  noted: "#5A47F5",
  off: "#b9b6c9",
} as const;

export function markOf(
  issue: Pick<CustomerIssue, "stage" | "ball_with" | "waiting_on_other_until">,
) {
  if (issue.stage === "noted")
    return { fill: "none", stroke: MARK.noted, hollow: true };
  if (
    ["paused", "closed"].includes(issue.stage) ||
    issue.waiting_on_other_until
  )
    return { fill: MARK.off, stroke: MARK.off, hollow: false };
  if (issue.stage === "solution_ready" || issue.stage === "live")
    return { fill: MARK.ready, stroke: MARK.ready, hollow: false };
  if (issue.ball_with === "client")
    return { fill: MARK.you, stroke: MARK.you, hollow: false };
  return { fill: MARK.us, stroke: MARK.us, hollow: false };
}

export type MapNode = {
  index: number;
  x: number;
  y: number;
  r: number;
  issue: CustomerIssue;
};
export type MapArea = {
  name: string;
  x: number;
  y: number;
  w: number;
  h: number;
};

/** Areas side by side, requests stacked in their area. Radius = 18 + 5 x impact. */
export function layoutMap(issues: CustomerIssue[], vertical = false) {
  const areas = [...new Set(issues.map((i) => i.area || "General"))];
  const columnW = 210;
  const rowH = 150;
  const top = 44;
  const byArea = areas.map((area) =>
    issues
      .map((issue, index) => ({ issue, index }))
      .filter(({ issue }) => (issue.area || "General") === area),
  );
  const nodes: MapNode[] = [];
  const regions: MapArea[] = [];
  if (vertical) {
    // WhatsApp card: one column, areas one under another.
    let y = top;
    byArea.forEach((members, a) => {
      const start = y;
      members.forEach(({ issue, index }) => {
        nodes.push({
          index,
          issue,
          // Zigzag across the whole card so lines never run through a label.
          x: nodes.length % 2 ? 330 : 170,
          y: y + 70,
          r: 18 + 5 * (issue.impact ?? 3),
        });
        y += rowH;
      });
      regions.push({
        name: areas[a],
        x: 16,
        y: start,
        w: 468,
        h: y - start - 10,
      });
    });
    return { nodes, regions, width: 500, height: y };
  }
  const rows = Math.max(1, ...byArea.map((m) => m.length));
  byArea.forEach((members, a) => {
    regions.push({
      name: areas[a],
      x: 12 + a * columnW,
      y: 8,
      w: columnW - 24,
      h: top + rows * rowH - 8,
    });
    members.forEach(({ issue, index }, k) => {
      nodes.push({
        index,
        issue,
        x: a * columnW + columnW / 2,
        y: top + k * rowH + rowH / 2 - 10,
        r: 18 + 5 * (issue.impact ?? 3),
      });
    });
  });
  return {
    nodes,
    regions,
    width: Math.max(360, areas.length * columnW),
    height: top + rows * rowH + 10,
  };
}

export function shortTitle(title: string, max = 18) {
  return title.length > max ? `${title.slice(0, max - 1)}…` : title;
}
