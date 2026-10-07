/**
 * The PNG card pi sends on WhatsApp (1080 x 1350): the same map / journey the customer
 * sees on the dashboard, drawn from a signed, expiring token. No chat text, no number.
 */

import { ImageResponse } from "next/og";

import type { CustomerIssue, IssueLink, Stage } from "@/lib/customer-api";
import {
  MARK,
  layoutMap,
  markOf,
  shortTitle,
} from "@/features/customer/layout";

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

function MapCard({ data, urdu }: { data: CardData; urdu: boolean }) {
  const open = data.issues
    .filter((i) => !["live", "closed"].includes(i.stage))
    .slice(0, 5);
  const shown = open.length ? open : data.issues.slice(0, 5);
  const { nodes, height } = layoutMap(shown, true);
  const at = (title: string) => nodes.find((n) => n.issue.title === title);
  const links = data.links.filter((l) => at(l.a_title) && at(l.b_title));
  const groups = new Map<string, number>();
  shown.forEach((i) =>
    groups.set(i.solution_id ?? "", (groups.get(i.solution_id ?? "") ?? 0) + 1),
  );
  const merged = Math.max(0, ...groups.values());
  const insight =
    merged >= 2
      ? urdu
        ? `Ek system ${merged} masle hal kar sakta hai.`
        : `One system can fix ${merged === 3 ? "all three" : `${merged} of them`}.`
      : urdu
        ? `pi ne ${links.length} connection dhoonde.`
        : `pi found ${links.length} connection${links.length === 1 ? "" : "s"}.`;
  const more = data.issues.length - shown.length;
  const boxW = 900;
  const boxH = 840;
  const viewH = Math.max(height, 420);
  const scale = Math.min(boxW / 500, boxH / viewH);
  const dx = (boxW - 500 * scale) / 2;
  const dy = (boxH - viewH * scale) / 2;
  return (
    <Frame
      title={urdu ? "Aap ka naqsha" : "Your Problem Map"}
      insight={insight}
      urdu={urdu}
    >
      <div
        style={{
          display: "flex",
          position: "relative",
          width: boxW,
          height: boxH,
        }}
      >
        <svg
          width={boxW}
          height={boxH}
          viewBox={`0 0 500 ${viewH}`}
          style={{ position: "absolute", left: 0, top: 0 }}
        >
          {links.map((link) => {
            const a = at(link.a_title)!;
            const b = at(link.b_title)!;
            const dashed =
              link.type === "part_of" || link.type === "depends_on";
            return (
              <line
                key={`${link.a_title}-${link.b_title}`}
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                stroke="#8b7cff"
                strokeWidth="4"
                strokeDasharray={dashed ? "10 8" : undefined}
              />
            );
          })}
          {nodes.map((node) => {
            const mark = markOf(node.issue);
            return (
              <g key={node.index}>
                <circle
                  cx={node.x}
                  cy={node.y}
                  r={node.r}
                  fill={mark.hollow ? INK : mark.fill}
                  stroke={mark.hollow ? mark.stroke : "#ffffff"}
                  strokeWidth={mark.hollow ? 5 : 3}
                />
              </g>
            );
          })}
        </svg>
        {nodes.map((node) => (
          <div
            key={node.index}
            style={{
              position: "absolute",
              display: "flex",
              justifyContent: "center",
              width: 460,
              left: dx + node.x * scale - 230,
              top: dy + (node.y + node.r) * scale + 8,
              fontSize: 44,
              fontWeight: 700,
              color: "#ffffff",
            }}
          >
            {shortTitle(node.issue.title, 20)}
          </div>
        ))}
        {more > 0 && (
          <div
            style={{
              position: "absolute",
              display: "flex",
              bottom: 8,
              left: 0,
              width: boxW,
              justifyContent: "center",
              fontSize: 34,
              color: "#a9a4c7",
            }}
          >
            {`+${more} more`}
          </div>
        )}
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
