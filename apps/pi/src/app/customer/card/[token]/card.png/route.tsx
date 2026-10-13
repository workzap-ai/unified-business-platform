/**
 * The PNG card pi sends on WhatsApp (1080 x 1350): the same map / journey the customer
 * sees on the dashboard, drawn from a signed, expiring token. No chat text, no number.
 */

import { ImageResponse } from "next/og";

import type { CustomerIssue, IssueLink, Stage } from "@/lib/customer-api";
import { MARK, markOf, shortTitle } from "@/features/customer/layout";

type CardData = {
  kind: "map" | "journey" | "flow";
  index: number;
  language: string;
  issues: CustomerIssue[];
  links: IssueLink[];
};

const W = 1080;
const H = 1350;
const INK = "#1b1830";

const STEPS = {
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

const STAGE_DONE: Record<Stage, number> = {
  noted: 1,
  need_answer: 1,
  on_it: 3,
  solution_ready: 4,
  building: 5,
  live: 7,
  paused: 0,
  closed: 0,
};

function Frame({
  title,
  insight,
  urdu,
  children,
}: {
  title: string;
  insight: string;
  urdu: boolean;
  children: React.ReactNode;
}) {
  const today = new Date().toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
  });
  return (
    <div
      style={{
        width: W,
        height: H,
        display: "flex",
        flexDirection: "column",
        background: INK,
        color: "#ffffff",
        padding: 64,
        fontFamily: "sans-serif",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", height: 120 - 64 }}>
        <div
          style={{
            display: "flex",
            width: 64,
            height: 64,
            borderRadius: 32,
            background: MARK.noted,
            alignItems: "center",
            justifyContent: "center",
            fontSize: 34,
            fontWeight: 700,
          }}
        >
          pi
        </div>
        <div
          style={{
            display: "flex",
            marginLeft: 24,
            fontSize: 48,
            fontWeight: 700,
          }}
        >
          {title}
        </div>
        <div
          style={{
            display: "flex",
            marginLeft: "auto",
            fontSize: 32,
            color: "#a9a4c7",
          }}
        >
          {today}
        </div>
      </div>
      <div
        style={{
          display: "flex",
          flex: 1,
          marginTop: 24,
          borderRadius: 32,
          background: "#26223f",
          alignItems: "center",
          justifyContent: "center",
          overflow: "hidden",
        }}
      >
        {children}
      </div>
      <div
        style={{
          display: "flex",
          justifyContent: "center",
          textAlign: "center",
          fontSize: 46,
          fontWeight: 700,
          marginTop: 32,
          lineHeight: 1.2,
        }}
      >
        {insight}
      </div>
      <div style={{ display: "flex", alignItems: "center", marginTop: 28 }}>
        <div style={{ display: "flex", fontSize: 30, color: "#a9a4c7" }}>
          pi Customer
        </div>
        <div
          style={{
            display: "flex",
            marginLeft: "auto",
            background: MARK.noted,
            borderRadius: 40,
            padding: "14px 32px",
            fontSize: 32,
            fontWeight: 700,
          }}
        >
          {urdu ? "Poora naqsha dekhein" : "See full map"}
        </div>
      </div>
    </div>
  );
}

/** Where a request stands, in words, with its mark colour. */
function statusOf(issue: CustomerIssue, urdu: boolean) {
  const mark = markOf(issue);
  if (mark.hollow) return { mark, label: urdu ? "Note hua" : "Noted" };
  if (issue.stage === "closed" || issue.stage === "live")
    return { mark, label: urdu ? "Mukammal" : "Done" };
  if (mark.fill === MARK.off)
    return { mark, label: urdu ? "Ruka hua" : "Paused" };
  if (issue.stage === "solution_ready")
    return { mark, label: urdu ? "Hal tayyar" : "Solution ready" };
  if (issue.ball_with === "client")
    return { mark, label: urdu ? "Aap ka jawab chahiye" : "Waiting on you" };
  return { mark, label: urdu ? "Hum kaam kar rahe hain" : "We're on it" };
}

/** The Problem Map card: each request on its own row (full name, where it stands and
 * how far it has come), pi's connections as lines between the rows, a count per status
 * at the top and one line on what matters most. */
function MapCard({ data, urdu }: { data: CardData; urdu: boolean }) {
  const open = data.issues.filter((i) => !["live", "closed"].includes(i.stage));
  const shown = (open.length ? open : data.issues).slice(0, 5);
  const more = data.issues.length - shown.length;
  const rows = shown.map((issue) => ({ issue, ...statusOf(issue, urdu) }));
  const at = (title: string) => shown.findIndex((i) => i.title === title);
  const links = data.links.filter(
    (l) => at(l.a_title) >= 0 && at(l.b_title) >= 0,
  );
  const groups = new Map<string, number>();
  shown.forEach((i) => {
    if (i.solution_id)
      groups.set(i.solution_id, (groups.get(i.solution_id) ?? 0) + 1);
  });
  const merged = Math.max(0, ...groups.values());
  const waiting = rows.filter((r) => r.mark.fill === MARK.you).length;
  const working = rows.filter((r) => r.mark.fill === MARK.us).length;
  const insight =
    merged >= 2
      ? urdu
        ? `Ek system ${merged} masle hal kar sakta hai.`
        : `One system can fix ${merged === 3 ? "all three" : `${merged} of them`}.`
      : waiting
        ? urdu
          ? `${waiting} request par aap ka jawab chahiye.`
          : `${waiting} request${waiting === 1 ? " needs" : "s need"} your answer.`
        : working
          ? urdu
            ? `${working} requests par kaam jaari hai.`
            : `We're working on ${working} of your ${data.issues.length} requests.`
          : urdu
            ? `Aap ki ${data.issues.length} requests ek nazar mein.`
            : `Your ${data.issues.length} requests at a glance.`;
  // A count per status, in the order the customer cares about.
  const chips = [
    {
      label: urdu ? "aap ka jawab" : "waiting on you",
      color: MARK.you,
      hollow: false,
    },
    {
      label: urdu ? "kaam jaari" : "we're on it",
      color: MARK.us,
      hollow: false,
    },
    {
      label: urdu ? "hal tayyar" : "solution ready",
      color: MARK.ready,
      hollow: false,
    },
    { label: urdu ? "note hua" : "noted", color: MARK.noted, hollow: true },
  ]
    .map((c) => ({
      ...c,
      count: rows.filter((r) =>
        c.hollow ? r.mark.hollow : !r.mark.hollow && r.mark.fill === c.color,
      ).length,
    }))
    .filter((c) => c.count > 0);

  // The rows share the panel's height; a node sits at the start of each row.
  // The panel fills the card; the status chips sit on top as its legend.
  const panelW = W - 128;
  const panelH = 880;
  const top = 116;
  const pad = 24;
  const rowH = Math.min(200, (panelH - top - pad) / Math.max(rows.length, 1));
  const nodeX = 84;
  const nodeY = (i: number) => top + i * rowH + rowH / 2;
  const twoLines = rows.length <= 4;

  return (
    <Frame
      title={urdu ? "Aap ka naqsha" : "Your Problem Map"}
      insight={insight}
      urdu={urdu}
    >
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          width: panelW,
          height: panelH,
          position: "relative",
        }}
      >
        <svg
          width={panelW}
          height={panelH}
          viewBox={`0 0 ${panelW} ${panelH}`}
          style={{ position: "absolute", left: 0, top: 0 }}
        >
          {links.map((link, k) => {
            const ya = nodeY(at(link.a_title));
            const yb = nodeY(at(link.b_title));
            const reach = 26 + (k % 3) * 18;
            const dashed =
              link.type === "part_of" || link.type === "depends_on";
            return (
              <path
                key={`${link.a_title}-${link.b_title}`}
                d={`M ${nodeX} ${ya} C ${nodeX - reach * 2} ${ya}, ${nodeX - reach * 2} ${yb}, ${nodeX} ${yb}`}
                fill="none"
                stroke="#a99cff"
                strokeWidth="5"
                strokeDasharray={dashed ? "12 10" : undefined}
              />
            );
          })}
          {rows.map((row, i) => {
            const r = 20 + 3 * Math.min(Math.max(row.issue.impact ?? 3, 1), 5);
            return (
              <circle
                key={row.issue.title}
                cx={nodeX}
                cy={nodeY(i)}
                r={r}
                fill={row.mark.hollow ? INK : row.mark.fill}
                stroke={row.mark.hollow ? row.mark.stroke : "#ffffff"}
                strokeWidth={row.mark.hollow ? 6 : 4}
              />
            );
          })}
        </svg>
        {rows.map((row, i) => {
          const done = STAGE_DONE[row.issue.stage] ?? 0;
          return (
            <div
              key={row.issue.title}
              style={{
                display: "flex",
                flexDirection: "column",
                justifyContent: "center",
                position: "absolute",
                left: nodeX + 64,
                top: top + i * rowH,
                width: panelW - nodeX - 64 - 36,
                height: rowH,
              }}
            >
              <div
                style={{
                  display: "flex",
                  fontSize: 40,
                  fontWeight: 700,
                  lineHeight: 1.15,
                  color: "#ffffff",
                }}
              >
                {shortTitle(row.issue.title, twoLines ? 62 : 32)}
              </div>
              <div
                style={{ display: "flex", alignItems: "center", marginTop: 10 }}
              >
                <div
                  style={{
                    display: "flex",
                    fontSize: 32,
                    fontWeight: 600,
                    color: row.mark.hollow ? "#c9c1ff" : row.mark.fill,
                  }}
                >
                  {row.label}
                </div>
                <div style={{ display: "flex", marginLeft: "auto" }}>
                  {Array.from({ length: 7 }, (_, s) => (
                    <div
                      key={s}
                      style={{
                        display: "flex",
                        width: 30,
                        height: 12,
                        marginLeft: 6,
                        borderRadius: 6,
                        background:
                          s < done
                            ? row.mark.hollow
                              ? MARK.noted
                              : row.mark.fill
                            : "#3a3558",
                      }}
                    />
                  ))}
                </div>
              </div>
            </div>
          );
        })}
        {/* Counts per status, and how many more requests the customer has. */}
        <div
          style={{
            display: "flex",
            position: "absolute",
            left: 0,
            top: 0,
            width: panelW,
            height: top - 16,
            alignItems: "center",
            justifyContent: "center",
            borderBottom: "2px solid #34305a",
          }}
        >
          {chips.map((c) => (
            <div
              key={c.label}
              style={{
                display: "flex",
                alignItems: "center",
                marginLeft: 10,
                marginRight: 10,
                padding: "6px 18px",
                borderRadius: 30,
                background: "#1b1830",
                fontSize: 32,
                color: "#e7e4f7",
              }}
            >
              <div
                style={{
                  display: "flex",
                  width: 22,
                  height: 22,
                  borderRadius: 11,
                  marginRight: 12,
                  background: c.hollow ? "transparent" : c.color,
                  border: c.hollow ? `5px solid ${c.color}` : "none",
                }}
              />
              {`${c.count} ${c.label}`}
            </div>
          ))}
          {more > 0 && (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                marginLeft: 10,
                padding: "6px 18px",
                fontSize: 32,
                color: "#a9a4c7",
              }}
            >
              {`+${more} ${urdu ? "aur" : "more"}`}
            </div>
          )}
        </div>
      </div>
    </Frame>
  );
}

function JourneyCard({ data, urdu }: { data: CardData; urdu: boolean }) {
  const issue = data.issues[data.index] ?? data.issues[0];
  const done = STAGE_DONE[issue.stage] ?? 0;
  const current = Math.min(done + 1, 7);
  const turnColour =
    issue.ball_with === "client"
      ? MARK.you
      : issue.stage === "solution_ready"
        ? MARK.ready
        : MARK.us;
  const steps = STEPS[urdu ? "ur" : "en"];
  const insight =
    issue.ball_with === "client" && issue.open_question
      ? `${urdu ? "Aap" : "Next: you"} · ${shortTitle(issue.open_question, 60)}`
      : `${urdu ? "Agla qadam" : "Next"} · ${shortTitle(issue.next_step.replace(/^(team|pi|you)\s*:\s*/i, ""), 60)}`;
  return (
    <Frame title={shortTitle(issue.title, 26)} insight={insight} urdu={urdu}>
      <div style={{ display: "flex", flexDirection: "column", width: 760 }}>
        {steps.map((label, i) => {
          const step = i + 1;
          const isDone = step <= done;
          const isNow = step === current && done < 7;
          return (
            <div
              key={label}
              style={{ display: "flex", alignItems: "center", height: 104 }}
            >
              <div
                style={{
                  display: "flex",
                  width: isNow ? 76 : 60,
                  height: isNow ? 76 : 60,
                  borderRadius: 40,
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 30,
                  fontWeight: 700,
                  background: isDone
                    ? MARK.noted
                    : isNow
                      ? turnColour
                      : "transparent",
                  border: isDone || isNow ? "none" : "4px solid #6f6a8f",
                  color: isNow && turnColour === MARK.you ? INK : "#ffffff",
                }}
              >
                {isDone ? (
                  <svg width="30" height="30" viewBox="0 0 24 24">
                    <path
                      d="M5 12.5l4.5 4.5L19 7.5"
                      fill="none"
                      stroke="#ffffff"
                      strokeWidth="3"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                ) : (
                  String(step)
                )}
              </div>
              <div
                style={{
                  display: "flex",
                  marginLeft: 36,
                  fontSize: isNow ? 46 : 40,
                  fontWeight: isNow ? 700 : 500,
                  color: isDone || isNow ? "#ffffff" : "#8f8aad",
                }}
              >
                {label}
              </div>
            </div>
          );
        })}
      </div>
    </Frame>
  );
}

export async function GET(
  request: Request,
  ctx: { params: Promise<{ token: string }> },
) {
  const { token } = await ctx.params;
  const source = new URL(
    `/api/v1/pi-app/customer-portal/card/${encodeURIComponent(token)}`,
    request.url,
  );
  const response = await fetch(source, { cache: "no-store" });
  if (!response.ok)
    return new Response("This card has expired.", { status: 404 });
  const data = (await response.json()) as CardData;
  if (!data.issues?.length)
    return new Response("Nothing to show yet.", { status: 404 });
  const urdu = ["roman_ur", "ur"].includes(data.language);
  return new ImageResponse(
    data.kind === "map" ? (
      <MapCard data={data} urdu={urdu} />
    ) : (
      <JourneyCard data={data} urdu={urdu} />
    ),
    {
      width: W,
      height: H,
      headers: {
        "Cache-Control": "public, max-age=300",
        "Referrer-Policy": "no-referrer",
      },
    },
  );
}
