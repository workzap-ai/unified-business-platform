"use client";

import { useState } from "react";
import { BookOpen, Flag, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/display";
import { Notice } from "@/components/app/states";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { clock, meetingIntelService } from "../meeting-intel-service";

/**
 * Chapters and key moments of a meeting, each with a time you can jump to. Chapters are pi's
 * reading of the transcript (one model call when you press the button; nothing is approved or
 * sent). Key moments are the findings your team already approved, at the time they were said.
 * Choosing one scrolls the transcript to that line and, when the meeting has a saved recording,
 * plays it from there.
 *
 * Backend: apps/api/app/modules/pi_meetings/chapter_routes.py.
 */

const KIND_LABELS: Record<string, string> = {
  decision: "Decision",
  commitment: "Commitment",
  next_step: "Next step",
  action: "Action",
  problem: "Problem",
  requirement_explicit: "Need",
  risk: "Risk",
};

export function MeetingChapters({
  id,
  lines,
  canMake,
}: {
  id: string;
  lines: number;
  canMake: boolean;
}) {
  const key = ["pi", "meeting-intel", id, "chapters"];
  const query = useScopedQuery(key, () => meetingIntelService.chapters(id), {
    enabled: lines > 0,
  });
  const make = useScopedMutation(() => meetingIntelService.makeChapters(id), {
    invalidate: [key],
    toastErrors: false,
  });
  const [note, setNote] = useState("");
  const data = query.data;

  function jump(ms: number, line: number) {
    setNote("");
    window.dispatchEvent(
      new CustomEvent("pi-meeting-seek", { detail: { ms } }),
    );
    const target = document.getElementById(`line-${line}`);
    if (target) {
      target.scrollIntoView({ behavior: "smooth", block: "center" });
      target.focus({ preventScroll: true });
    } else {
      setNote(
        "That line is further down. Use “Show the other lines” below, then choose it again.",
      );
    }
  }

  if (lines === 0) return null;
  const chapters = data?.chapters ?? [];
  const moments = data?.moments ?? [];
  if (
    !query.isPending &&
    chapters.length === 0 &&
    moments.length === 0 &&
    !canMake
  ) {
    return null;
  }
  return (
    <Card>
      <CardBody className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="flex items-center gap-1.5 text-sm font-semibold">
              <BookOpen className="size-4" aria-hidden /> Chapters and key
              moments
            </h2>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Choose one to jump to it in the transcript.
            </p>
          </div>
          {canMake && (
            <Button
              variant="secondary"
              loading={make.isPending}
              onClick={() => make.mutate()}
            >
              <Sparkles />{" "}
              {chapters.length > 0 ? "Make them again" : "Make chapters"}
            </Button>
          )}
        </div>
        {make.isError && (
          <Notice tone="danger">
            The chapters could not be made this time. Try again in a moment.
          </Notice>
        )}
        {note && <Notice tone="info">{note}</Notice>}
        {chapters.length > 0 && (
          <ol className="space-y-1.5" aria-label="Chapters">
            {chapters.map((c) => (
              <li key={c.start_line}>
                <button
                  type="button"
                  onClick={() => jump(c.start_ms, c.start_line)}
                  className="flex w-full items-start gap-2.5 rounded-lg px-2 py-1.5 text-left hover:bg-surface-muted"
                >
                  <span className="mt-0.5 shrink-0 rounded-md bg-surface-muted px-1.5 py-0.5 text-xs tabular-nums">
                    {clock(c.start_ms) || "0:00"}
                  </span>
                  <span className="min-w-0 text-sm">
                    <span className="font-medium">{c.title}</span>
                    {c.summary && (
                      <span className="block text-xs text-muted-foreground">
                        {c.summary}
                      </span>
                    )}
                  </span>
                </button>
              </li>
            ))}
          </ol>
        )}
        {chapters.length > 0 && (
          <p className="text-xs text-muted-foreground">
            Chapters are pi’s reading of the transcript and are not reviewed.
          </p>
        )}
        {moments.length > 0 && (
          <div className="space-y-1.5">
            <h3 className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground">
              <Flag className="size-3.5" aria-hidden /> Key moments (approved)
            </h3>
            <ul className="space-y-1">
              {moments.map((m) => (
                <li key={`${m.kind}-${m.line}-${m.text}`}>
                  <button
                    type="button"
                    onClick={() => jump(m.start_ms, m.line)}
                    className="flex w-full items-start gap-2.5 rounded-lg px-2 py-1.5 text-left hover:bg-surface-muted"
                  >
                    <span className="mt-0.5 shrink-0 rounded-md bg-surface-muted px-1.5 py-0.5 text-xs tabular-nums">
                      {clock(m.start_ms) || "0:00"}
                    </span>
                    <span className="min-w-0 text-sm">
                      <span className="mr-1.5 text-xs font-medium text-muted-foreground">
                        {KIND_LABELS[m.kind] ?? "Moment"}
                      </span>
                      {m.text}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </CardBody>
    </Card>
  );
}
