"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowUp } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { AGENT_LIMITS as L } from "./meeting-agents-service";

/** Enter sends, Shift+Enter makes a new line. The box grows with the text up to a limit. */
export function ChatComposer({
  disabled,
  sending,
  placeholder,
  onSend,
}: {
  disabled?: boolean;
  sending: boolean;
  placeholder: string;
  onSend: (text: string) => void;
}) {
  const [text, setText] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);
  const trimmed = text.trim();
  const ready = trimmed.length >= L.questionMin && !sending && !disabled;

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 144)}px`;
  }, [text]);

  function submit() {
    if (!ready) return;
    onSend(trimmed);
    setText("");
  }

  return (
    <form
      className="border-t border-border bg-surface p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <div className="flex items-end gap-2 rounded-2xl border border-border bg-surface-muted px-3 py-1.5 transition-colors focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/15">
        <textarea
          ref={ref}
          rows={1}
          aria-label="Your question about this meeting"
          placeholder={placeholder}
          value={text}
          maxLength={L.questionMax}
          disabled={disabled}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (
              e.key === "Enter" &&
              !e.shiftKey &&
              !e.nativeEvent.isComposing
            ) {
              e.preventDefault();
              submit();
            }
          }}
          className="max-h-36 min-h-9 flex-1 resize-none bg-transparent py-1.5 text-base leading-snug sm:text-[14px] outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed"
        />
        <Button
          type="submit"
          size="icon"
          className="mb-0.5 size-10 rounded-full sm:size-9"
          loading={sending}
          disabled={!ready}
          aria-label="Send"
        >
          {!sending && <ArrowUp />}
        </Button>
      </div>
      <p className="mt-1.5 flex justify-between gap-3 px-1 text-[11px] text-muted-foreground">
        <span className="hidden sm:inline">
          Enter to send, Shift+Enter for a new line
        </span>
        <span
          className={cn(
            "tabular ml-auto",
            text.length < L.questionMax - 60 && "invisible",
            text.length >= L.questionMax - 20 && "font-medium text-warning",
          )}
          aria-live="polite"
        >
          {text.length}/{L.questionMax}
        </span>
      </p>
    </form>
  );
}
