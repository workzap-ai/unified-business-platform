"use client";

import { FlaskConical, RotateCcw, Send, ShieldAlert } from "lucide-react";
import * as React from "react";

import { Badge, Button, Notice, Switch, Textarea, cn } from "@/components/ui";
import { errorText, post } from "@/lib/api";

interface PreviewResult {
  simulated: true;
  status: "ok" | "blocked" | "handoff" | "action" | "ai_unavailable";
  reply: string | null;
  language?: string;
  team_summary?: string;
  simulated_actions: string[];
  blocked_reason: string | null;
  knowledge_used: string[];
  drafts_used: string[];
  price_rule: string;
}

interface Turn {
  role: "customer" | "pi";
  text: string;
  result?: PreviewResult;
}

const BLOCKED: Record<string, string> = {
  SERVICE_PRICE_BLOCKED:
    "pi's reply mentioned a price, which your price rules don't allow, so it would go to your team instead.",
  PRICE_POLICY_BLOCKED:
    "pi's reply mentioned a price, which your price rules don't allow, so it would go to your team instead.",
  UNVERIFIABLE_AMOUNT:
    "pi's reply had an amount it couldn't check against your catalog, so it would go to your team.",
  UNSUPPORTED_FACT:
    "pi's reply had a figure that isn't in your approved information, so it would go to your team.",
  LEAK_BLOCKED: "The reply was blocked by a safety check.",
};

export function TestConversation({
  includeDraftsToggle = false,
}: {
  includeDraftsToggle?: boolean;
}) {
  const [turns, setTurns] = React.useState<Turn[]>([]);
  const [text, setText] = React.useState("");
  const [drafts, setDrafts] = React.useState(includeDraftsToggle);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const endRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    endRef.current?.scrollIntoView({ block: "nearest" });
  }, [turns]);

  async function send(event?: React.FormEvent) {
    event?.preventDefault();
    const message = text.trim();
    if (!message || busy) return;
    const history = turns
      .filter((t) => t.text)
      .map(({ role, text: t }) => ({ role, text: t }));
    setTurns((all) => [...all, { role: "customer", text: message }]);
    setText("");
    setBusy(true);
    setError(null);
    try {
      const result = await post<PreviewResult>("/playground", {
        message,
        history: history.slice(-20),
        include_drafts: drafts,
      });
      setTurns((all) => [
        ...all,
        { role: "pi", text: result.reply ?? "", result },
      ]);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-xl border border-border bg-surface-muted">
      <div className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
        <Badge tone="warning">
          <FlaskConical className="size-3.5" aria-hidden /> Test only — nothing
          is sent
        </Badge>
        {includeDraftsToggle ? (
          <label
            htmlFor="drafts"
            className="ms-auto flex items-center gap-2 text-sm"
          >
            <Switch
              id="drafts"
              checked={drafts}
              onCheckedChange={setDrafts}
              label="Include unpublished drafts"
            />
            Include unpublished drafts
          </label>
        ) : null}
        <Button
          variant="ghost"
          size="sm"
          className={includeDraftsToggle ? "" : "ms-auto"}
          onClick={() => setTurns([])}
          disabled={!turns.length}
        >
          <RotateCcw className="size-4" aria-hidden /> Start over
        </Button>
      </div>
      <div
        className="max-h-[28rem] min-h-48 space-y-3 overflow-y-auto p-4"
        aria-live="polite"
      >
        {turns.length === 0 ? (
          <p className="py-10 text-center text-sm text-muted-foreground">
            Try &ldquo;What do you offer?&rdquo; or ask in another language.
          </p>
        ) : null}
        {turns.map((turn, index) => (
          <div
            key={index}
            className={cn(
              "flex",
              turn.role === "customer" ? "justify-end" : "justify-start",
            )}
          >
            <div className="max-w-[85%] space-y-2">
              {turn.text ? (
                <div
                  data-user-text
                  className={cn(
                    "whitespace-pre-line rounded-2xl px-4 py-2.5 text-[15px] shadow-sm",
                    turn.role === "customer"
                      ? "rounded-ee-md bg-bubble-customer"
                      : "rounded-es-md bg-bubble-pi",
                  )}
                >
                  {turn.text}
                </div>
              ) : null}
              {turn.result ? <ResultDetails result={turn.result} /> : null}
            </div>
          </div>
        ))}
        {busy ? (
          <p className="text-sm text-muted-foreground">pi is thinking…</p>
        ) : null}
        <div ref={endRef} />
      </div>
      {error ? (
        <div className="px-4 pb-2">
          <Notice tone="danger">{error}</Notice>
        </div>
      ) : null}
      <form
        onSubmit={send}
        className="flex items-end gap-2 border-t border-border p-3"
      >
        <label htmlFor="test-message" className="sr-only">
          Message as a customer
        </label>
        <Textarea
          id="test-message"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send();
            }
          }}
          placeholder="Write as a customer…"
          className="min-h-11 flex-1 resize-none"
          rows={1}
          maxLength={2000}
        />
        <Button
          type="submit"
          size="icon"
          aria-label="Send test message"
          loading={busy}
          disabled={!text.trim()}
        >
          {busy ? null : <Send className="size-4" aria-hidden />}
        </Button>
      </form>
    </div>
  );
}

function ResultDetails({ result }: { result: PreviewResult }) {
  return (
    <div className="space-y-2 text-sm">
      {result.status === "ai_unavailable" ? (
        <Notice tone="warning">
          pi&apos;s AI isn&apos;t available right now, so a real customer would
          be handed to your team.
        </Notice>
      ) : null}
      {result.status === "blocked" ? (
        <div className="flex gap-2 rounded-lg border border-warning/30 bg-warning-soft p-3">
          <ShieldAlert className="size-4 shrink-0 text-warning" aria-hidden />
          <p>
            {BLOCKED[result.blocked_reason ?? ""] ??
              "This reply would go to your team for review."}
          </p>
        </div>
      ) : null}
      {result.status === "handoff" ? (
        <p className="text-muted-foreground">
          pi doesn&apos;t know this yet. It would ask you and tell the customer
          your team will reply.
        </p>
      ) : null}
      {result.simulated_actions.length ? (
        <div className="rounded-lg border border-dashed border-border-strong bg-surface p-3">
          <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Would do (simulated)
          </p>
          <ul className="list-disc space-y-0.5 ps-5">
            {result.simulated_actions.map((action) => (
              <li key={action}>{action}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {result.knowledge_used.length ? (
        <p className="text-xs text-muted-foreground">
          Used: {result.knowledge_used.join(", ")}
          {result.drafts_used.length
            ? ` (includes unpublished: ${result.drafts_used.join(", ")})`
            : ""}
        </p>
      ) : null}
      {result.team_summary ? (
        <details className="text-xs text-muted-foreground">
          <summary className="cursor-pointer">Summary for your team</summary>
          <p className="mt-1 whitespace-pre-line" data-user-text>
            {result.team_summary}
          </p>
        </details>
      ) : null}
    </div>
  );
}
