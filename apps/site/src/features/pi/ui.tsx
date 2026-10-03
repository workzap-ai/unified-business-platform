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

export function Face({
  name,
  size = 120,
  className,
}: {
  name: "rest" | "think" | "done" | "greet" | "noted" | "heads";
  size?: number;
  className?: string;
}) {
  return (
    <Image
      src={`/pi-brand/pi-${name}-color.svg`}
      alt={ALT[name]}
      width={size}
      height={size}
      className={className}
      unoptimized
    />
  );
}

export function Chat({
  lines,
  note,
}: {
  lines: ["pi" | "you", ReactNode][];
  note?: string;
}) {
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
        {lines.map(([who, text], i) => (
          <p key={i} className={`pi-bubble pi-bubble-${who}`}>
            <span className="pi-sr">
              {who === "you" ? "You say: " : "pi says: "}
            </span>
            {text}
          </p>
        ))}
      </div>
      <figcaption>{note ?? "Illustrative conversation."}</figcaption>
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
      <div className="pi-wrap">
        <h1>{title}</h1>
        {sub ? <p className="pi-lead">{sub}</p> : null}
        {children}
      </div>
    </section>
  );
}

export function Section({
  title,
  id,
  tone = "white",
  children,
}: {
  title?: string;
  id?: string;
  tone?: "white" | "soft" | "tint";
  children: ReactNode;
}) {
  return (
    <section id={id} className={`pi-section pi-section-${tone}`}>
      <div className="pi-wrap">
        {title ? <h2>{title}</h2> : null}
        {children}
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

/** Closing call to action: the button plus the standing AI line. */
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
      <div className="pi-wrap">
        {heading ? <h2>{heading}</h2> : null}
        <WhatsAppButton page={page} pos={pos} />
        <p className="pi-small">
          pi is an AI. It says so in its first message.
        </p>
        {children}
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
