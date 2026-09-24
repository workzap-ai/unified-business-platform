"use client";

import { useState } from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

/** Chip input: type a tag and press Enter (or comma) to add; Backspace on empty removes the last. */
export function TagInput({
  id,
  value,
  onChange,
  placeholder = "Type a tag and press Enter",
  invalid,
  describedBy,
  max = 20,
}: {
  id?: string;
  value: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
  invalid?: boolean;
  describedBy?: string;
  max?: number;
}) {
  const [draft, setDraft] = useState("");

  function commit(raw: string) {
    const tag = raw.trim().toLowerCase().replace(/\s+/g, "-").slice(0, 40);
    if (!tag || value.includes(tag) || value.length >= max) {
      setDraft("");
      return;
    }
    onChange([...value, tag]);
    setDraft("");
  }

  return (
    <div
      className={cn(
        "flex min-h-9 w-full flex-wrap items-center gap-1.5 rounded-md border border-border bg-surface px-2 py-1.5 shadow-sm transition-colors focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/15 hover:border-border-strong",
        invalid && "border-danger",
      )}
    >
      {value.map((tag) => (
        <span
          key={tag}
          className="inline-flex items-center gap-1 rounded-full bg-surface-muted py-0.5 pr-1 pl-2 text-xs font-medium text-foreground-secondary"
        >
          {tag}
          <button
            type="button"
            onClick={() => onChange(value.filter((t) => t !== tag))}
            className="rounded-full p-0.5 text-muted-foreground hover:bg-surface-sunken hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring"
            aria-label={`Remove tag ${tag}`}
          >
            <X className="size-3" />
          </button>
        </span>
      ))}
      <input
        id={id}
        value={draft}
        onChange={(e) => {
          const next = e.target.value;
          if (next.endsWith(",")) commit(next.slice(0, -1));
          else setDraft(next);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            commit(draft);
          } else if (e.key === "Backspace" && !draft && value.length) {
            onChange(value.slice(0, -1));
          }
        }}
        onBlur={() => draft && commit(draft)}
        placeholder={value.length ? "" : placeholder}
        aria-describedby={describedBy}
        aria-invalid={invalid || undefined}
        className="h-6 min-w-24 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground/80"
      />
    </div>
  );
}
