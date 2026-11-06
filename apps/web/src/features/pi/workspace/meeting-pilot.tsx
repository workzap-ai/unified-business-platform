"use client";

import { useEffect, useRef, useState } from "react";
import { Check, Circle, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/display";
import { Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/controls";
import { useScopedMutation } from "@/hooks/use-scoped";
import { ApiError } from "@/services/api-client";
import { meetingIntelService } from "../meeting-intel-service";

/**
 * pi listens to the live meeting and tells the person running it what to ask next. Only that
 * person sees it: pi says nothing to the customer. The checklist is theirs to change; an item is
 * ticked only when a line of the meeting answers it. A suggestion is a prompt, not an instruction.
 */
const DEFAULT_CHECKLIST = [
  "What is the main problem",
  "How often it happens",
  "What it costs them",
  "Who decides",
  "When they need it",
].join("\n");
const EVERY_MS = 45_000;

export function MeetingPilot({ id }: { id: string }) {
  const [text, setText] = useState(DEFAULT_CHECKLIST);
  const [auto, setAuto] = useState(true);
  const items = text
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean)
    .slice(0, 8);
  const suggest = useScopedMutation(
    () => meetingIntelService.pilotSuggest(id, items),
    { toastErrors: false },
  );
  const run = useRef(suggest.mutate);
  const busy = useRef(false);
  useEffect(() => {
    run.current = suggest.mutate;
    busy.current = suggest.isPending;
  });

  // while the meeting is live, ask again every little while (and not in a hidden tab)
  useEffect(() => {
    if (!auto) return;
    const t = setInterval(() => {
      if (!busy.current && document.visibilityState === "visible")
        run.current(undefined);
    }, EVERY_MS);
    return () => clearInterval(t);
  }, [auto]);

  // switched off for this workspace: the card is not shown at all
  if (
    suggest.error instanceof ApiError &&
    suggest.error.code === "MEETING_PILOT_OFF"
  )
    return null;
  const out = suggest.data;
  const unavailable =
    suggest.error instanceof ApiError &&
    suggest.error.code === "MEETING_PILOT_UNAVAILABLE";
  return (
    <Card>
      <CardBody className="space-y-3">
        <div>
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <Sparkles className="size-4" aria-hidden /> pi suggests
          </h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            pi listens to the lines recorded so far and suggests the next
            question. Only you see this. It can lag behind by a few minutes
            while recording, because the transcript arrives in parts.
          </p>
        </div>
        <div>
          <Label htmlFor="pilot-checklist">
            What to cover (one per line, up to 8)
          </Label>
          <Textarea
            id="pilot-checklist"
            rows={4}
            value={text}
            maxLength={600}
            onChange={(e) => setText(e.target.value)}
          />
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Button
            loading={suggest.isPending}
            disabled={suggest.isPending}
            onClick={() => suggest.mutate(undefined)}
          >
            Suggest the next question
          </Button>
          <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <input
              type="checkbox"
              checked={auto}
              onChange={(e) => setAuto(e.target.checked)}
            />
            Refresh every 45 seconds
          </label>
        </div>
        {unavailable && (
          <p className="text-xs text-muted-foreground" role="status">
            No suggestion right now. pi will try again.
          </p>
        )}
        {out && (
          <div className="space-y-2" role="status">
            <p className="text-[14px] leading-relaxed break-words">
              {out.question
                ? out.question
                : out.lines_read === 0
                  ? "Nothing has been said yet."
                  : "No new question to suggest right now."}
            </p>
            {out.checklist.length > 0 && (
              <ul className="space-y-0.5 text-xs">
                {out.checklist.map((c) => (
                  <li key={c.text} className="flex items-center gap-1.5">
                    {c.done ? (
                      <Check className="size-3.5 text-success" aria-hidden />
                    ) : (
                      <Circle
                        className="size-3.5 text-muted-foreground"
                        aria-hidden
                      />
                    )}
                    <span
                      className={c.done ? "text-muted-foreground" : undefined}
                    >
                      {c.text}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </CardBody>
    </Card>
  );
}
