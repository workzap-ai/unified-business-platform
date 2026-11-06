"use client";

import { useState } from "react";
import { MessageCircleQuestion } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/display";
import { Input } from "@/components/ui/input";
import { Notice } from "@/components/app/states";
import { useScopedMutation } from "@/hooks/use-scoped";
import { ApiError } from "@/services/api-client";
import { clock, meetingIntelService } from "../meeting-intel-service";

/**
 * Ask this meeting a question. The answer comes only from this meeting's transcript and shows the
 * lines it came from, so it can be checked; when the meeting does not say it, the answer says so
 * instead of guessing. Nothing here is saved to a customer's memory.
 */
export function MeetingAsk({ id }: { id: string }) {
  const [question, setQuestion] = useState("");
  const ask = useScopedMutation((q: string) => meetingIntelService.ask(id, q), {
    toastErrors: false,
  });
  const failed =
    ask.error instanceof ApiError &&
    ask.error.code === "MEETING_ASK_UNAVAILABLE"
      ? "The answer could not be written right now. Try again in a moment."
      : ask.error
        ? "Something went wrong. Try again."
        : "";
  const answer = ask.data;
  const ready = question.trim().length >= 3 && !ask.isPending;
  return (
    <Card>
      <CardBody className="space-y-3">
        <div>
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <MessageCircleQuestion className="size-4" aria-hidden /> Ask this
            meeting
          </h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            For example: “What did they say about the budget?” pi answers only
            from what was said in this meeting and shows the lines it used.
          </p>
        </div>
        <form
          className="flex flex-wrap gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (ready) ask.mutate(question.trim());
          }}
        >
          <div className="min-w-48 flex-1">
            <Input
              aria-label="Your question about this meeting"
              maxLength={300}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Ask a question about this meeting"
              className="h-9"
            />
          </div>
          <Button type="submit" loading={ask.isPending} disabled={!ready}>
            Ask
          </Button>
        </form>
        {failed && <Notice tone="danger">{failed}</Notice>}
        {answer && !ask.isPending && (
          <div className="space-y-2" role="status">
            {answer.found ? (
              <>
                <p className="text-[14px] leading-relaxed break-words">
                  {answer.answer}
                </p>
                {answer.partial && (
                  <p className="text-xs text-muted-foreground">
                    This is a long meeting: pi read the parts that matched your
                    question, not every line.
                  </p>
                )}
                <blockquote className="space-y-0.5 border-l-2 border-border pl-3 text-xs text-muted-foreground">
                  {answer.sources.map((s) => (
                    <p key={s.ordinal} className="break-words">
                      <span className="font-medium">
                        {s.speaker || "Speaker"}
                        {clock(s.start_ms) ? ` ${clock(s.start_ms)}` : ""}:
                      </span>{" "}
                      {s.text}
                    </p>
                  ))}
                </blockquote>
              </>
            ) : (
              <p className="text-[14px] text-muted-foreground">
                This was not said in the meeting
                {answer.partial ? " (in the parts pi read)" : ""}.
              </p>
            )}
          </div>
        )}
      </CardBody>
    </Card>
  );
}
