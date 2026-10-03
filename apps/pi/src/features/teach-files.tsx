"use client";

import { FileUp, Mic, Square } from "lucide-react";
import * as React from "react";

import { Button, Card, CardSection } from "@/components/ui";
import { api } from "@/lib/api";
import { useAction } from "@/lib/session";
import type { Draft } from "@/lib/types";

const ACCEPT =
  ".pdf,.docx,.txt,.md,image/png,image/jpeg,image/webp,audio/*,application/pdf";
const MAX_RECORDING_SECONDS = 180;

function upload(file: Blob, name: string) {
  const body = new FormData();
  body.append("file", file, name);
  // Reading a long PDF or transcribing a voice note can take a while.
  return api<Draft>("POST", "/knowledge/upload", body, { timeoutMs: 120_000 });
}

/**
 * Teach Pi from a file or a voice note. Everything becomes a draft in "Waiting for
 * review"; nothing is used with customers until it's published.
 */
export function TeachFromFile() {
  const input = React.useRef<HTMLInputElement>(null);
  const send = useAction(
    ({ file, name }: { file: Blob; name: string }) => upload(file, name),
    {
      invalidate: [["drafts"]],
      success: "pi read it. Review the draft below, then publish.",
    },
  );
  return (
    <Card className="lg:col-span-2">
      <CardSection className="space-y-3">
        <h2 className="flex items-center gap-2 font-semibold">
          <FileUp className="size-4 text-accent" aria-hidden /> Teach from a
          file or voice note
        </h2>
        <p className="text-sm text-muted-foreground">
          Upload a price list, menu, brochure or policy (PDF, Word, text or a
          photo), or just say it. You check the draft before pi uses it.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <input
            ref={input}
            type="file"
            accept={ACCEPT}
            className="sr-only"
            id="teach-file"
            onChange={(e) => {
              const file = e.target.files?.[0];
              e.target.value = "";
              if (file) send.mutate({ file, name: file.name });
            }}
          />
          <Button
            variant="secondary"
            loading={send.isPending}
            onClick={() => input.current?.click()}
          >
            <FileUp className="size-4" aria-hidden /> Choose a file
          </Button>
          <VoiceNote
            disabled={send.isPending}
            onDone={(blob, name) => send.mutate({ file: blob, name })}
          />
        </div>
        <p className="text-xs text-muted-foreground">
          Up to 10 MB. Scanned PDFs can&apos;t be read. Upload photos of the
          pages instead.
        </p>
      </CardSection>
    </Card>
  );
}

const noopSubscribe = () => () => {};
const canRecord = () =>
  "MediaRecorder" in window && !!navigator.mediaDevices?.getUserMedia;

function VoiceNote({
  disabled,
  onDone,
}: {
  disabled: boolean;
  onDone: (blob: Blob, name: string) => void;
}) {
  // Recording needs MediaRecorder + a microphone API; the server render says "no".
  const supported = React.useSyncExternalStore(
    noopSubscribe,
    canRecord,
    () => false,
  );
  const [seconds, setSeconds] = React.useState<number | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const recorder = React.useRef<MediaRecorder | null>(null);
  const timer = React.useRef<ReturnType<typeof setInterval> | null>(null);

  React.useEffect(() => {
    return () => {
      if (timer.current) clearInterval(timer.current);
      recorder.current?.stream.getTracks().forEach((t) => t.stop());
    };
  }, []);

  const stop = React.useCallback(() => {
    if (timer.current) clearInterval(timer.current);
    timer.current = null;
    if (recorder.current?.state === "recording") recorder.current.stop();
  }, []);

  const start = async () => {
    setError(null);
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setError("Allow microphone access to record a voice note.");
      return;
    }
    const chunks: Blob[] = [];
    const rec = new MediaRecorder(stream);
    rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    rec.onstop = () => {
      stream.getTracks().forEach((t) => t.stop());
      setSeconds(null);
      const type = rec.mimeType || "audio/webm";
      const blob = new Blob(chunks, { type });
      if (blob.size > 0)
        onDone(
          blob,
          type.includes("mp4") ? "voice-note.m4a" : "voice-note.webm",
        );
    };
    recorder.current = rec;
    rec.start();
    setSeconds(0);
    timer.current = setInterval(() => {
      setSeconds((s) => {
        const next = (s ?? 0) + 1;
        if (next >= MAX_RECORDING_SECONDS) stop();
        return next;
      });
    }, 1000);
  };

  if (!supported) return null;
  const recording = seconds !== null;
  return (
    <>
      <Button
        variant={recording ? "danger" : "secondary"}
        disabled={disabled && !recording}
        onClick={() => (recording ? stop() : void start())}
        aria-pressed={recording}
      >
        {recording ? (
          <>
            <Square className="size-4" aria-hidden /> Stop and send
          </>
        ) : (
          <>
            <Mic className="size-4" aria-hidden /> Record a voice note
          </>
        )}
      </Button>
      <span className="text-sm text-muted-foreground" aria-live="polite">
        {recording
          ? `Recording ${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")} (up to 3 minutes)`
          : (error ?? "")}
      </span>
    </>
  );
}
