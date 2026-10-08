"use client";

/**
 * pi Customer v2 visuals: Problem Map, priority chart, Problem -> Solution flow and the
 * activity timeline. Plain SVG/HTML (no chart library), so the same layout functions
 * also draw the WhatsApp cards. Colour always comes with a label: "Noted" is a hollow
 * ring, every mark has text, and every chart has a "View as list" table.
 */

import { useEffect, useRef, useState } from "react";
import { List, Network, Unlink } from "lucide-react";

import type { CustomerIssue, IssueLink } from "@/lib/customer-api";
import { cn } from "@/lib/cn";
import { STAGE, TURN, shortDay } from "./shared";
import { MARK, markOf, shortTitle } from "./layout";

export { MARK, layoutMap, markOf } from "./layout";

/* ----------------------------------------------------------- encoding */
type Lang = "en" | "ur";

const DASHED = new Set(["part_of", "depends_on"]);

export function LinkKind({ type, lang }: { type: string; lang: Lang }) {
  const words: Record<string, [string, string]> = {
    shared_data: ["shared data", "ek jaisa data"],
    same_cause: ["same cause", "ek hi wajah"],
    depends_on: ["depends on", "pehle ye chahiye"],
    part_of: ["part of", "is ka hissa"],
  };
  return <>{(words[type] ?? [type, type])[lang === "ur" ? 1 : 0]}</>;
}

function Legend({ lang, links = true }: { lang: Lang; links?: boolean }) {
  const items: [string, string, boolean][] = [
    [MARK.us, TURN.us[lang], false],
    [MARK.you, TURN.you[lang], false],
    [MARK.ready, STAGE.solution_ready[lang], false],
    [MARK.noted, STAGE.noted[lang], true],
  ];
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-muted-foreground">
      {items.map(([color, label, hollow]) => (
        <li key={label} className="inline-flex items-center gap-1.5">
          <span
            aria-hidden
            className="inline-block size-2.5 rounded-full"
            style={
              hollow ? { border: `2px solid ${color}` } : { background: color }
            }
          />
          {label}
        </li>
      ))}
      {links && (
        <>
          <li className="inline-flex items-center gap-1.5">
            <svg width="22" height="6" aria-hidden>
              <line
                x1="0"
                y1="3"
                x2="22"
                y2="3"
                stroke={MARK.noted}
                strokeWidth="2"
              />
            </svg>
            {lang === "ur" ? "ek data / ek wajah" : "shared data / same cause"}
          </li>
          <li className="inline-flex items-center gap-1.5">
            <svg width="22" height="6" aria-hidden>
              <line
                x1="0"
                y1="3"
                x2="22"
                y2="3"
                stroke={MARK.noted}
                strokeWidth="2"
                strokeDasharray="4 3"
              />
            </svg>
            {lang === "ur" ? "hissa / pehle chahiye" : "part of / depends on"}
          </li>
        </>
      )}
    </ul>
  );
}

function ViewToggle({
  list,
  onChange,
  lang,
}: {
  list: boolean;
  onChange: (list: boolean) => void;
  lang: Lang;
}) {
  return (
    <button
      type="button"
      onClick={() => onChange(!list)}
      className="inline-flex min-h-9 items-center gap-1.5 rounded-lg border border-border px-2.5 text-xs font-medium text-foreground-secondary hover:bg-surface-muted"
      aria-pressed={list}
    >
      {list ? (
        <Network className="size-3.5" aria-hidden />
      ) : (
        <List className="size-3.5" aria-hidden />
      )}
      {list
        ? lang === "ur"
          ? "Map dekhein"
          : "View map"
        : lang === "ur"
          ? "List dekhein"
          : "View as list"}
    </button>
  );
}

/* --------------------------------------------------------- problem map */

const MAP_CSS = `
@keyframes pimap-pop { from { transform: scale(.86) } to { transform: none } }
@keyframes pimap-fade { from { opacity: .35 } to { opacity: 1 } }
@keyframes pimap-pulse { 0% { transform: scale(1); opacity: .75 } 70%, 100% { transform: scale(1.32); opacity: 0 } }
.pimap-pulse { animation: pimap-pulse 2.4s ease-out infinite }
.pimap-node { animation: pimap-pop .45s cubic-bezier(.2,.8,.2,1) both }
.pimap-line { animation: pimap-fade .6s ease-out both }
@media (prefers-reduced-motion: reduce) { .pimap-node, .pimap-line, .pimap-pulse { animation: none } }
`;

const JOURNEY_LABELS = {
  en: [
    "Noted",
    "Understood",
    "Linked",
    "Solution ready",
    "Your decision",
    "Building",
    "Live",
  ],
  ur: [
    "Note hua",
    "Samjha gaya",
    "Juda hua",
    "Hal tayyar",
    "Aap ka faisla",
    "Ban raha",
    "Mukammal",
  ],
};

function useWidth() {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) =>
      setWidth(entry.contentRect.width),
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}

/** Requests one solution would fix sit next to each other, the most connected in the
 * middle of its group, so lines stay short and never cross the map. */
function mapOrder(issues: CustomerIssue[]) {
  const groups = new Map<string, CustomerIssue[]>();
  for (const issue of issues) {
    const key = issue.solution_id || issue.title;
    groups.set(key, [...(groups.get(key) ?? []), issue]);
  }
  return [...groups.values()]
    .sort((a, b) => b.length - a.length)
    .flatMap((group) => {
      const sorted = [...group].sort(
        (a, b) => (b.linked ?? 0) - (a.linked ?? 0),
      );
      const out: CustomerIssue[] = [];
      sorted.forEach((issue, k) =>
        k % 2 ? out.unshift(issue) : out.push(issue),
      );
      return out;
    });
}

const CARD_W = 136;

const NARROW = 520;
const ROW = 204;

function mapHeight(n: number, w: number) {
  return w < NARROW
    ? Math.max(260, n * ROW + 40)
    : Math.round(Math.max(w * 0.7, 400));
}

function mapPoints(n: number, w: number, h: number, d: (k: number) => number) {
  const cx = w / 2;
  const cy = h / 2 - 10;
  const raw =
    w < NARROW && n > 1
      ? Array.from({ length: n }, (_, k) => ({
          x: k % 2 ? w * 0.68 : w * 0.32,
          y: 70 + k * ROW,
        }))
      : n === 1
        ? [{ x: cx, y: cy }]
        : n === 2
          ? [
              { x: w * 0.26, y: cy },
              { x: w * 0.74, y: cy },
            ]
          : Array.from({ length: n }, (_, k) => {
              const angle = -Math.PI / 2 + (2 * Math.PI * k) / n;
              return {
                x: cx + w * 0.36 * Math.cos(angle),
                y: cy + h * 0.34 * Math.sin(angle),
              };
            });
  // Keep every card (circle + two-line title) inside the map.
  return raw.map((p, k) => ({
    x: Math.min(Math.max(p.x, CARD_W / 2 + 6), w - CARD_W / 2 - 6),
    y: Math.min(Math.max(p.y, d(k) / 2 + 10), h - d(k) / 2 - 62),
  }));
}

export function ProblemMap({
  issues,
  links,
  lang,
  onNotRelated,
  onOpen,
}: {
  issues: CustomerIssue[];
  links: IssueLink[];
  lang: Lang;
  onNotRelated?: (link: IssueLink) => void;
  onOpen?: (issue: CustomerIssue) => void;
}) {
  const [asList, setAsList] = useState(false);
  const [picked, setPicked] = useState<IssueLink | null>(null);
  const [hover, setHover] = useState<string | null>(null);
  const [box, width] = useWidth();
  const ur = lang === "ur";

  const open = issues.filter((i) => !["live", "closed"].includes(i.stage));
  const shown = mapOrder((open.length ? open : issues).slice(0, 8));
  const titles = new Set(shown.map((i) => i.title));
  const visible = links.filter(
    (l) => titles.has(l.a_title) && titles.has(l.b_title),
  );
  const groups = new Map<string, CustomerIssue[]>();
  shown.forEach((i) => {
    const key = i.solution_id ?? "";
    groups.set(key, [...(groups.get(key) ?? []), i]);
  });
  const biggest =
    [...groups.values()].sort((a, b) => b.length - a.length)[0] ?? [];
  const merged = visible.length ? biggest.length : 0;

  if (!issues.length)
    return (
      <div className="flex flex-col items-center gap-3 rounded-2xl bg-[#1b1830] px-4 py-12 text-center">
        <span
          aria-hidden
          className="size-16 rounded-full border-2 border-dashed border-[#5A47F5]"
        />
        <p className="max-w-xs text-sm text-[#cfcae8]">
          {ur
            ? "pi ko koi masla batayein, woh yahan nazar aayega."
            : "Tell pi about a problem and it appears here."}
        </p>
      </div>
    );

  const w = width || 640;
  const narrow = w < NARROW;
  const h = mapHeight(shown.length, w);
  const size = (i: CustomerIssue) =>
    50 + 6 * Math.min(5, Math.max(1, i.impact ?? 3));
  const points = mapPoints(shown.length, w, h, (k) => size(shown[k]));
  const nodes = shown.map((issue, k) => ({
    issue,
    ...points[k],
    d: size(issue),
  }));
  const at = (title: string) => nodes.find((n) => n.issue.title === title)!;
  const center = { x: w / 2, y: h / 2 - 10 };
  const hub = !narrow && shown.length >= 3 && merged >= 2;
  const related = (title: string) =>
    !hover ||
    title === hover ||
    visible.some(
      (l) =>
        (l.a_title === hover && l.b_title === title) ||
        (l.b_title === hover && l.a_title === title),
    );
  const curve = (link: IssueLink) => {
    const a = at(link.a_title);
    const b = at(link.b_title);
    const mx = (a.x + b.x) / 2;
    const my = (a.y + b.y) / 2;
    // Arcs bow away from the middle (where the solution hub sits).
    const pull = shown.length >= 3 ? 0.42 : 0;
    const cx = narrow
      ? mx + (Math.abs(a.x - b.x) < 20 ? (mx < w / 2 ? -70 : 70) : 34)
      : shown.length === 2
        ? mx
        : mx + (mx - center.x) * pull;
    const cy = narrow
      ? my
      : shown.length === 2
        ? my - 46
        : my + (my - center.y) * pull;
    return {
      d: `M ${a.x} ${a.y} Q ${cx} ${cy} ${b.x} ${b.y}`,
      // On a phone the label sits in the gap between rows, clear of the titles.
      label: narrow
        ? {
            x: Math.min(
              Math.max(0.25 * a.x + 0.5 * cx + 0.25 * b.x, 82),
              w - 82,
            ),
            y: (a.y + b.y) / 2 + (Math.abs(a.x - b.x) < 20 ? 0 : 34),
          }
        : {
            x: 0.25 * a.x + 0.5 * cx + 0.25 * b.x,
            y: 0.25 * a.y + 0.5 * cy + 0.25 * b.y,
          },
    };
  };
  const outline = biggest.map((i) => i.solution_outline).find(Boolean);

  return (
    <div className="space-y-3">
      <style>{MAP_CSS}</style>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-muted-foreground">
          {ur
            ? `${shown.length} masle · pi ne ${visible.length} connection dhoonde`
            : `${shown.length} ${shown.length === 1 ? "problem" : "problems"} · ${visible.length} ${visible.length === 1 ? "connection" : "connections"} found by pi`}
        </p>
        <ViewToggle list={asList} onChange={setAsList} lang={lang} />
      </div>
      {asList ? (
        <table className="w-full text-left text-sm">
          <caption className="sr-only">Problem map as a list</caption>
          <thead className="text-xs text-muted-foreground">
            <tr>
              <th className="py-1.5 pr-2 font-medium">
                {ur ? "Masla" : "Problem"}
              </th>
              <th className="py-1.5 pr-2 font-medium">
                {ur ? "Halat" : "Status"}
              </th>
              <th className="py-1.5 font-medium">
                {ur ? "Juda hua" : "Linked to"}
              </th>
            </tr>
          </thead>
          <tbody>
            {shown.map((issue) => {
              const partners = visible
                .filter(
                  (l) => l.a_title === issue.title || l.b_title === issue.title,
                )
                .map((l) =>
                  l.a_title === issue.title ? l.b_title : l.a_title,
                );
              return (
                <tr
                  key={issue.title}
                  className="border-t border-border align-top"
                >
                  <td className="py-2 pr-2 font-medium">{issue.title}</td>
                  <td className="py-2 pr-2">{STAGE[issue.stage][lang]}</td>
                  <td className="py-2 text-muted-foreground">
                    {partners.join(", ") || "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      ) : (
        <div
          ref={box}
          className="relative overflow-hidden rounded-2xl"
          style={{
            height: h,
            background:
              "radial-gradient(120% 90% at 50% 45%, #2c2655 0%, #1f1b3a 55%, #171430 100%)",
          }}
          onMouseLeave={() => setHover(null)}
        >
          <svg
            width={w}
            height={h}
            className="absolute inset-0"
            role="img"
            aria-label={`Problem map: ${shown.map((i) => i.title).join(", ")}`}
          >
            <defs>
              <pattern
                id="pimap-dots"
                width="22"
                height="22"
                patternUnits="userSpaceOnUse"
              >
                <circle
                  cx="1.5"
                  cy="1.5"
                  r="1.1"
                  fill="#ffffff"
                  opacity="0.07"
                />
              </pattern>
              <radialGradient id="pimap-hub" cx="50%" cy="40%" r="70%">
                <stop offset="0%" stopColor="#7b6bff" />
                <stop offset="100%" stopColor="#4a36e0" />
              </radialGradient>
            </defs>
            <rect width={w} height={h} fill="url(#pimap-dots)" />
            {/* One soft halo per group of requests one solution would fix. */}
            {[...groups.values()]
              .filter((g) => g.length >= 2 && visible.length)
              .map((g) => (
                <path
                  key={g[0].title}
                  className="pimap-line"
                  d={g
                    .map(
                      (i, k) =>
                        `${k ? "L" : "M"} ${at(i.title).x} ${at(i.title).y}`,
                    )
                    .join(" ")}
                  stroke="#8b7cff"
                  strokeOpacity="0.10"
                  strokeWidth={Math.min(130, w * 0.22)}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  fill="none"
                />
              ))}
            {hub &&
              biggest.map((i) => (
                <line
                  key={`spoke-${i.title}`}
                  className="pimap-line"
                  x1={at(i.title).x}
                  y1={at(i.title).y}
                  x2={center.x}
                  y2={center.y}
                  stroke="#b3a8ff"
                  strokeOpacity={related(i.title) ? 0.35 : 0.1}
                  strokeWidth="1.5"
                  strokeDasharray="2 5"
                />
              ))}
            {visible.map((link, k) => {
              const { d } = curve(link);
              const lit = related(link.a_title) && related(link.b_title);
              return (
                <g key={`${link.a_title}-${link.b_title}`}>
                  <path
                    d={d}
                    className="pimap-line"
                    style={{ animationDelay: `${200 + k * 120}ms` }}
                    fill="none"
                    stroke="#a99cff"
                    strokeOpacity={lit ? 0.95 : 0.2}
                    strokeWidth={
                      2 +
                      Math.max(
                        0,
                        Math.round(((link.confidence ?? 0.8) - 0.8) * 10),
                      )
                    }
                    strokeLinecap="round"
                    strokeDasharray={DASHED.has(link.type) ? "7 6" : undefined}
                  />
                  <path
                    d={d}
                    fill="none"
                    stroke="transparent"
                    strokeWidth="24"
                    className="cursor-pointer"
                    onClick={() => setPicked(link)}
                  />
                </g>
              );
            })}
          </svg>

          {hub && (
            <div
              className="pimap-node absolute flex flex-col items-center justify-center rounded-full text-center text-white shadow-[0_0_40px_rgba(123,107,255,0.45)]"
              style={{
                left: center.x - 54,
                top: center.y - 54,
                width: 108,
                height: 108,
                background:
                  "radial-gradient(circle at 50% 35%, #7b6bff, #4a36e0)",
                animationDelay: "350ms",
              }}
              title={outline || undefined}
            >
              <span className="text-[10px] font-semibold uppercase tracking-wide text-white/75">
                {ur ? "Ek hal" : "One solution"}
              </span>
              <span className="text-[13px] font-bold leading-tight">
                {ur ? `${merged} masle` : `fixes ${merged}`}
              </span>
            </div>
          )}

          {visible.map((link) => {
            const { label } = curve(link);
            const text = link.reason || (ur ? "juda hua" : "linked");
            return (
              <button
                key={`pill-${link.a_title}-${link.b_title}`}
                type="button"
                onClick={() => setPicked(link)}
                title={link.benefit || link.reason}
                className={cn(
                  "pimap-line absolute line-clamp-2 max-w-[150px] -translate-x-1/2 -translate-y-1/2 rounded-full border border-white/10 bg-[#332e5c]/95 px-2.5 py-1 text-center text-[11px] font-medium leading-tight text-[#ece9ff] shadow-lg transition-opacity hover:bg-[#433b78]",
                  !(related(link.a_title) && related(link.b_title)) &&
                    "opacity-30",
                )}
                style={{ left: label.x, top: label.y }}
              >
                {text}
              </button>
            );
          })}

          {nodes.map((node, k) => {
            const { issue, d } = node;
            const mark = markOf(issue);
            const steps = Math.min(7, Math.max(0, issue.journey_steps ?? 0));
            const r = d / 2 - 3;
            const around = 2 * Math.PI * r;
            const yourTurn =
              issue.ball_with === "client" && !issue.waiting_on_other_until;
            return (
              <button
                key={issue.title}
                type="button"
                className={cn(
                  "pimap-node absolute flex flex-col items-center text-center transition-opacity duration-200 focus:outline-none",
                  !related(issue.title) && "opacity-30",
                )}
                style={{
                  left: node.x - CARD_W / 2,
                  top: node.y - d / 2,
                  width: CARD_W,
                  animationDelay: `${k * 90}ms`,
                }}
                onMouseEnter={() => setHover(issue.title)}
                onFocus={() => setHover(issue.title)}
                onBlur={() => setHover(null)}
                onClick={() => onOpen?.(issue)}
                aria-label={`${issue.title}: ${STAGE[issue.stage][lang]}, ${steps} of 7 steps`}
              >
                <span
                  className="relative block"
                  style={{ width: d, height: d }}
                >
                  {yourTurn && (
                    <span
                      aria-hidden
                      className="pimap-pulse absolute inset-0 rounded-full border-[3px] border-[#f5a524]"
                    />
                  )}
                  <svg
                    width={d}
                    height={d}
                    className="absolute inset-0 -rotate-90"
                  >
                    <circle
                      cx={d / 2}
                      cy={d / 2}
                      r={r}
                      fill="none"
                      stroke="#ffffff"
                      strokeOpacity="0.14"
                      strokeWidth="4"
                    />
                    <circle
                      cx={d / 2}
                      cy={d / 2}
                      r={r}
                      fill="none"
                      stroke="#c4bbff"
                      strokeWidth="4"
                      strokeLinecap="round"
                      strokeDasharray={`${(around * steps) / 7} ${around}`}
                    />
                  </svg>
                  <span
                    className="absolute flex items-center justify-center rounded-full text-[13px] font-bold tabular-nums shadow-[inset_0_-6px_12px_rgba(0,0,0,0.18)] transition-transform hover:scale-105"
                    style={{
                      inset: 8,
                      background: mark.hollow ? "#1f1b3a" : mark.fill,
                      border: mark.hollow
                        ? `3px solid ${mark.stroke}`
                        : "2px solid rgba(255,255,255,0.9)",
                      color: mark.fill === MARK.you ? "#1b1830" : "#ffffff",
                    }}
                  >
                    {steps}/7
                  </span>
                </span>
                {issue.area && (
                  <span className="mt-1.5 text-[9.5px] font-semibold uppercase tracking-wider text-[#a9a4c7]">
                    {issue.area}
                  </span>
                )}
                <span className="line-clamp-2 text-[13px] font-semibold leading-snug text-white">
                  {issue.title}
                </span>
                <span className="mt-1 inline-flex items-center gap-1 whitespace-nowrap rounded-full bg-white/10 px-2 py-0.5 text-[10.5px] font-medium text-[#ddd9f5]">
                  <span
                    aria-hidden
                    className="size-1.5 rounded-full"
                    style={
                      mark.hollow
                        ? { border: `1.5px solid ${mark.stroke}` }
                        : { background: mark.fill }
                    }
                  />
                  {yourTurn ? TURN.you[lang] : STAGE[issue.stage][lang]}
                </span>
              </button>
            );
          })}
        </div>
      )}
      {picked && (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-border bg-surface-muted/60 p-3 text-sm">
          <div className="min-w-0">
            <p className="font-medium">
              {picked.a_title} + {picked.b_title}
            </p>
            <p className="text-muted-foreground">
              <LinkKind type={picked.type} lang={lang} />
              {picked.benefit
                ? ` · ${picked.benefit}`
                : picked.reason
                  ? ` · ${picked.reason}`
                  : ""}
            </p>
          </div>
          {onNotRelated && (
            <button
              type="button"
              className="inline-flex min-h-9 items-center gap-1.5 rounded-lg px-2.5 text-xs font-medium text-danger hover:bg-danger-soft"
              onClick={() => {
                onNotRelated(picked);
                setPicked(null);
              }}
            >
              <Unlink className="size-3.5" aria-hidden />
              {ur ? "Juda hua nahi" : "Not related"}
            </button>
          )}
        </div>
      )}
      <Legend lang={lang} />
      {merged >= 2 && (
        <p className="rounded-xl bg-accent px-3 py-2 text-sm font-medium text-accent-foreground">
          {ur
            ? `Ek hi system ${merged} masle hal kar sakta hai${outline ? `: ${outline}` : ""}`
            : `One system can fix ${merged === 3 ? "all three" : `${merged} of these`}${outline ? `: ${outline}` : ""}`}
        </p>
      )}
    </div>
  );
}

/* ------------------------------------------------------ complete journey */

/** Every request on the same seven-step road: where it is, whose turn, what's next. */
export function JourneyRoad<T extends CustomerIssue>({
  issues,
  lang,
  onOpen,
  subtitle,
  keepOrder = false,
}: {
  issues: T[];
  lang: Lang;
  onOpen?: (issue: T) => void;
  /** Extra line under the title, e.g. the business name. */
  subtitle?: (issue: T) => string;
  /** Keep the caller's order (it already sorts and filters). */
  keepOrder?: boolean;
}) {
  const ur = lang === "ur";
  const labels = JOURNEY_LABELS[ur ? "ur" : "en"];
  if (!issues.length) return null;
  const order = keepOrder
    ? issues
    : [...issues].sort(
        (a, b) =>
          Number(b.ball_with === "client") - Number(a.ball_with === "client") ||
          (b.journey_steps ?? 0) - (a.journey_steps ?? 0),
      );
  return (
    <div className="space-y-1">
      <div className="hidden grid-cols-[minmax(0,15rem)_minmax(0,1fr)] gap-4 pb-1 md:grid">
        <span />
        <div className="grid grid-cols-7">
          {labels.map((label, k) => (
            <span
              key={label}
              className="text-center text-[11px] font-medium text-muted-foreground"
            >
              <span className="block tabular-nums text-muted-foreground/70">
                {k + 1}
              </span>
              {label}
            </span>
          ))}
        </div>
      </div>
      <ul className="divide-y divide-border">
        {order.map((issue, n) => {
          const stopped = ["paused", "closed"].includes(issue.stage);
          const done = stopped
            ? 0
            : Math.min(7, Math.max(0, issue.journey_steps ?? 0));
          const current = done >= 7 ? -1 : done; // index of the step in progress
          const mark = markOf(issue);
          const yourTurn =
            issue.ball_with === "client" && !issue.waiting_on_other_until;
          const next =
            yourTurn && issue.open_question
              ? `${ur ? "Aap" : "You"}: ${issue.open_question}`
              : issue.next_step?.replace(/^(team|pi|you)\s*:\s*/i, "") || "";
          return (
            <li key={`${n}-${issue.title}`} className="py-3">
              <button
                type="button"
                onClick={() => onOpen?.(issue)}
                className="grid w-full grid-cols-1 items-center gap-2 rounded-xl text-left md:grid-cols-[minmax(0,15rem)_minmax(0,1fr)] md:gap-4"
              >
                <span className="min-w-0">
                  <span className="block truncate text-sm font-semibold">
                    {issue.title}
                  </span>
                  <span className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
                    {subtitle && <span>{subtitle(issue)} ·</span>}
                    <span>
                      {stopped
                        ? STAGE[issue.stage][lang]
                        : `${done}/7 · ${STAGE[issue.stage][lang]}`}
                    </span>
                    {!!issue.linked && (
                      <span>
                        ·{" "}
                        {ur
                          ? `${issue.linked} se juda`
                          : `linked to ${issue.linked}`}
                      </span>
                    )}
                  </span>
                </span>
                <span className="block">
                  <span className="relative grid grid-cols-7 items-center">
                    {/* the road */}
                    <span
                      aria-hidden
                      className="absolute left-[7%] right-[7%] top-1/2 h-0.5 -translate-y-1/2 rounded bg-border"
                    />
                    <span
                      aria-hidden
                      className="absolute left-[7%] top-1/2 h-1 -translate-y-1/2 rounded bg-[#5A47F5] transition-[width] duration-700"
                      style={{
                        width: `${(Math.max(0, Math.min(done, 7) - 1) / 6) * 86}%`,
                      }}
                    />
                    {labels.map((label, k) => {
                      const isDone = k < done;
                      const isNow = k === current && !stopped;
                      return (
                        <span
                          key={label}
                          className="relative flex justify-center"
                          title={label}
                        >
                          {isNow ? (
                            <span className="relative flex size-7 items-center justify-center">
                              {yourTurn && (
                                <span
                                  aria-hidden
                                  className="absolute inset-0 rounded-full bg-[#f5a524]/50 motion-safe:animate-ping"
                                  style={{ animationDuration: "2.2s" }}
                                />
                              )}
                              <span
                                className="relative flex size-7 items-center justify-center rounded-full text-[11px] font-bold ring-4 ring-background"
                                style={{
                                  background: mark.hollow
                                    ? "transparent"
                                    : mark.fill,
                                  border: mark.hollow
                                    ? `2px solid ${mark.stroke}`
                                    : undefined,
                                  color:
                                    mark.fill === MARK.you
                                      ? "#1b1830"
                                      : mark.hollow
                                        ? mark.stroke
                                        : "#fff",
                                }}
                              >
                                {k + 1}
                              </span>
                            </span>
                          ) : isDone ? (
                            <span className="relative flex size-4 items-center justify-center rounded-full bg-[#5A47F5] ring-4 ring-background">
                              <svg
                                viewBox="0 0 24 24"
                                className="size-2.5"
                                aria-hidden
                              >
                                <path
                                  d="M5 12.5l4.5 4.5L19 7.5"
                                  fill="none"
                                  stroke="#fff"
                                  strokeWidth="3.5"
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                />
                              </svg>
                            </span>
                          ) : (
                            <span className="relative size-3 rounded-full border-2 border-border-strong bg-background ring-4 ring-background" />
                          )}
                        </span>
                      );
                    })}
                  </span>
                  {next && !stopped && done < 7 && (
                    <span
                      className={cn(
                        "mt-2 block truncate rounded-lg px-2.5 py-1 text-xs",
                        yourTurn
                          ? "bg-warning-soft text-foreground"
                          : "bg-surface-muted text-foreground-secondary",
                      )}
                    >
                      <span className="font-medium">
                        {ur ? "Agla qadam: " : "Next: "}
                      </span>
                      {next}
                      {!yourTurn && issue.next_update_by
                        ? ` · ${ur ? "update" : "update by"} ${shortDay(issue.next_update_by)}`
                        : ""}
                    </span>
                  )}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/* ------------------------------------------------------- priority chart */

export function score(issue: CustomerIssue) {
  return (issue.urgency ?? 3) * (issue.impact ?? 3);
}

export function rankIssues(issues: CustomerIssue[]) {
  return issues
    .filter((i) => !["live", "closed", "paused"].includes(i.stage))
    .sort((a, b) => score(b) - score(a) || (b.linked ?? 0) - (a.linked ?? 0));
}

export function PriorityChart({
  issues,
  links,
  lang,
}: {
  issues: CustomerIssue[];
  links: IssueLink[];
  lang: Lang;
}) {
  const [asList, setAsList] = useState(false);
  const ranked = rankIssues(issues);
  if (!ranked.length) return null;
  const top = ranked[0];
  const fixes = links
    .filter((l) => l.a_title === top.title || l.b_title === top.title)
    .map((l) => (l.a_title === top.title ? l.b_title : l.a_title));
  const suggestion = (
    <p className="rounded-xl bg-[#1b1830] px-3 py-2.5 text-sm text-white">
      <span className="font-semibold">
        {lang === "ur" ? "pi ka mashwara: " : "pi's suggestion: "}
      </span>
      {lang === "ur"
        ? `Pehle "${top.title}" se shuru karein.`
        : `Start with "${top.title}".`}
      {fixes.length > 0 &&
        (lang === "ur"
          ? ` Is se "${fixes[0]}" bhi hal hota hai.`
          : ` It also fixes "${fixes[0]}".`)}
    </p>
  );
  // Under three open problems a chart says little: a ranked list instead.
  if (ranked.length < 3 || asList)
    return (
      <div className="space-y-3">
        {ranked.length >= 3 && (
          <div className="flex justify-end">
            <ViewToggle list={asList} onChange={setAsList} lang={lang} />
          </div>
        )}
        <ol className="space-y-2">
          {ranked.map((issue, n) => (
            <li key={issue.title} className="flex items-center gap-3 text-sm">
              <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-surface-muted text-xs font-semibold">
                {n + 1}
              </span>
              <span className="min-w-0 flex-1 truncate font-medium">
                {issue.title}
              </span>
              <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
                {lang === "ur" ? "score" : "score"} {score(issue)}
              </span>
            </li>
          ))}
        </ol>
        {suggestion}
      </div>
    );

  const size = 300;
  const pad = 34;
  const cell = (size - pad * 2) / 5;
  const pos = (v: number) => pad + (v - 0.5) * cell;
  const seen = new Map<string, number>();
  const marks = ranked.slice(0, 6).map((issue) => {
    const key = `${issue.urgency}-${issue.impact}`;
    const n = seen.get(key) ?? 0;
    seen.set(key, n + 1);
    // Requests with the same scores fan out around their cell instead of stacking.
    const angle = (n * 2 * Math.PI) / 3 + Math.PI / 4;
    const spread = n ? 0.28 * cell : 0;
    const r = Math.min(24, 10 * Math.sqrt(1 + (issue.linked ?? 0)));
    const x = pos(issue.urgency ?? 3) + spread * Math.cos(angle);
    const y = size - pos(issue.impact ?? 3) + spread * Math.sin(angle);
    // Label beside the bubble, on the side with more room.
    const right = x < size / 2 + 20;
    return { issue, x, y, r, right, ly: y + 3.5 };
  });
  // Labels on the same side never overlap: push them apart (12px apart at least).
  for (const side of [true, false]) {
    const same = marks
      .filter((m) => m.right === side)
      .sort((a, b) => a.ly - b.ly);
    same.forEach((m, k) => {
      if (k && m.ly - same[k - 1].ly < 12) m.ly = same[k - 1].ly + 12;
    });
  }
  const mid = pos(3.5);
  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <ViewToggle list={asList} onChange={setAsList} lang={lang} />
      </div>
      <svg
        viewBox={`0 0 ${size} ${size}`}
        className="mx-auto h-auto w-full max-w-sm"
        role="img"
        aria-label="Priority chart: urgency against business impact"
      >
        <rect
          x={mid}
          y={pad}
          width={size - pad - mid}
          height={size - pad - mid}
          fill="#5A47F5"
          opacity="0.08"
        />
        {[1, 2, 3, 4, 5].map((v) => (
          <g key={v} className="text-muted-foreground">
            <line
              x1={pos(v)}
              y1={pad}
              x2={pos(v)}
              y2={size - pad}
              stroke="currentColor"
              strokeOpacity="0.12"
            />
            <line
              x1={pad}
              y1={size - pos(v)}
              x2={size - pad}
              y2={size - pos(v)}
              stroke="currentColor"
              strokeOpacity="0.12"
            />
            <text
              x={pos(v)}
              y={size - 14}
              textAnchor="middle"
              fontSize="10"
              fill="currentColor"
            >
              {v}
            </text>
            <text
              x={18}
              y={size - pos(v) + 3}
              textAnchor="middle"
              fontSize="10"
              fill="currentColor"
            >
              {v}
            </text>
          </g>
        ))}
        <line
          x1={mid}
          y1={pad}
          x2={mid}
          y2={size - pad}
          stroke="currentColor"
          strokeOpacity="0.35"
          className="text-muted-foreground"
        />
        <line
          x1={pad}
          y1={size - mid}
          x2={size - pad}
          y2={size - mid}
          stroke="currentColor"
          strokeOpacity="0.35"
          className="text-muted-foreground"
        />
        <g
          className="text-muted-foreground"
          fontSize="9"
          fontWeight="600"
          fill="currentColor"
        >
          <text x={size - pad - 4} y={pad + 12} textAnchor="end">
            {lang === "ur" ? "PEHLE YE" : "FIX FIRST"}
          </text>
          <text x={pad + 4} y={pad + 12}>
            {lang === "ur" ? "AGLA PLAN" : "PLAN NEXT"}
          </text>
          <text x={size - pad - 4} y={size - pad - 6} textAnchor="end">
            {lang === "ur" ? "JALDI KAAM" : "QUICK WINS"}
          </text>
          <text x={pad + 4} y={size - pad - 6}>
            {lang === "ur" ? "BAAD MEIN" : "LATER"}
          </text>
        </g>
        {marks.map(({ issue, x, y, r, right, ly }) => {
          const mark = markOf(issue);
          return (
            <g key={issue.title}>
              <circle
                cx={x}
                cy={y}
                r={r}
                fill={mark.hollow ? "transparent" : mark.fill}
                stroke={mark.hollow ? mark.stroke : "#ffffff"}
                strokeWidth="2"
              />
              <text
                x={right ? x + r + 5 : x - r - 5}
                y={ly}
                textAnchor={right ? "start" : "end"}
                fontSize="10"
                fontWeight="600"
                fill="currentColor"
                className="text-foreground"
                stroke="var(--surface, #fff)"
                strokeWidth="3"
                paintOrder="stroke"
              >
                {shortTitle(issue.title, 20)}
              </text>
              <title>{`${issue.title}: urgency ${issue.urgency}, impact ${issue.impact}, ${issue.linked ?? 0} links`}</title>
            </g>
          );
        })}
      </svg>
      <p className="text-center text-xs text-muted-foreground">
        {lang === "ur"
          ? "Daayen = zyada jaldi · Upar = zyada asar · Bara circle = zyada connections"
          : "Right = more urgent · Up = more impact · Bigger = more connections"}
      </p>
      {suggestion}
    </div>
  );
}

/* -------------------------------------------------- problem -> solution */

function FlowBox({
  label,
  tone,
  children,
  dashed,
}: {
  label: string;
  tone: string;
  children: React.ReactNode;
  dashed?: boolean;
}) {
  return (
    <div
      className={cn(
        "rounded-xl border-2 px-3 py-2.5 text-center text-sm",
        dashed && "border-dashed",
        tone,
      )}
    >
      <p className="text-[10px] font-bold tracking-wide">{label}</p>
      <div className="mt-1 text-foreground">{children}</div>
    </div>
  );
}
export function SolutionFlow({
  issue,
  issues,
  links,
  lang,
}: {
  issue: CustomerIssue;
  issues: CustomerIssue[];
  links: IssueLink[];
  lang: Lang;
}) {
  const [mine, setMine] = useState(false);
  const group = issues.filter(
    (i) => i.solution_id && i.solution_id === issue.solution_id,
  );
  const members = group.length ? group : [issue];
  const ready = members.some((m) => m.root_cause || m.solution_outline);
  const reason = links.find(
    (l) =>
      members.some((m) => m.title === l.a_title) &&
      members.some((m) => m.title === l.b_title),
  );
  const builds = [
    ...new Set(members.map((m) => m.solution_outline).filter(Boolean)),
  ];
  const outcomes = [...new Set(members.map((m) => m.outcome).filter(Boolean))];
  const L = (en: string, ur: string) => (lang === "ur" ? ur : en);
  if (!ready)
    return (
      <div className="grid gap-2">
        {[
          L("PROBLEM", "MASLA"),
          L("ROOT CAUSE", "ASAL WAJAH"),
          L("WE'D BUILD", "HUM BANAYENGE"),
          L("OUTCOME", "NATEEJA"),
        ].map((label) => (
          <FlowBox
            key={label}
            label={label}
            tone="border-border text-muted-foreground"
            dashed
          >
            <span className="text-xs text-muted-foreground">
              {L("pi is working this out", "pi samajh raha hai")}
            </span>
          </FlowBox>
        ))}
      </div>
    );
  return (
    <div className="space-y-2">
      <div className="flex justify-end">
        <button
          type="button"
          onClick={() => setMine(!mine)}
          className="inline-flex min-h-9 items-center rounded-lg border border-border px-2.5 text-xs font-medium text-foreground-secondary hover:bg-surface-muted"
          aria-pressed={mine}
        >
          {mine
            ? L("pi's summary", "pi ka khulasa")
            : L("My words", "Mere alfaaz")}
        </button>
      </div>
      {/* Top to bottom: it fits a phone and the side panel; problems merge into one build. */}
      <div className="grid gap-2">
        <div className="space-y-2">
          {members.map((m) => (
            <div key={m.title} className="grid grid-cols-2 gap-2">
              <FlowBox
                label={L("PROBLEM", "MASLA")}
                tone="border-[#5A47F5]/60 text-[#5A47F5]"
              >
                {mine && m.original_words ? `“${m.original_words}”` : m.title}
              </FlowBox>
              <FlowBox
                label={L("ROOT CAUSE", "ASAL WAJAH")}
                tone="border-[#f5a524]/70 text-[#a46a00]"
              >
                {m.root_cause || "—"}
              </FlowBox>
            </div>
          ))}
          {reason && members.length > 1 && (
            <p className="text-center text-xs">
              <span className="rounded-full bg-[#1b1830] px-2.5 py-1 text-white">
                {L("linked by pi: ", "pi ne joda: ")}
                {reason.reason || <LinkKind type={reason.type} lang={lang} />}
              </span>
            </p>
          )}
        </div>
        <p aria-hidden className="text-center text-muted-foreground">
          ↓
        </p>
        <FlowBox
          label={L("WE'D BUILD", "HUM BANAYENGE")}
          tone="border-[#3b82f6]/70 text-[#1d5fd1]"
        >
          {builds.length ? builds.map((b) => <p key={b}>{b}</p>) : "—"}
        </FlowBox>
        <p aria-hidden className="text-center text-muted-foreground">
          ↓
        </p>
        <FlowBox
          label={L("OUTCOME", "NATEEJA")}
          tone="border-[#1f9d63]/70 text-[#1f9d63]"
        >
          {outcomes.length ? outcomes.map((o) => <p key={o}>{o}</p>) : "—"}
        </FlowBox>
      </div>
    </div>
  );
}

/* ------------------------------------------------------ activity timeline */

export type TimelineEvent = {
  at: string;
  actor: "pi" | "team" | "you";
  kind: string;
  title?: string;
  detail?: string;
  to?: string;
};

function eventText(e: TimelineEvent, lang: Lang) {
  const ur = lang === "ur";
  switch (e.kind) {
    case "problem.noted":
      return [ur ? "pi ne masla note kiya" : "pi noted a problem", e.title];
    case "stage.changed":
      return [
        ur ? "Halat badli" : "Status changed",
        `${e.title}${e.to && e.to in STAGE ? ` → ${STAGE[e.to as keyof typeof STAGE][lang]}` : ""}`,
      ];
    case "link.found":
      return [
        ur ? "pi ne masle jode" : "pi linked problems",
        `${e.title}${e.detail ? ` · ${e.detail}` : ""}`,
      ];
    case "pi.asked":
      return [ur ? "pi ne poocha" : "pi asked you", e.title];
    case "team.replied":
      return [ur ? "Team ne jawab diya" : "The team replied", ""];
    case "team.picked_up":
      return [ur ? "Team ne kaam uthaya" : "The team picked this up", ""];
    case "client.wrote":
      return [ur ? "Aap ne WhatsApp pe likha" : "You wrote on WhatsApp", ""];
    default:
      return [e.kind, e.title ?? ""];
  }
}

export function ActivityTimeline({
  events,
  lang,
  lastSeen,
}: {
  events: TimelineEvent[];
  lang: Lang;
  lastSeen?: string | null;
}) {
  const [who, setWho] = useState<"all" | TimelineEvent["actor"]>("all");
  const shown = events.filter((e) => who === "all" || e.actor === who);
  if (!events.length)
    return (
      <p className="py-4 text-sm text-muted-foreground">
        {lang === "ur"
          ? "Abhi kuch nahi. pi se baat karein, timeline bharti jayegi."
          : "Nothing yet. Your timeline fills up as you talk to pi."}
      </p>
    );
  const dayOf = (at: string) =>
    new Date(at).toDateString() === new Date().toDateString()
      ? lang === "ur"
        ? "Aaj"
        : "Today"
      : shortDay(at);
  return (
    <div className="space-y-3">
      <div
        className="flex flex-wrap gap-1.5"
        role="tablist"
        aria-label="Filter activity"
      >
        {(["all", "pi", "team", "you"] as const).map((key) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={who === key}
            onClick={() => setWho(key)}
            className={cn(
              "min-h-8 rounded-full border px-3 text-xs font-medium",
              who === key
                ? "border-foreground bg-foreground text-background"
                : "border-border",
            )}
          >
            {
              {
                all: lang === "ur" ? "Sab" : "All",
                pi: "pi",
                team: "Team",
                you: lang === "ur" ? "Aap" : "You",
              }[key]
            }
          </button>
        ))}
      </div>
      <ol className="space-y-0">
        {shown.map((e, i) => {
          const label = dayOf(e.at);
          const header =
            i === 0 || dayOf(shown[i - 1].at) !== label ? label : null;
          const fresh = Boolean(lastSeen && e.at > lastSeen);
          const [head, rest] = eventText(e, lang);
          return (
            <li key={`${e.at}-${i}`}>
              {header && (
                <p className="pb-1.5 pt-3 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  {header}
                </p>
              )}
              <div
                className={cn(
                  "flex gap-3 border-l-2 py-1.5 pl-3",
                  fresh ? "border-accent" : "border-transparent",
                )}
              >
                <span className="w-11 shrink-0 pt-1 text-xs text-muted-foreground tabular-nums">
                  {new Date(e.at).toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </span>
                <span
                  aria-hidden
                  className={cn(
                    "flex size-7 shrink-0 items-center justify-center rounded-full text-[10px] font-bold",
                    e.actor === "pi" && "bg-[#5A47F5] text-white",
                    e.actor === "team" && "bg-[#1b1830] text-white",
                    e.actor === "you" &&
                      "border-2 border-foreground text-foreground",
                  )}
                >
                  {e.actor === "pi"
                    ? "pi"
                    : e.actor === "team"
                      ? "T"
                      : lang === "ur"
                        ? "A"
                        : "Y"}
                </span>
                <p className="min-w-0 text-sm">
                  <span className="font-medium">{head}</span>
                  {rest ? (
                    <span className="text-foreground-secondary">: {rest}</span>
                  ) : null}
                  {fresh && (
                    <span className="ml-1.5 text-xs font-medium text-accent">
                      {lang === "ur" ? "naya" : "new"}
                    </span>
                  )}
                </p>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
