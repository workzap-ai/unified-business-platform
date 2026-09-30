import { cn } from "@/lib/cn";

/** Pi mark: a speech bubble with a single dot, drawn in the accent colour. */
export function PiMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden className={cn("size-8", className)}>
      <rect x="2" y="3" width="28" height="22" rx="8" className="fill-accent" />
      <path d="M9 25 L9 30 L15 25 Z" className="fill-accent" />
      <text
        x="16"
        y="19"
        textAnchor="middle"
        className="fill-accent-foreground"
        style={{ font: "600 16px Georgia, serif" }}
      >
        Pi
      </text>
    </svg>
  );
}

export function Wordmark({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2.5 text-2xl font-semibold tracking-[-0.04em]",
        className,
      )}
    >
      <PiMark className="size-9" />
      Pi
    </span>
  );
}
