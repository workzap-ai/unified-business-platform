"use client";

import Link from "next/link";
import { Fragment, type ReactNode } from "react";

/*
 * The small Markdown subset Agent Beta answers use: paragraphs, "- " and "1. " lists,
 * **bold**, *italic*, `code` and [links](/page). Rendered as React elements, never as
 * HTML, so model or record text can't inject markup. Only the agent's known pages and
 * https links become links; anything else stays plain text.
 */

const PAGES = new Set([
  "/customers",
  "/catalog",
  "/inventory",
  "/sales",
  "/quotes",
  "/orders",
  "/billing",
  "/finance",
  "/hr",
  "/settings/members",
  "/settings/integrations",
  "/workspace-agent",
  "/pi/inbox",
  "/pi/handoffs",
  "/pi/whatsapp",
]);
const INLINE =
  /(\*\*([^*\n]+?)\*\*|__([^_\n]+?)__|`([^`\n]+)`|\[([^\]\n]+)\]\(([^)\s]+)\)|(?<![\w*])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![\w*]))/g;

function inline(
  text: string,
  onNavigate: (() => void) | undefined,
  key: string,
): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  let n = 0;
  for (const m of text.matchAll(INLINE)) {
    const at = m.index ?? 0;
    if (at > last) out.push(text.slice(last, at));
    const k = `${key}-${n++}`;
    if (m[2] ?? m[3]) {
      out.push(
        <strong key={k} className="font-semibold text-foreground">
          {inline(m[2] ?? m[3], onNavigate, k)}
        </strong>,
      );
    } else if (m[4]) {
      out.push(
        <code
          key={k}
          className="rounded bg-surface-muted px-1 py-0.5 font-mono text-[0.85em]"
        >
          {m[4]}
        </code>,
      );
    } else if (m[5]) {
      const href = m[6];
      const page = href.split(/[?#]/)[0];
      if (PAGES.has(page)) {
        out.push(
          <Link
            key={k}
            href={href}
            onClick={onNavigate}
            className="font-medium text-primary underline underline-offset-2"
          >
            {m[5]}
          </Link>,
        );
      } else if (/^https:\/\/\S+$/.test(href)) {
        out.push(
          <a
            key={k}
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="font-medium text-primary underline underline-offset-2"
          >
            {m[5]}
          </a>,
        );
      } else {
        out.push(m[5]);
      }
    } else if (m[7]) {
      out.push(<em key={k}>{inline(m[7], onNavigate, k)}</em>);
    }
    last = at + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

type Block =
  | { kind: "p"; lines: string[] }
  | { kind: "h"; text: string }
  | { kind: "ul" | "ol"; items: string[] };

const BULLET = /^\s*[-*•]\s+(.*)$/;
const NUMBER = /^\s*\d+[.)]\s+(.*)$/;
const HEADING = /^\s*#{1,4}\s+(.*)$/;

function blocks(text: string): Block[] {
  const out: Block[] = [];
  let gap = false;
  for (const raw of text.replace(/\r\n?/g, "\n").split("\n")) {
    const line = raw.trimEnd();
    const prev = out[out.length - 1];
    if (!line.trim()) {
      gap = true; // a blank line ends the paragraph or list above
      continue;
    }
    const joins = !gap;
    gap = false;
    const bullet = line.match(BULLET);
    const number = bullet ? null : line.match(NUMBER);
    const heading = line.match(HEADING);
    if (bullet || number) {
      const kind = bullet ? "ul" : "ol";
      const item = (bullet ?? number)![1];
      if (prev && prev.kind === kind) prev.items.push(item);
      else out.push({ kind, items: [item] });
    } else if (heading) {
      out.push({ kind: "h", text: heading[1] });
    } else if (joins && prev && prev.kind === "p") {
      prev.lines.push(line.trim());
    } else if (joins && prev && (prev.kind === "ul" || prev.kind === "ol")) {
      prev.items[prev.items.length - 1] += ` ${line.trim()}`;
    } else {
      out.push({ kind: "p", lines: [line.trim()] });
    }
  }
  return out;
}

/** Agent Beta's answer text, formatted. */
export function AgentText({
  text,
  onNavigate,
}: {
  text: string;
  onNavigate?: () => void;
}) {
  return (
    <div className="space-y-2.5 break-words text-sm leading-6">
      {blocks(text).map((b, i) => {
        const key = `b${i}`;
        if (b.kind === "h")
          return (
            <p key={key} className="font-semibold text-foreground" dir="auto">
              {inline(b.text, onNavigate, key)}
            </p>
          );
        if (b.kind === "p")
          return (
            <p key={key} dir="auto">
              {b.lines.map((line, j) => (
                <Fragment key={j}>
                  {j ? <br /> : null}
                  {inline(line, onNavigate, `${key}-${j}`)}
                </Fragment>
              ))}
            </p>
          );
        const List = b.kind === "ul" ? "ul" : "ol";
        return (
          <List
            key={key}
            className={
              b.kind === "ul"
                ? "list-disc space-y-1 ps-5 marker:text-primary"
                : "list-decimal space-y-1 ps-5 marker:font-semibold marker:text-primary"
            }
          >
            {b.items.map((item, j) => (
              <li key={j} dir="auto">
                {inline(item, onNavigate, `${key}-${j}`)}
              </li>
            ))}
          </List>
        );
      })}
    </div>
  );
}

/** The whole chat as a Markdown document (Export). */
export function chatAsMarkdown(
  title: string,
  turns: { user?: string; reply?: { message: string } }[],
): string {
  const lines = [
    `# ${title}`,
    "",
    `Exported ${new Date().toLocaleString()}`,
    "",
  ];
  for (const t of turns) {
    if (t.user) lines.push(`**You:** ${t.user}`, "");
    if (t.reply) lines.push(`**Pi Agent:**`, "", t.reply.message, "");
  }
  return lines.join("\n");
}
