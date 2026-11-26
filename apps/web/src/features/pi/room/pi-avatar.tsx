/* eslint-disable @next/next/no-img-element -- small static brand SVGs, served as they are */

/**
 * pi's face (brand guide v1.1: the violet speech-bubble character with a small amber spark). The
 * SVGs are the brand files, copied as they are to /brand/pi; they are never redrawn. The light
 * version is used on light grounds and the lilac one on dark grounds, following the app's theme.
 * `greet` (open smile) is shown while pi speaks, `rest` (attentive, gentle smile) otherwise, and
 * `micro` is the small mark for chips and headings.
 */
export type PiAvatarExpression = "rest" | "greet" | "micro";

const ALT: Record<PiAvatarExpression, string> = {
  rest: "pi, the AI assistant, listening",
  greet: "pi, the AI assistant, speaking",
  micro: "pi, the AI assistant",
};

export function PiAvatar({
  expression = "rest",
  size = 64,
  decorative = false,
  className = "",
}: {
  expression?: PiAvatarExpression;
  size?: number;
  decorative?: boolean;
  className?: string;
}) {
  const base = `/brand/pi/pi-${expression}`;
  const alt = decorative ? "" : ALT[expression];
  const shared = {
    width: size,
    height: size,
    draggable: false,
  } as const;
  return (
    <span
      className={`inline-flex shrink-0 select-none ${className}`}
      style={{ width: size, height: size }}
    >
      <img
        src={`${base}-color.svg`}
        alt={alt}
        {...shared}
        className="size-full dark:hidden"
      />
      <img
        src={`${base}-dark.svg`}
        alt={alt}
        {...shared}
        className="hidden size-full dark:block"
      />
    </span>
  );
}
