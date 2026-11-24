"use client";

/**
 * Nori Platform, "By person" view: the same cards as the board, grouped by the person who wrote
 * them. One block per person with their newest message first, repeats folded ("Hello x3") and
 * the chat one tap away. The board view (columns) stays beside it.
 */
import { useMemo } from "react";
import Link from "next/link";
import { ExternalLink, MessageCircle } from "lucide-react";
import { Avatar, Badge } from "@/components/ui/display";
import { cn } from "@/lib/utils";
import { NORI_ITEM_LABEL } from "./nori-board-panel";
import { inboxHref } from "./lib";
import type { BoardCard } from "../team-board-service";

const STATE: Record<BoardCard["column"], string> = {
  todo: "To do",
  doing: "In progress",
  waiting: "Waiting",
  done: "Done",
};

function ago(iso: string) {
  const minutes = Math.max(
    0,
    Math.round((Date.now() - new Date(iso).getTime()) / 60_000),
  );
  if (minutes < 2) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  if (minutes < 60 * 48) return `${Math.round(minutes / 60)}h ago`;
  return `${Math.round(minutes / 1440)}d ago`;
}

interface Person {
  key: string;
  name: string;
  workspace: string;
  phone: string;
  chat: string | null;
  cards: BoardCard[];
}

/** Cards grouped by phone (else chat, else name); the person with the newest card first. */
export function groupByPerson(cards: BoardCard[]): Person[] {
  const map = new Map<string, Person>();
  for (const card of cards) {
    const n = card.nori;
    const key =
      n?.phone_mask ||
      n?.conversation_id ||
      `${n?.workspace ?? ""}|${n?.person ?? ""}` ||
      "hand";
    let person = map.get(key);
    if (!person) {
      person = {
        key,
        name: n?.person || n?.phone_mask || "Added by hand",
        workspace: n?.workspace ?? "",
        phone: n?.phone_mask ?? "",
        chat: null,
        cards: [],
      };
      map.set(key, person);
    }
    person.cards.push(card);
  }
  const out = [...map.values()];
  for (const p of out) {
    p.cards.sort((a, b) => b.created_at.localeCompare(a.created_at));
    p.chat =
      p.cards.find((c) => c.nori?.conversation_id)?.nori?.conversation_id ??
      null;
  }
  return out.sort((a, b) =>
    b.cards[0].created_at.localeCompare(a.cards[0].created_at),
  );
}

/** Consecutive cards with the same title and state become one row with a count. */
function fold(cards: BoardCard[]) {
  const rows: { card: BoardCard; count: number }[] = [];
  for (const card of cards) {
    const last = rows.at(-1);
    if (
      last &&
      last.card.title.trim().toLowerCase() ===
        card.title.trim().toLowerCase() &&
      last.card.column === card.column
    )
      last.count += 1;
    else rows.push({ card, count: 1 });
  }
  return rows;
}

export function NoriPeopleView({ cards }: { cards: BoardCard[] }) {
  const people = useMemo(() => groupByPerson(cards), [cards]);
  const open = cards.filter((c) => c.column !== "done").length;
  if (people.length === 0) {
    return (
      <p className="rounded-md border border-dashed border-border px-3 py-8 text-center text-sm text-muted-foreground">
        Nothing from nori yet. When a nori user writes to pi, their message
        shows here.
      </p>
    );
  }
  return (
    <div className="space-y-3">
      <p className="text-[13px] text-muted-foreground">
        <span className="font-medium text-foreground tabular-nums">
          {people.length}
        </span>{" "}
        {people.length === 1 ? "person" : "people"} ·{" "}
        <span className="font-medium text-foreground tabular-nums">{open}</span>{" "}
        open {open === 1 ? "request" : "requests"}
      </p>
      <ul className="grid gap-3 lg:grid-cols-2">
        {people.map((person, index) => {
          const rows = fold(person.cards);
          const openCount = person.cards.filter(
            (c) => c.column !== "done",
          ).length;
          return (
            <li key={person.key} className="min-w-0">
              <details
                open={index < 2}
                className="rounded-lg border border-border bg-surface shadow-sm"
              >
                <summary className="flex cursor-pointer list-none items-center gap-3 p-3 [&::-webkit-details-marker]:hidden">
                  <Avatar name={person.name} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-semibold">
                      {person.name}
                    </span>
                    <span className="block truncate text-xs text-muted-foreground">
                      {[person.workspace, person.phone]
                        .filter(Boolean)
                        .join(" · ") || "No workspace"}
                      {" · "}
                      {ago(person.cards[0].created_at)}
                    </span>
                  </span>
                  <Badge tone={openCount ? "pi" : "neutral"}>
                    {openCount ? `${openCount} open` : "All done"}
                  </Badge>
                </summary>
                <div className="border-t border-border">
                  <ul className="divide-y divide-border">
                    {rows.map(({ card, count }) => (
                      <li
                        key={card.id}
                        className="flex flex-wrap items-start gap-x-2 gap-y-1 px-3 py-2.5"
                      >
                        <span className="min-w-0 flex-1 text-sm leading-snug break-words">
                          {card.title}
                          {count > 1 && (
                            <span className="ms-1.5 text-xs text-muted-foreground tabular-nums">
                              ×{count}
                            </span>
                          )}
                        </span>
                        {card.nori && (
                          <Badge tone="info">
                            {NORI_ITEM_LABEL[card.nori.item_kind]}
                          </Badge>
                        )}
                        <span
                          className={cn(
                            "text-xs tabular-nums",
                            card.column === "done"
                              ? "text-success"
                              : "text-muted-foreground",
                          )}
                        >
                          {STATE[card.column]} · {ago(card.created_at)}
                        </span>
                        {card.nori?.url && (
                          <a
                            href={card.nori.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
                          >
                            nori <ExternalLink className="size-3.5" />
                            <span className="sr-only">Open in nori</span>
                          </a>
                        )}
                      </li>
                    ))}
                  </ul>
                  {person.chat && (
                    <div className="border-t border-border p-2">
                      <Link
                        href={inboxHref(person.chat)}
                        className="inline-flex h-8 items-center gap-1.5 rounded-md px-2 text-xs font-medium text-primary hover:bg-surface-muted"
                      >
                        <MessageCircle className="size-4" aria-hidden="true" />{" "}
                        Open chat
                      </Link>
                    </div>
                  )}
                </div>
              </details>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
