"use client";

/**
 * The owner's problem map (Book 5, 4.9) and the Solution Box status card.
 *
 * The map is drawn in the browser from the same JSON pi draws on WhatsApp, so the two never
 * disagree: solid arrows for what the owner said or confirmed, dashed for pi's guess, a "Naya"
 * tag on what is new since the version before, greyed problems that are resolved. Phones get the
 * list (grouped by cluster); the picture needs room. Urdu, Arabic and Persian read right to left.
 * No amounts appear anywhere on this page.
 */

import { Fragment, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  Flag,
  List,
  Network,
  Pause,
  RotateCcw,
  Pencil,
} from "lucide-react";

import { errorText } from "@/lib/api";
import {
  customerGet,
  customerPost,
  type MapEditAction,
  type MapLinkData,
  type MapNodeData,
  type MapVersionSummary,
  type ProblemMapPayload,
  type ProblemMapVersion,
  type SolutionBoxStatus,
} from "@/lib/customer-api";
import { cn } from "@/lib/cn";
import { Badge, Button, Card, ErrorState, Skeleton } from "@/components/ui";
import { shortDay, useLang, usePrefs } from "./shared";

const RTL = new Set(["ur", "ar", "fa", "ps", "sd"]);

/** Words for the map page: English and Roman Urdu, like the rest of the portal. */
const WORDS = {
  title: { en: "Your problem map", ur: "Aap ke karobar ka naqsha" },
  latest: { en: "Latest", ur: "Taaza" },
  empty: {
    en: "Your map appears here once pi has noted a few problems in the chat.",
    ur: "Jab pi chat mein kuch masle note kar lega, naqsha yahan nazar aaye ga.",
  },
  newTag: { en: "New", ur: "Naya" },
  guess: { en: "pi's guess", ur: "pi ka andaza" },
  said: { en: "You said", ur: "Aap ne bataya" },
  list: { en: "List", ur: "List" },
  picture: { en: "Map", ur: "Naqsha" },
  versions: { en: "Versions", ur: "Versions" },
  viewing: {
    en: "You are looking at an older version.",
    ur: "Ye purana version hai.",
  },
  back: { en: "Back to the latest", ur: "Taaza par wapas" },
  resolved: { en: "Solved", ur: "Hal ho gaya" },
  parked: { en: "Parked", ur: "Chhor diya" },
  markSolved: { en: "Solved", ur: "Hal ho gaya" },
  park: { en: "Park it", ur: "Chhor dein" },
  reopen: { en: "Open again", ur: "Dobara kholein" },
  rename: { en: "Rename", ur: "Naam badlein" },
  startHere: { en: "Start here", ur: "Yahan se shuru" },
  clearStart: { en: "Not first", ur: "Pehle nahi" },
  first: { en: "Start here", ur: "Yahan se shuru" },
  save: { en: "Save", ur: "Save" },
  foot: {
    en: "Only the numbers you told pi. No names or personal details.",
    ur: "Sirf aap ke bataye hue number. Koi naam ya zaati tafseel nahi.",
  },
  guessKey: {
    en: "Dashed arrow: pi's guess, waiting for you to confirm.",
    ur: "Toti hui lakeer: pi ka andaza, aap ki tasdeeq baqi hai.",
  },
  group: { en: "Group", ur: "Jar" },
  problems: { en: "problems", ur: "masle" },
  links: { en: "links", ur: "jorr" },
} as const;

type Lang = "en" | "ur";
const t = (key: keyof typeof WORDS, lang: Lang) => WORDS[key][lang];

const LINK_WORDS: Record<string, [string, string]> = {
  causes: ["leads to", "is se hota hai"],
  worsens: ["makes worse", "is se barhta hai"],
  blocks: ["blocks", "rok deta hai"],
  competes: ["competes with", "muqabla karta hai"],
  same_root: ["same root as", "ek hi jar"],
  symptom_of: ["is a symptom of", "is ki alamat hai"],
};
const linkWord = (type: string, lang: Lang) =>
  (LINK_WORDS[type] ?? [type, type])[lang === "ur" ? 1 : 0];

/** One colour per category, always shown next to the category's name (never colour alone). */
const HUES = ["#5A47F5", "#1f9d63", "#c2410c", "#0e7490", "#a21caf"];
const categoryName = (key: string) =>
  key.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
function hueOf(categories: string[], key: string) {
  const order = [...new Set(categories)];
  return HUES[order.indexOf(key) % HUES.length] ?? HUES[0];
}

/* ------------------------------------------------------------------ layout */

export const CARD_W = 200;
export const CARD_H = 78;
const GAP_X = 90;
const GAP_Y = 28;
const PAD = 16;

type Placed = { node: MapNodeData; x: number; y: number };

/** Cause to effect, left to right (right to left for rtl): a column per step, in input order. */
export function layoutNodes(
  nodes: MapNodeData[],
  links: MapLinkData[],
  rtl = false,
) {
  const ids = nodes.map((n) => n.id);
  const edges = links
    .filter((l) =>
      ["causes", "worsens", "blocks", "symptom_of"].includes(l.type),
    )
    .map((l) => (l.type === "symptom_of" ? [l.to, l.from] : [l.from, l.to]))
    .filter(([a, b]) => ids.includes(a) && ids.includes(b) && a !== b);
  const rank: Record<string, number> = Object.fromEntries(
    ids.map((i) => [i, 0]),
  );
  for (let pass = 0; pass < ids.length; pass++) {
    let moved = false;
    for (const [a, b] of edges) {
      if (rank[b] < rank[a] + 1 && rank[a] + 1 < ids.length) {
        rank[b] = rank[a] + 1;
        moved = true;
      }
    }
    if (!moved) break;
  }
  const rows: Record<number, number> = {};
  const columns = Math.max(0, ...Object.values(rank)) + 1;
  const placed: Placed[] = nodes.map((node) => {
    const column = rank[node.id];
    const row = (rows[column] = (rows[column] ?? -1) + 1);
    const slot = rtl ? columns - 1 - column : column;
    return {
      node,
      x: PAD + slot * (CARD_W + GAP_X),
      y: PAD + row * (CARD_H + GAP_Y),
    };
  });
  const height =
    PAD * 2 +
    (Math.max(0, ...Object.values(rows)) + 1) * (CARD_H + GAP_Y) -
    GAP_Y;
  const width = PAD * 2 + columns * CARD_W + (columns - 1) * GAP_X;
  return { placed, width, height };
}

function wrap(text: string, max = 24): string[] {
  const lines: string[] = [];
  let line = "";
  for (const word of text.split(/\s+/)) {
    if (line && `${line} ${word}`.length > max) {
      lines.push(line);
      line = word;
    } else line = line ? `${line} ${word}` : word;
  }
  if (line) lines.push(line);
  return lines.slice(0, 2);
}

function edgePath(a: Placed, b: Placed) {
  const aRight = a.x < b.x;
  const sameColumn = a.x === b.x;
  if (sameColumn) {
    const down = a.y < b.y;
    const x = a.x + CARD_W / 2;
    const y1 = a.y + (down ? CARD_H : 0);
    const y2 = b.y + (down ? 0 : CARD_H);
    return `M ${x} ${y1} L ${x} ${y2}`;
  }
  const x1 = a.x + (aRight ? CARD_W : 0);
  const x2 = b.x + (aRight ? 0 : CARD_W);
  const y1 = a.y + CARD_H / 2;
  const y2 = b.y + CARD_H / 2;
  const mid = (x1 + x2) / 2;
  return `M ${x1} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${x2} ${y2}`;
}

function MapPicture({
  nodes,
  links,
  rtl,
  lang,
  selected,
  onSelect,
}: {
  nodes: MapNodeData[];
  links: MapLinkData[];
  rtl: boolean;
  lang: Lang;
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  const { placed, width, height } = layoutNodes(nodes, links, rtl);
  const at = Object.fromEntries(placed.map((p) => [p.node.id, p]));
  const categories = nodes.map((n) => n.category);
  return (
    <div className="overflow-x-auto rounded-xl bg-surface-muted/50 p-2">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        width={width}
        height={height}
        role="img"
        aria-label={t("title", lang)}
        className="mx-auto max-w-none"
      >
        <defs>
          <marker
            id="pm-arrow"
            viewBox="0 0 10 10"
            refX="9"
            refY="5"
            markerWidth="7"
            markerHeight="7"
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" fill="currentColor" />
          </marker>
        </defs>
        <g className="text-foreground-secondary">
          {links.map((l, i) => {
            const a = at[l.from];
            const b = at[l.to];
            if (!a || !b) return null;
            const guess = l.evidence === "pi_inferred";
            const plain = l.type === "competes" || l.type === "same_root";
            return (
              <path
                key={`${l.from}-${l.to}-${l.type}-${i}`}
                d={edgePath(a, b)}
                fill="none"
                stroke="currentColor"
                strokeWidth={2}
                strokeDasharray={guess ? "6 5" : undefined}
                markerEnd={plain ? undefined : "url(#pm-arrow)"}
              >
                <title>
                  {`${a.node.label} ${linkWord(l.type, lang)} ${b.node.label}${
                    guess ? ` (${t("guess", lang)})` : ""
                  }`}
                </title>
              </path>
            );
          })}
        </g>
        {placed.map(({ node, x, y }) => {
          const hue = hueOf(categories, node.category);
          const off = node.status !== "open";
          const on = selected === node.id;
          const textX = rtl ? x + CARD_W - 14 : x + 14;
          return (
            <g
              key={node.id}
              onClick={() => onSelect(node.id)}
              className="cursor-pointer"
              opacity={off ? 0.6 : 1}
              role="button"
              tabIndex={0}
              aria-label={node.label}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") onSelect(node.id);
              }}
            >
              <rect
                x={x}
                y={y}
                width={CARD_W}
                height={CARD_H}
                rx={12}
                className="fill-surface"
                stroke={on ? hue : "var(--border-strong)"}
                strokeWidth={on ? 3 : 1.5}
              />
              <rect
                x={rtl ? x + CARD_W - 6 : x}
                y={y}
                width={6}
                height={CARD_H}
                rx={3}
                fill={off ? "#9ca3af" : hue}
              />
              {wrap(node.label).map((line, i) => (
                <text
                  key={i}
                  x={textX}
                  y={y + 28 + i * 20}
                  textAnchor={rtl ? "end" : "start"}
                  className="fill-foreground text-[15px] font-medium"
                  style={{ direction: rtl ? "rtl" : "ltr" }}
                >
                  {line}
                </text>
              ))}
              {node.is_new && (
                <g>
                  <rect
                    x={rtl ? x + 6 : x + CARD_W - 52}
                    y={y - 9}
                    width={46}
                    height={18}
                    rx={9}
                    fill="#fbbf24"
                  />
                  <text
                    x={rtl ? x + 29 : x + CARD_W - 29}
                    y={y + 4}
                    textAnchor="middle"
                    className="text-[11px] font-semibold"
                    fill="#1f2933"
                  >
                    {t("newTag", lang)}
                  </text>
                </g>
              )}
              {node.rank !== undefined && !off && (
                <text
                  x={textX}
                  y={y + CARD_H - 10}
                  textAnchor={rtl ? "end" : "start"}
                  className="fill-muted-foreground text-[12px]"
                >
                  {node.rank === 1 ? t("first", lang) : `#${node.rank}`}
                </text>
              )}
              {off && (
                <text
                  x={textX}
                  y={y + CARD_H - 10}
                  textAnchor={rtl ? "end" : "start"}
                  className="fill-muted-foreground text-[12px]"
                >
                  {node.status === "resolved"
                    ? t("resolved", lang)
                    : t("parked", lang)}
                </text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

/* -------------------------------------------------------------------- list */

function MapList({
  data,
  lang,
  selected,
  onSelect,
}: {
  data: ProblemMapVersion["map"];
  lang: Lang;
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  const label = Object.fromEntries(data.nodes.map((n) => [n.id, n.label]));
  const inCluster = new Set(data.clusters.flatMap((c) => c.node_ids));
  const groups = [
    ...data.clusters.map((c) => ({
      key: c.id,
      title: c.title,
      nodes: data.nodes.filter((n) => c.node_ids.includes(n.id)),
    })),
    ...(data.nodes.some((n) => !inCluster.has(n.id))
      ? [
          {
            key: "alone",
            title: "",
            nodes: data.nodes.filter((n) => !inCluster.has(n.id)),
          },
        ]
      : []),
  ];
  return (
    <div className="space-y-4">
      {groups.map((g) => (
        <section key={g.key} aria-label={g.title || undefined}>
          {g.title && (
            <h3 className="mb-1.5 text-sm font-semibold text-muted-foreground">
              {t("group", lang)}: {g.title}
            </h3>
          )}
          <ul className="space-y-2">
            {g.nodes.map((n) => {
              const out = data.links.filter((l) => l.from === n.id);
              return (
                <li key={n.id}>
                  <button
                    type="button"
                    onClick={() => onSelect(n.id)}
                    aria-pressed={selected === n.id}
                    className={cn(
                      "w-full rounded-xl border bg-surface p-3 text-start transition-colors hover:bg-surface-muted/60",
                      selected === n.id ? "border-accent" : "border-border",
                      n.status !== "open" && "opacity-70",
                    )}
                  >
                    <span className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">{n.label}</span>
                      {n.is_new && (
                        <Badge tone="warning">{t("newTag", lang)}</Badge>
                      )}
                      {n.status === "resolved" && (
                        <Badge tone="success">{t("resolved", lang)}</Badge>
                      )}
                      {n.status === "parked" && (
                        <Badge>{t("parked", lang)}</Badge>
                      )}
                      {n.rank !== undefined && (
                        <Badge tone="accent">
                          {n.rank === 1 ? t("first", lang) : `#${n.rank}`}
                        </Badge>
                      )}
                    </span>
                    <span className="mt-0.5 block text-xs text-muted-foreground">
                      {categoryName(n.category)}
                    </span>
                    {n.facts.length > 0 && (
                      <span className="mt-1 block text-sm text-foreground-secondary">
                        {n.facts.join(" · ")}
                      </span>
                    )}
                    {out.map((l, i) => (
                      <span
                        key={i}
                        className="mt-1 block text-sm text-foreground-secondary"
                      >
                        {linkWord(l.type, lang)} {label[l.to]}
                        {l.evidence === "pi_inferred" && (
                          <span className="text-muted-foreground">
                            {" "}
                            ({t("guess", lang)})
                          </span>
                        )}
                      </span>
                    ))}
                  </button>
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </div>
  );
}

/* ----------------------------------------------------------------- editing */

function Editor({
  node,
  lang,
  busy,
  error,
  onEdit,
}: {
  node: MapNodeData;
  lang: Lang;
  busy: boolean;
  error: string | null;
  onEdit: (action: MapEditAction, label?: string, priority?: number) => void;
}) {
  const [name, setName] = useState(node.label);
  const [renaming, setRenaming] = useState(false);
  return (
    <div className="rounded-xl border border-border bg-surface-muted/40 p-3">
      <p className="mb-2 text-sm font-medium">{node.label}</p>
      {renaming ? (
        <form
          className="flex flex-wrap gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            onEdit("rename", name);
            setRenaming(false);
          }}
        >
          <input
            value={name}
            maxLength={60}
            onChange={(e) => setName(e.target.value)}
            aria-label={t("rename", lang)}
            className="h-10 min-w-0 flex-1 rounded-xl border border-border-strong bg-surface px-3 text-base focus-visible:outline-2 focus-visible:outline-ring"
          />
          <Button
            type="submit"
            size="sm"
            loading={busy}
            disabled={!name.trim()}
          >
            {t("save", lang)}
          </Button>
        </form>
      ) : (
        <div className="flex flex-wrap gap-2">
          {node.status !== "resolved" && (
            <Button
              variant="secondary"
              size="sm"
              disabled={busy}
              onClick={() => onEdit("resolve")}
            >
              <Check className="size-4" aria-hidden />
              {t("markSolved", lang)}
            </Button>
          )}
          {node.status === "open" && (
            <Button
              variant="secondary"
              size="sm"
              disabled={busy}
              onClick={() => onEdit("park")}
            >
              <Pause className="size-4" aria-hidden />
              {t("park", lang)}
            </Button>
          )}
          {node.status !== "open" && (
            <Button
              variant="secondary"
              size="sm"
              disabled={busy}
              onClick={() => onEdit("reopen")}
            >
              <RotateCcw className="size-4" aria-hidden />
              {t("reopen", lang)}
            </Button>
          )}
          {node.status === "open" && node.rank !== 1 && (
            <Button
              variant="secondary"
              size="sm"
              disabled={busy}
              onClick={() => onEdit("rank", undefined, 1)}
            >
              <Flag className="size-4" aria-hidden />
              {t("startHere", lang)}
            </Button>
          )}
          {node.rank !== undefined && (
            <Button
              variant="secondary"
              size="sm"
              disabled={busy}
              onClick={() => onEdit("unrank")}
            >
              {t("clearStart", lang)}
            </Button>
          )}
          <Button
            variant="secondary"
            size="sm"
            disabled={busy}
            onClick={() => setRenaming(true)}
          >
            <Pencil className="size-4" aria-hidden />
            {t("rename", lang)}
          </Button>
        </div>
      )}
      {error && (
        <p role="alert" className="mt-2 text-sm text-danger">
          {error}
        </p>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------- page */

export function ProblemMapSection({
  conversationId,
}: {
  conversationId: string;
}) {
  const client = useQueryClient();
  const lang = useLang();
  const prefs = usePrefs();
  const [view, setView] = useState<"picture" | "list">("picture");
  const [old, setOld] = useState<number | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const key = ["pi-customer", "map", conversationId];
  const map = useQuery({
    queryKey: key,
    queryFn: () =>
      customerGet<ProblemMapPayload>(`/conversations/${conversationId}/map`),
    refetchInterval: 15_000,
  });
  const older = useQuery({
    queryKey: [...key, old],
    queryFn: () =>
      customerGet<ProblemMapVersion>(
        `/conversations/${conversationId}/map/${old}`,
      ),
    enabled: old !== null,
  });
  const edit = useMutation({
    mutationFn: (v: {
      node: string;
      action: MapEditAction;
      label?: string;
      priority?: number;
    }) =>
      customerPost<ProblemMapPayload>(
        `/conversations/${conversationId}/map/problems/${v.node}`,
        {
          action: v.action,
          ...(v.label ? { label: v.label } : {}),
          ...(v.priority ? { priority: v.priority } : {}),
        },
      ),
    onSuccess: (data) => {
      client.setQueryData(key, data);
      void client.invalidateQueries({ queryKey: ["pi-customer", "box"] });
    },
  });

  if (map.isPending)
    return (
      <Skeleton className="h-64 w-full rounded-2xl" aria-label="Loading" />
    );
  if (map.isError)
    return (
      <ErrorState
        message={errorText(map.error)}
        onRetry={() => map.refetch()}
      />
    );
  const payload = map.data;
  const shown: ProblemMapVersion | null =
    old !== null && older.data ? older.data : payload.latest;
  const language =
    prefs.data?.language && prefs.data.language !== "auto"
      ? prefs.data.language
      : (payload.language ?? "en");
  const rtl = RTL.has(language);
  const viewingOld = old !== null && old !== payload.latest?.version;
  const node = shown?.map.nodes.find((n) => n.id === selected) ?? null;

  return (
    <Card className="p-4 sm:p-5" dir={rtl ? "rtl" : "ltr"}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">{t("title", lang)}</h2>
        {shown && (
          <div
            role="tablist"
            aria-label={t("title", lang)}
            className="hidden rounded-xl bg-surface-muted p-1 md:inline-flex"
          >
            {(
              [
                ["picture", Network],
                ["list", List],
              ] as const
            ).map(([k, Icon]) => (
              <button
                key={k}
                type="button"
                role="tab"
                aria-selected={view === k}
                onClick={() => setView(k)}
                className={cn(
                  "inline-flex min-h-9 items-center gap-1.5 rounded-lg px-3 text-sm font-medium",
                  view === k
                    ? "bg-surface text-foreground shadow-sm"
                    : "text-muted-foreground",
                )}
              >
                <Icon className="size-4" aria-hidden />
                {t(k, lang)}
              </button>
            ))}
          </div>
        )}
      </div>

      {!shown ? (
        <p className="py-8 text-center text-sm text-muted-foreground">
          {t("empty", lang)}
        </p>
      ) : (
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">
            v{shown.version} · {shown.problems} {t("problems", lang)} ·{" "}
            {shown.links} {t("links", lang)}
          </p>
          {viewingOld && (
            <div className="flex flex-wrap items-center gap-2 rounded-xl bg-info-soft px-3 py-2 text-sm text-info">
              {t("viewing", lang)}
              <Button variant="link" size="sm" onClick={() => setOld(null)}>
                {t("back", lang)}
              </Button>
            </div>
          )}
          {/* Phones always get the list; the picture needs room. */}
          <div className={cn("md:hidden")}>
            <MapList
              data={shown.map}
              lang={lang}
              selected={selected}
              onSelect={setSelected}
            />
          </div>
          <div className="hidden md:block">
            {view === "picture" ? (
              <MapPicture
                nodes={shown.map.nodes}
                links={shown.map.links}
                rtl={rtl}
                lang={lang}
                selected={selected}
                onSelect={setSelected}
              />
            ) : (
              <MapList
                data={shown.map}
                lang={lang}
                selected={selected}
                onSelect={setSelected}
              />
            )}
          </div>
          <p className="text-xs text-muted-foreground">{t("guessKey", lang)}</p>
          {node && !viewingOld && (
            <Editor
              key={`${node.id}-${node.label}-${node.status}`}
              node={node}
              lang={lang}
              busy={edit.isPending}
              error={edit.isError ? errorText(edit.error) : null}
              onEdit={(action, label, priority) =>
                edit.mutate({ node: node.id, action, label, priority })
              }
            />
          )}
          {payload.versions.length > 1 && (
            <div>
              <h3 className="mb-1.5 text-sm font-semibold text-muted-foreground">
                {t("versions", lang)}
              </h3>
              <ol
                className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1"
                aria-label={t("versions", lang)}
              >
                {payload.versions.map((v: MapVersionSummary, i) => (
                  <Fragment key={v.version}>
                    <li>
                      <button
                        type="button"
                        onClick={() => setOld(i === 0 ? null : v.version)}
                        aria-pressed={shown.version === v.version}
                        className={cn(
                          "min-h-10 shrink-0 rounded-xl border px-3 text-sm",
                          shown.version === v.version
                            ? "border-accent bg-accent-soft text-accent-soft-foreground"
                            : "border-border bg-surface text-foreground-secondary",
                        )}
                      >
                        v{v.version}
                        {i === 0 ? ` · ${t("latest", lang)}` : ""}
                        <span className="block text-xs text-muted-foreground">
                          {shortDay(v.shared_at ?? v.created_at)}
                        </span>
                      </button>
                    </li>
                  </Fragment>
                ))}
              </ol>
            </div>
          )}
          <p className="text-xs text-muted-foreground">{t("foot", lang)}</p>
        </div>
      )}
    </Card>
  );
}

/* ------------------------------------------------------------- solution box */

const BOX_STATE: Record<
  NonNullable<SolutionBoxStatus["state"]>,
  {
    en: string;
    ur: string;
    tone: "neutral" | "accent" | "info" | "success" | "warning";
  }
> = {
  collecting: {
    en: "Collecting your problems",
    ur: "Masle jama ho rahe hain",
    tone: "neutral",
  },
  ready: {
    en: "Ready to look at together",
    ur: "Saath dekhne ke liye tayyar",
    tone: "accent",
  },
  offered: { en: "Offered", ur: "Pesh kiya gaya", tone: "accent" },
  drafting: { en: "Being prepared", ur: "Tayyari ho rahi hai", tone: "info" },
  in_review: {
    en: "With our team to check",
    ur: "Team check kar rahi hai",
    tone: "info",
  },
  sent: { en: "Sent to you", ur: "Aap ko bhej diya", tone: "success" },
  accepted: { en: "Accepted", ur: "Manzoor", tone: "success" },
  declined: { en: "Declined", ur: "Mana kar diya", tone: "neutral" },
  changes_asked: {
    en: "Changes asked",
    ur: "Tabdeeli maangi",
    tone: "warning",
  },
  revised: { en: "Being revised", ur: "Dobara ban raha hai", tone: "info" },
};

/** Where the Solution Box stands, and whether a document has been approved or sent. Never a price. */
export function SolutionBoxCard({
  conversationId,
  business,
}: {
  conversationId: string;
  business?: string;
}) {
  const lang = useLang();
  const box = useQuery({
    queryKey: ["pi-customer", "box", conversationId],
    queryFn: () =>
      customerGet<SolutionBoxStatus>(`/conversations/${conversationId}/box`),
    refetchInterval: 30_000,
  });
  if (!box.data?.available || !box.data.state) return null;
  const state = BOX_STATE[box.data.state];
  const doc = box.data.document;
  return (
    <Card className="p-4 sm:p-5">
      <h2 className="font-semibold">
        {lang === "ur" ? "Solution Box" : "Solution Box"}
        {business ? ` · ${business}` : ""}
      </h2>
      <p className="mt-2 flex flex-wrap items-center gap-2">
        <Badge tone={state.tone}>{state[lang]}</Badge>
        <span className="text-xs text-muted-foreground">
          {lang === "ur" ? "Box version" : "Box version"} {box.data.version}
          {box.data.map_version ? ` · map v${box.data.map_version}` : ""}
        </span>
      </p>
      {doc && (
        <p className="mt-2 text-sm text-foreground-secondary">
          {doc.sent
            ? lang === "ur"
              ? `Document ${doc.ref} aap ko bhej diya gaya hai.`
              : `Document ${doc.ref} has been sent to you.`
            : lang === "ur"
              ? `Document ${doc.ref} manzoor ho chuka hai.`
              : `Document ${doc.ref} has been approved.`}
          {doc.sent && doc.sent_at ? ` (${shortDay(doc.sent_at)})` : ""}
        </p>
      )}
    </Card>
  );
}
