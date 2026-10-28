"use client";

import { Brain } from "lucide-react";

import { Badge } from "@/components/ui";
import type { Message } from "@/lib/types";

const BOX_STATE: Record<string, string> = {
  collecting: "collecting",
  offered: "offered",
  in_review: "in review",
  sent: "sent",
};

/**
 * What pi had understood when it sent this message: the move and why, the problems it noted from
 * the owner's last message, what it guessed, and whether an offer was allowed. Read-only, from
 * data already stored (the API sends a whitelisted summary); collapsed until a team member opens it.
 */
export function MessageNotes({ message }: { message: Message }) {
  const u = message.understood;
  if (!u || message.sender_type !== "ai") return null;
  const problems = u.problems ?? [];
  const hypotheses = u.hypotheses ?? [];
  return (
    <details
      className="mt-1 rounded-lg border border-border bg-surface-muted/60 px-3 py-1.5 text-xs text-foreground-secondary"
      data-testid="message-notes"
    >
      <summary className="flex cursor-pointer list-none items-center gap-1.5 font-medium">
        <Brain className="size-3.5" aria-hidden />
        What pi understood
        {u.label ? <Badge tone="accent">{u.label}</Badge> : null}
        {problems.length ? (
          <span className="text-muted-foreground">
            {problems.length === 1
              ? "1 problem noted"
              : `${problems.length} problems noted`}
          </span>
        ) : null}
      </summary>
      <dl className="mt-2 space-y-2">
        {u.reason ? (
          <div>
            <dt className="font-semibold text-foreground">Why this reply</dt>
            <dd data-user-text>{u.reason}</dd>
          </div>
        ) : null}
        {problems.length ? (
          <div>
            <dt className="font-semibold text-foreground">Problems noted</dt>
            <dd>
              <ul className="list-inside list-disc">
                {problems.map((p, i) => (
                  <li key={`${p.number ?? i}-${p.title}`} data-user-text>
                    {p.number ? `P${p.number}: ` : ""}
                    {p.title}
                    {p.category ? (
                      <span className="text-muted-foreground">
                        {" "}
                        ({p.category.replace(/_/g, " ")})
                      </span>
                    ) : null}
                  </li>
                ))}
              </ul>
            </dd>
          </div>
        ) : null}
        {hypotheses.length ? (
          <div>
            <dt className="font-semibold text-foreground">pi&apos;s guess</dt>
            <dd>
              <ul className="list-inside list-disc">
                {hypotheses.map((h) => (
                  <li key={h.text} data-user-text>
                    {h.text}{" "}
                    <span className="text-muted-foreground">
                      ({h.confidence} confidence, not confirmed by the owner)
                    </span>
                  </li>
                ))}
              </ul>
            </dd>
          </div>
        ) : null}
        {u.offer ? (
          <div>
            <dt className="font-semibold text-foreground">Solution box</dt>
            <dd>
              {u.box_state
                ? `Box ${BOX_STATE[u.box_state] ?? u.box_state}. `
                : ""}
              {u.offer.allowed
                ? `The offer was allowed (rule ${u.offer.rule}).`
                : `No offer yet (rule ${u.offer.rule})${u.offer.blocked_reason ? `: ${u.offer.blocked_reason}` : "."}`}
            </dd>
          </div>
        ) : null}
      </dl>
    </details>
  );
}
