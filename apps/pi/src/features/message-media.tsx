"use client";

import {
  AudioLines,
  FileText,
  ImageIcon,
  MousePointerClick,
} from "lucide-react";
import * as React from "react";

import { apiBlob } from "@/lib/api";
import type { Message } from "@/lib/types";

const VISUAL_LABEL: Record<string, string> = {
  map: "Problem map",
  map_text: "Problem map",
  board: "Board",
  progress: "Progress",
};

const KIND_LABEL: Record<string, string> = {
  map: "Problem map",
  board: "Board",
  progress: "Progress",
};

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

/** A picture pi sent. Signed links expire, so a failed load shows a calm placeholder. */
export function SentPicture({ message }: { message: Message }) {
  const media = message.media ?? {};
  const src = text(media.image) || message.card?.image || "";
  const [failed, setFailed] = React.useState(false);
  if (!src) return null;
  const visual = text(media.visual) || message.card?.kind || "";
  const label = VISUAL_LABEL[visual] ?? KIND_LABEL[visual] ?? "Picture";
  const alt = text(media.alt);
  const version = media.map_version;
  return (
    <figure className="mb-1.5" data-testid="sent-picture">
      <figcaption className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        {label}
        {version !== undefined && version !== null && version !== ""
          ? ` · version ${String(version)}`
          : ""}
      </figcaption>
      {failed ? (
        <div
          role="img"
          aria-label={alt || "Picture expired"}
          className="flex h-24 w-full max-w-[260px] items-center justify-center gap-2 rounded-xl border border-dashed border-border bg-card text-sm text-muted-foreground"
        >
          <ImageIcon className="size-4" aria-hidden /> Picture expired
        </div>
      ) : (
        <a href={src} target="_blank" rel="noopener noreferrer">
          {/* eslint-disable-next-line @next/next/no-img-element -- signed external picture */}
          <img
            src={src}
            alt={alt || `${label} sent on WhatsApp`}
            loading="lazy"
            onError={() => setFailed(true)}
            className="block w-full max-w-[260px] rounded-xl border border-border"
          />
        </a>
      )}
      {alt ? (
        <p
          className="mt-1 max-w-[260px] text-xs text-muted-foreground"
          dir="auto"
        >
          {alt}
        </p>
      ) : null}
    </figure>
  );
}

/** A PDF pi sent (solution document or quote). */
export function SentDocument({ message }: { message: Message }) {
  const doc = message.media?.document as
    { link?: unknown; filename?: unknown } | undefined;
  const link = text(doc?.link);
  if (!link) return null;
  return (
    <a
      href={link}
      target="_blank"
      rel="noopener noreferrer"
      className="mb-1.5 flex items-center gap-2 rounded-lg border border-border bg-card px-2.5 py-1.5 text-sm font-medium text-primary hover:underline"
    >
      <FileText className="size-4 shrink-0" aria-hidden />
      <span className="min-w-0 truncate">
        {text(doc?.filename) || "Document.pdf"}
      </span>
    </a>
  );
}

/** The buttons pi sent with a message (shown for the team's information only). */
export function SentButtons({ message }: { message: Message }) {
  const buttons = message.media?.buttons;
  if (!Array.isArray(buttons) || !buttons.length) return null;
  return (
    <div
      className="mt-1.5 flex flex-wrap items-center gap-1.5"
      data-testid="sent-buttons"
    >
      <span className="text-[11px] font-medium text-muted-foreground">
        Buttons sent
      </span>
      {buttons.map((b, i) => (
        <span
          key={`${String(b)}-${i}`}
          className="inline-flex items-center gap-1 rounded-full border border-border bg-card px-2 py-0.5 text-xs text-muted-foreground"
        >
          <MousePointerClick className="size-3" aria-hidden />
          <span dir="auto">{String(b)}</span>
        </span>
      ))}
    </div>
  );
}

/** What pi read from a customer's picture or heard in a voice note. */
export function CustomerReading({ message }: { message: Message }) {
  const media = message.media ?? {};
  const description = text(media.description);
  const transcript = text(media.transcript);
  if (!description && !transcript) return null;
  return (
    <div className="mt-1.5 rounded-lg border border-border bg-card/60 px-2.5 py-1.5 text-sm">
      {transcript ? (
        <>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            <AudioLines className="me-1 inline size-3" aria-hidden />
            Voice note transcript
          </p>
          <p className="whitespace-pre-line" dir="auto">
            {transcript}
          </p>
        </>
      ) : (
        <>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            pi read this image as:
          </p>
          <p className="whitespace-pre-line" dir="auto">
            {description}
          </p>
        </>
      )}
    </div>
  );
}

/** A customer's own picture, fetched through the private media route only on request. */
export function CustomerImage({ message }: { message: Message }) {
  const [state, setState] = React.useState<
    "idle" | "loading" | "failed" | { url: string }
  >("idle");
  const url = typeof state === "object" ? state.url : null;
  React.useEffect(
    () => () => {
      if (url) URL.revokeObjectURL(url);
    },
    [url],
  );
  async function load() {
    setState("loading");
    try {
      const blob = await apiBlob(
        `/pi/conversations/${message.conversation_id}/messages/${message.id}/media`,
      );
      setState({ url: URL.createObjectURL(blob) });
    } catch {
      setState("failed");
    }
  }
  if (url) {
    return (
      // eslint-disable-next-line @next/next/no-img-element -- a private blob URL
      <img
        src={url}
        alt="Picture sent by the customer"
        className="mb-1.5 block max-h-80 w-full max-w-[260px] rounded-xl border border-border object-contain"
      />
    );
  }
  return (
    <div className="mb-1.5">
      <button
        type="button"
        onClick={load}
        disabled={state === "loading"}
        className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-3 py-1 text-xs font-medium hover:bg-surface-muted disabled:opacity-60"
      >
        <ImageIcon className="size-3.5" aria-hidden />
        {state === "loading"
          ? "Loading..."
          : state === "failed"
            ? "Could not load. Try again"
            : "Show image"}
      </button>
    </div>
  );
}
