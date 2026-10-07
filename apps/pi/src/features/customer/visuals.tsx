"use client";

/**
 * pi Customer v2 visuals: Problem Map, priority chart, Problem -> Solution flow and the
 * activity timeline. Plain SVG/HTML (no chart library), so the same layout functions
 * also draw the WhatsApp cards. Colour always comes with a label: "Noted" is a hollow
 * ring, every mark has text, and every chart has a "View as list" table.
 */

import { useState } from "react";
import { List, Network, Unlink } from "lucide-react";

import type { CustomerIssue, IssueLink } from "@/lib/customer-api";
import { cn } from "@/lib/cn";
import { STAGE, TURN, shortDay } from "./shared";
import { MARK, layoutMap, markOf, shortTitle } from "./layout";

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
  const open = issues.filter((i) => !["live", "closed"].includes(i.stage));
  const shown = open.length ? open : issues;
  const groups = new Map<string, number>();
  shown.forEach((i) =>
    groups.set(i.solution_id ?? "", (groups.get(i.solution_id ?? "") ?? 0) + 1),
  );
  const merged = Math.max(0, ...groups.values());

  if (!issues.length)
    return (
      <div className="flex flex-col items-center gap-3 py-8 text-center">
        <span
          aria-hidden
          className="size-16 rounded-full border-2 border-dashed border-border-strong"
        />
        <p className="text-sm text-muted-foreground">
          {lang === "ur"
            ? "pi ko koi masla batayein, woh yahan nazar aayega."
            : "Tell pi about a problem and it appears here."}
        </p>
      </div>
    );

  const { nodes, regions, width, height } = layoutMap(shown);
  const at = (title: string) => nodes.find((n) => n.issue.title === title);
  const visible = links.filter((l) => at(l.a_title) && at(l.b_title));

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-muted-foreground">
          {lang === "ur"
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
                {lang === "ur" ? "Masla" : "Problem"}
              </th>
              <th className="py-1.5 pr-2 font-medium">
                {lang === "ur" ? "Halat" : "Status"}
              </th>
              <th className="py-1.5 font-medium">
                {lang === "ur" ? "Juda hua" : "Linked to"}
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
        <div className="-mx-1 overflow-x-auto rounded-xl bg-[#1b1830] p-1 [scrollbar-width:thin]">
          <svg
            viewBox={`0 0 ${width} ${height}`}
            className="h-auto min-w-[340px] w-full"
            role="img"
            aria-label={`Problem map: ${shown.map((i) => i.title).join(", ")}`}
          >
            {regions.map((region) => (
              <g key={region.name}>
                <rect
                  x={region.x}
                  y={region.y}
                  width={region.w}
                  height={region.h}
                  rx="14"
                  fill="#26223f"
                />
                <text
                  x={region.x + 14}
                  y={region.y + 22}
                  fill="#a9a4c7"
                  fontSize="11"
                  fontWeight="600"
                  letterSpacing="0.06em"
                >
                  {region.name.toUpperCase()}
                </text>
              </g>
            ))}
            {visible.map((link) => {
              const a = at(link.a_title)!;
              const b = at(link.b_title)!;
              const mx = (a.x + b.x) / 2;
              const my = (a.y + b.y) / 2;
              const label = shortTitle(link.reason || "", 28);
              return (
                <g
                  key={`${link.a_title}-${link.b_title}`}
                  className="cursor-pointer"
                  onClick={() => setPicked(link)}
                >
                  <line
                    x1={a.x}
                    y1={a.y}
                    x2={b.x}
                    y2={b.y}
                    stroke="#8b7cff"
                    strokeWidth={
                      2 + Math.round(((link.confidence ?? 0.8) - 0.8) * 10)
                    }
                    strokeDasharray={DASHED.has(link.type) ? "6 5" : undefined}
                  />
                  {/* 24px hit area */}
                  <line
                    x1={a.x}
                    y1={a.y}
                    x2={b.x}
                    y2={b.y}
                    stroke="transparent"
                    strokeWidth="24"
                  />
                  {label && (
                    <g>
                      <rect
                        x={mx - label.length * 3.4 - 8}
                        y={my - 11}
                        width={label.length * 6.8 + 16}
                        height="22"
                        rx="11"
                        fill="#332e55"
                      />
                      <text
                        x={mx}
                        y={my + 4}
                        textAnchor="middle"
                        fill="#e6e3f5"
                        fontSize="11"
                      >
                        {label}
                      </text>
                    </g>
                  )}
                </g>
              );
            })}
            {nodes.map((node) => {
              const mark = markOf(node.issue);
              return (
                <g
                  key={node.index}
                  className={onOpen ? "cursor-pointer" : undefined}
                  onClick={() => onOpen?.(node.issue)}
                >
                  <circle
                    cx={node.x}
                    cy={node.y}
                    r={node.r}
                    fill={mark.hollow ? "#1b1830" : mark.fill}
                    stroke={mark.hollow ? mark.stroke : "#ffffff"}
                    strokeWidth={mark.hollow ? 3 : 2}
                  />
                  <text
                    x={node.x}
                    y={node.y + node.r + 18}
                    textAnchor="middle"
                    fill="#ffffff"
                    fontSize="12"
                    fontWeight="600"
                  >
                    {shortTitle(node.issue.title)}
                  </text>
                  <title>{`${node.issue.title} · ${STAGE[node.issue.stage].en}`}</title>
                </g>
              );
            })}
          </svg>
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
              {lang === "ur" ? "Juda hua nahi" : "Not related"}
            </button>
          )}
        </div>
      )}
      <Legend lang={lang} />
      {merged >= 2 && (
        <p className="rounded-xl bg-accent px-3 py-2 text-sm font-medium text-accent-foreground">
          {lang === "ur"
            ? `Ek hi system ${merged} masle hal kar sakta hai →`
            : `One system can fix ${merged === 3 ? "all three" : `${merged} of these`} →`}
        </p>
      )}
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
    const offset = (n % 2 ? 1 : -1) * 0.18 * Math.ceil(n / 2) * cell;
    return {
      issue,
      x: pos(issue.urgency ?? 3) + offset,
      y: size - pos(issue.impact ?? 3) + offset,
      r: Math.min(28, 11 * Math.sqrt(1 + (issue.linked ?? 0))),
    };
  });
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
        {marks.map(({ issue, x, y, r }) => {
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
                x={x}
                y={y - r - 5}
                textAnchor="middle"
                fontSize="10"
                fontWeight="600"
                fill="currentColor"
                className="text-foreground"
              >
                {shortTitle(issue.title, 16)}
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
