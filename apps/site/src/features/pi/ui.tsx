import Image from "next/image";
import Link from "next/link";
import type { ReactNode } from "react";
import { IS_PRODUCTION, PI } from "./config";
import { WhatsAppButton } from "./client";

export type SlotKind = "WORKZAP" | "PRODUCT" | "CONFIRM";

/**
 * An answer that is not decided or not yet true. It shows as a dashed marker in
 * previews, and a production deploy refuses to build while any exist, so nothing
 * unfinished can go live looking finished.
 */
export function Slot({
  kind,
  children,
}: {
  kind: SlotKind;
  children: ReactNode;
}) {
  if (IS_PRODUCTION) {
    throw new Error(
      `pi: unfinished ${kind} slot still on the page. Resolve it before a production deploy.`,
    );
  }
  return (
    <span className="pi-slot" data-slot={kind}>
      <b>{kind}</b> {children}
    </span>
  );
}

/** Content that exists in the copy but must stay hidden until its gate opens. */
export function Gate({
  name,
  children,
  otherwise = null,
}: {
  name: keyof typeof PI.live;
  children: ReactNode;
  otherwise?: ReactNode;
}) {
  return <>{PI.live[name] ? children : otherwise}</>;
}

export const ALT = {
  rest: "pi, a violet speech-bubble character with a small amber spark on its head, looking attentive with a gentle smile",
  think:
    "pi, the speech-bubble character, showing three typing dots while it works on something",
  done: "pi, the speech-bubble character, smiling widely with happy closed eyes because a problem is resolved",
  greet:
    "pi, the speech-bubble character, with an open smile, greeting someone at the start of a conversation",
  noted:
    "pi, the speech-bubble character, with a small tick for a mouth, showing it has noted a problem",
  heads:
    "pi, the speech-bubble character, with both brows raised and a small round mouth, flagging something to notice",
} as const;

export function AiChip() {
  return (
    <span className="pi-ai-chip" title="pi is an AI">
      AI
    </span>
  );
}

export type FaceName = "rest" | "think" | "done" | "greet" | "noted" | "heads";

/**
 * One of pi's drawn faces. `tone="dark"` is the official Lilac-on-Ink version,
 * used only on Ink grounds (never plain Violet on Ink).
 */
export function Face({
  name,
  size = 120,
  className,
  tone = "color",
}: {
  name: FaceName;
  size?: number;
  className?: string;
  tone?: "color" | "dark";
}) {
  return (
    <Image
      src={`/pi-brand/pi-${name}-${tone}.svg`}
      alt={ALT[name]}
      width={size}
      height={size}
      className={className}
      unoptimized
      // tiny SVG faces: load at once so a face is never missing from a section
      loading="eager"
    />
  );
}

type Line = ["pi" | "you", ReactNode, FaceName?];

/** One message from pi (with its face and the AI chip) or from the person. */
function Msg({
  who,
  face,
  children,
}: {
  who: "pi" | "you";
  face?: FaceName;
  children: ReactNode;
}) {
  if (who === "you") {
    return (
      <div className="pi-msg pi-msg-you">
        <p className="pi-msg-body">
          <span className="pi-sr">You say: </span>
          {children}
        </p>
      </div>
    );
  }
  return (
    <div className="pi-msg pi-msg-pi">
      {face ? (
        <Face name={face} size={56} className="pi-msg-face" />
      ) : (
        <span className="pi-msg-face-gap" aria-hidden="true" />
      )}
      <div className="pi-msg-body">
        <span className="pi-msg-name">
          pi <AiChip />
        </span>
        <p>
          <span className="pi-sr">pi says: </span>
          {children}
        </p>
      </div>
    </div>
  );
}

export function Chat({ lines, note }: { lines: Line[]; note?: string }) {
  const withFaces = lines.some((l) => l[2]);
  return (
    <figure className="pi-chat">
      <div className="pi-chat-head">
        <Image
          src="/pi-brand/pi-avatar-light.svg"
          alt=""
          width={36}
          height={36}
          unoptimized
        />
        <div>
          <strong>pi</strong> <AiChip />
          <span className="pi-chat-sub">AI assistant · by Workzap</span>
        </div>
      </div>
      <div className="pi-chat-body">
        {lines.map(([who, text, face], i) =>
          withFaces ? (
            <Msg key={i} who={who} face={face}>
              {text}
            </Msg>
          ) : (
            <p key={i} className={`pi-bubble pi-bubble-${who}`}>
              <span className="pi-sr">
                {who === "you" ? "You say: " : "pi says: "}
              </span>
              {text}
            </p>
          ),
        )}
      </div>
      <figcaption>{note ?? "Illustrative conversation."}</figcaption>
    </figure>
  );
}

/**
 * A short exchange laid out as messages: pi's lines carry pi's face and the AI
 * chip, the person's lines sit on the right. Used where a page speaks as pi.
 */
export function Thread({
  lines,
  note = "Illustrative conversation.",
}: {
  lines: Line[];
  note?: string;
}) {
  return (
    <figure className="pi-thread">
      {lines.map(([who, text, face], i) => (
        <Msg key={i} who={who} face={face}>
          {text}
        </Msg>
      ))}
      <figcaption>{note}</figcaption>
    </figure>
  );
}

export function PageIntro({
  title,
  sub,
  children,
}: {
  title: string;
  sub?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <section className="pi-intro">
      <div className="pi-wrap pi-intro-grid">
        <div>
          <h1>{title}</h1>
          {sub ? <p className="pi-lead">{sub}</p> : null}
          {children}
        </div>
        <div className="pi-intro-face">
          <Face name="rest" size={168} />
          <AiChip />
        </div>
      </div>
    </section>
  );
}

/**
 * A page section. A titled section puts its heading in a left column and its
 * content on the right ("split") so a page does not read as one long stack;
 * pass layout="stack" when the content needs the full width.
 */
export function Section({
  title,
  id,
  tone = "white",
  layout = "split",
  children,
}: {
  title?: string;
  id?: string;
  tone?: "white" | "soft" | "tint";
  layout?: "split" | "stack";
  children: ReactNode;
}) {
  const split = Boolean(title) && layout === "split";
  return (
    <section id={id} className={`pi-section pi-section-${tone}`}>
      <div className={split ? "pi-wrap pi-split" : "pi-wrap"}>
        {title ? <h2>{title}</h2> : null}
        {split ? <div className="pi-split-body">{children}</div> : children}
      </div>
    </section>
  );
}

/** Bold lead + sentence rows, used for most lists. */
export function Points({
  items,
  numbered = false,
  start,
}: {
  items: { lead: string; text: ReactNode }[];
  numbered?: boolean;
  start?: number;
}) {
  const Tag = numbered ? "ol" : "ul";
  return (
    <Tag className="pi-points" start={numbered ? start : undefined}>
      {items.map((it) => (
        <li key={it.lead}>
          <strong>{it.lead}</strong> {it.text}
        </li>
      ))}
    </Tag>
  );
}

/**
 * Closing call to action: the one full-width Ink band on a page. Heading in
 * White, pi's Greeting face in its Lilac-on-Ink version, the button, and the
 * standing AI line.
 */
export function CtaBlock({
  page,
  pos,
  heading,
  children,
}: {
  page: string;
  pos: string;
  heading?: string;
  children?: ReactNode;
}) {
  return (
    <section className="pi-cta">
      <div
        className={
          heading ? "pi-wrap pi-cta-grid" : "pi-wrap pi-cta-grid pi-cta-bare"
        }
      >
        <div className="pi-cta-face">
          <Face name="greet" tone="dark" size={200} />
          <AiChip />
        </div>
        <div className="pi-cta-copy">
          {heading ? <h2>{heading}</h2> : null}
          <WhatsAppButton page={page} pos={pos} />
          <p className="pi-small">
            pi is an AI. It says so in its first message.
          </p>
          {children}
        </div>
      </div>
    </section>
  );
}

export function PersonLine() {
  return (
    <p className="pi-small">
      Prefer to talk to a person?{" "}
      <Slot kind="CONFIRM">
        pi can bring a person into the chat — build the hand-off before this
        line goes live
      </Slot>{" "}
      <Link href={`${PI.base}/talk-to-pi`}>Ask pi to bring one in.</Link>
    </p>
  );
}
