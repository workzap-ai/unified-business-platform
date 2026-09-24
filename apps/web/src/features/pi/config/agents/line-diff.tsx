"use client";

import { cn } from "@/lib/utils";

export type DiffLine = { kind: "same" | "added" | "removed"; text: string };

/** Line-level diff via longest common subsequence (instructions are short). */
export function diffLines(before: string, after: string): DiffLine[] {
  const a = before.split("\n");
  const b = after.split("\n");
  const n = a.length;
  const m = b.length;
  const table: number[][] = Array.from({ length: n + 1 }, () =>
    new Array<number>(m + 1).fill(0),
  );
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      table[i]![j] =
        a[i] === b[j]
          ? table[i + 1]![j + 1]! + 1
          : Math.max(table[i + 1]![j]!, table[i]![j + 1]!);
    }
  }
  const out: DiffLine[] = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) {
      out.push({ kind: "same", text: a[i]! });
      i++;
      j++;
    } else if (table[i + 1]![j]! >= table[i]![j + 1]!) {
      out.push({ kind: "removed", text: a[i]! });
      i++;
    } else {
      out.push({ kind: "added", text: b[j]! });
      j++;
    }
  }
  while (i < n) out.push({ kind: "removed", text: a[i++]! });
  while (j < m) out.push({ kind: "added", text: b[j++]! });
  return out;
}

export function diffStats(lines: DiffLine[]) {
  return {
    added: lines.filter((l) => l.kind === "added").length,
    removed: lines.filter((l) => l.kind === "removed").length,
  };
}

/** Side-by-side (stacked on mobile) instruction comparison. */
export function SideBySideDiff({
  before,
  after,
  beforeLabel,
  afterLabel,
}: {
  before: string;
  after: string;
  beforeLabel: string;
  afterLabel: string;
}) {
  const lines = diffLines(before, after);
  const left = lines.filter((l) => l.kind !== "added");
  const right = lines.filter((l) => l.kind !== "removed");
  const { added, removed } = diffStats(lines);
  return (
    <div>
      <p className="mb-2 text-xs text-muted-foreground" aria-live="polite">
        <span className="font-medium text-success">+{added}</span> added ·{" "}
        <span className="font-medium text-danger">−{removed}</span> removed
        lines
      </p>
      <div className="grid gap-3 lg:grid-cols-2">
        <DiffPane label={beforeLabel} lines={left} />
        <DiffPane label={afterLabel} lines={right} />
      </div>
    </div>
  );
}

function DiffPane({ label, lines }: { label: string; lines: DiffLine[] }) {
  return (
    <figure className="min-w-0 overflow-hidden rounded-lg border border-border">
      <figcaption className="border-b border-border bg-surface-muted px-3 py-1.5 text-xs font-medium text-muted-foreground">
        {label}
      </figcaption>
      <pre className="scrollbar-thin max-h-96 overflow-auto py-1 font-mono text-xs leading-5">
        {lines.length === 1 && lines[0]!.text === "" ? (
          <span className="block px-3 text-muted-foreground">(empty)</span>
        ) : (
          lines.map((line, index) => (
            <span
              key={index}
              className={cn(
                "block px-3 break-words whitespace-pre-wrap",
                line.kind === "added" && "bg-success-soft text-success",
                line.kind === "removed" && "bg-danger-soft text-danger",
              )}
            >
              <span className="sr-only">
                {line.kind === "added"
                  ? "Added: "
                  : line.kind === "removed"
                    ? "Removed: "
                    : ""}
              </span>
              <span aria-hidden="true" className="mr-2 select-none opacity-60">
                {line.kind === "added"
                  ? "+"
                  : line.kind === "removed"
                    ? "−"
                    : " "}
              </span>
              {line.text || " "}
            </span>
          ))
        )}
      </pre>
    </figure>
  );
}
