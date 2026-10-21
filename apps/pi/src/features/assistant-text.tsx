"use client";

import Link from "next/link";
import * as React from "react";

/*
 * The small Markdown subset pi's answers use: paragraphs, "- " and "1. " lists,
 * **bold**, *italic*, `code` and [links](/page). Rendered as React elements, never as
 * HTML, so model or customer text can't inject markup. Only in-app paths and https
 * links become links; anything else stays plain text.
 */

const INTERNAL = /^\/[A-Za-z0-9\-_/?=&#.%]*$/;
const INLINE =
  /(\*\*([^*\n]+?)\*\*|__([^_\n]+?)__|`([^`\n]+)`|\[([^\]\n]+)\]\(([^)\s]+)\)|(?<![\w*])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![\w*]))/g;

function inline(
  text: string,
  onNavigate: (() => void) | undefined,
  key = "i",
): React.ReactNode[] {
  const out: React.ReactNode[] = [];
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
      if (INTERNAL.test(href)) {
        out.push(
          <Link
            key={k}
            href={href}
            onClick={onNavigate}
            className="font-medium text-accent underline underline-offset-2"
          >
            {m[5]}
          </Link>,
        );
      } else if (/^https:\/\/[^\s]+$/.test(href)) {
        out.push(
          <a
            key={k}
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="font-medium text-accent underline underline-offset-2"
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

export function blocks(text: string): Block[] {
  const out: Block[] = [];
  let gap = false;
  for (const raw of text.replace(/\r\n?/g, "\n").split("\n")) {
    const line = raw.trimEnd();
    const prev = out[out.length - 1];
    const bullet = line.match(BULLET);
    const number = bullet ? null : line.match(NUMBER);
    const heading = line.match(HEADING);
    if (!line.trim()) {
      gap = true; // a blank line ends the paragraph or list above
      continue;
    }
    const joins = !gap;
    gap = false;
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
      // A wrapped list item continues the item above.
      prev.items[prev.items.length - 1] += ` ${line.trim()}`;
    } else {
      out.push({ kind: "p", lines: [line.trim()] });
    }
  }
  return out;
}

/** pi's answer text, formatted. */
export function AssistantText({
  text,
  onNavigate,
}: {
  text: string;
  onNavigate?: () => void;
}) {
  return (
    <div className="space-y-2 break-words text-sm leading-6">
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
                <React.Fragment key={j}>
                  {j ? <br /> : null}
                  {inline(line, onNavigate, `${key}-${j}`)}
                </React.Fragment>
              ))}
            </p>
          );
        const List = b.kind === "ul" ? "ul" : "ol";
        return (
          <List
            key={key}
            className={
              b.kind === "ul"
                ? "list-disc space-y-1 ps-5 marker:text-accent"
                : "list-decimal space-y-1 ps-5 marker:font-semibold marker:text-accent"
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
