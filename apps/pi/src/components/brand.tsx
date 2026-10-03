import { cn } from "@/lib/cn";

/*
 * pi brand assets (brand guide v1.1), served from /brand/pi. The wordmark and lockups are
 * outlined SVGs and are never retyped. On dark grounds the lilac versions are used.
 */
const BRAND = "/brand/pi";

export type PiExpression =
  "rest" | "think" | "done" | "sorry" | "greet" | "noted" | "unsure" | "heads";

export const PI_ALT: Record<PiExpression, string> = {
  rest: "pi, a violet speech-bubble character with a small amber spark on its head, looking attentive with a gentle smile",
  think:
    "pi, the speech-bubble character, showing three typing dots while it works on something",
  done: "pi, the speech-bubble character, smiling widely with happy closed eyes because a problem is resolved",
  sorry:
    "pi, the speech-bubble character, with raised worried brows and a small downturned mouth, apologising",
  greet:
    "pi, the speech-bubble character, with an open smile, greeting someone at the start of a conversation",
  noted:
    "pi, the speech-bubble character, with a small tick for a mouth, showing it has noted a problem",
  unsure:
    "pi, the speech-bubble character, with one raised brow and a wavy mouth, unsure what was meant and asking",
  heads:
    "pi, the speech-bubble character, with both brows raised and a small round mouth, flagging something to notice",
};

/** Light and dark versions of one asset; the browser picks by colour scheme. */
function Themed({
  name,
  alt,
  className,
  width,
  height,
}: {
  name: string;
  alt: string;
  className?: string;
  width: number;
  height: number;
}) {
  return (
    <picture className="contents">
      <source
        media="(prefers-color-scheme: dark)"
        srcSet={`${BRAND}/${name}-dark.svg`}
      />
      <img
        src={`${BRAND}/${name}-color.svg`}
        alt={alt}
        width={width}
        height={height}
        draggable={false}
        className={cn("shrink-0 select-none", className)}
      />
    </picture>
  );
}

/**
 * The pi character. Full face at 32 px and up; below that the guide's micro face
 * (20-31 px) or the bare bubble (under 20 px) keeps it readable.
 */
export function PiFace({
  expression = "rest",
  size = 32,
  className,
  decorative = false,
}: {
  expression?: PiExpression;
  size?: number;
  className?: string;
  decorative?: boolean;
}) {
  const name =
    size >= 32 ? `pi-${expression}` : size >= 20 ? "pi-micro" : "pi-none";
  return (
    <Themed
      name={name}
      alt={decorative ? "" : PI_ALT[expression]}
      width={size}
      height={size}
      className={className}
    />
  );
}

/** Small mark for tight spaces: the character alone. */
export function PiMark({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex size-8", className)}>
      <PiFace size={32} decorative className="size-full" />
    </span>
  );
}

/** The horizontal lockup: character, outlined "pi" wordmark and BY WORKZAP. */
export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex h-11 items-center", className)}>
      <Themed
        name="pi-lockup-horizontal"
        alt="pi by Workzap"
        width={84}
        height={44}
        className="h-full w-auto"
      />
    </span>
  );
}

/** The stacked lockup, for covers and sign-in screens where there is height. */
export function StackedLockup({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex h-24 items-center", className)}>
      <Themed
        name="pi-lockup-stacked"
        alt="pi by Workzap"
        width={55}
        height={96}
        className="h-full w-auto"
      />
    </span>
  );
}
