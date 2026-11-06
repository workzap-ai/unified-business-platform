"use client";

import { useRef, useState } from "react";
import { FileVideo } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/display";
import { Notice } from "@/components/app/states";
import { useScopedMutation } from "@/hooks/use-scoped";
import { ApiError } from "@/services/api-client";
import { meetingIntelService } from "../meeting-intel-service";

/**
 * Turns a recorded meeting (a video or audio file) into the meeting's transcript, summary and
 * requirement map.
 *
 * The server has no media tools, so the browser pulls the sound out of the file: it decodes the
 * audio track at 16 kHz, mixes it to mono and cuts it into self-contained WAV parts of three
 * minutes (about 5.8 MB each). Each part goes through the same route as a live recording
 * (`POST .../recording/parts`), so redaction, speech-to-text, the consent rule and retries behave
 * exactly the same, and a dropped connection costs one part. Only the words are kept: the file
 * itself and its audio are not uploaded or stored.
 *
 * Limits: whatever the browser can decode (MP4/MOV with AAC, WebM, MP3, WAV, M4A, Ogg), and a file
 * of up to MAX_FILE_BYTES, because the whole track is decoded in memory.
 */

const SAMPLE_RATE = 16_000;
const PART_SECONDS = 180;
const MAX_FILE_BYTES = 700 * 1024 * 1024;
const TRIES = 3;
const FINAL_STATUSES = [403, 404, 409, 413, 422];

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** 16-bit mono PCM in a WAV container. */
function wav(samples: Float32Array): Blob {
  const data = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(data);
  const text = (at: number, s: string) =>
    [...s].forEach((c, i) => view.setUint8(at + i, c.charCodeAt(0)));
  text(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  text(8, "WAVE");
  text(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, SAMPLE_RATE, true);
  view.setUint32(28, SAMPLE_RATE * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  text(36, "data");
  view.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Blob([data], { type: "audio/wav" });
}

/** Decode the file's sound at 16 kHz and mix every channel down to one. */
async function mono16k(file: File): Promise<Float32Array> {
  const ctx = new AudioContext({ sampleRate: SAMPLE_RATE });
  try {
    const buffer = await ctx.decodeAudioData(await file.arrayBuffer());
    const out = new Float32Array(buffer.length);
    for (let c = 0; c < buffer.numberOfChannels; c++) {
      const channel = buffer.getChannelData(c);
      for (let i = 0; i < out.length; i++) out[i] += channel[i];
    }
    if (buffer.numberOfChannels > 1)
      for (let i = 0; i < out.length; i++) out[i] /= buffer.numberOfChannels;
    return out;
  } finally {
    void ctx.close().catch(() => undefined);
  }
}

type Phase = "idle" | "reading" | "sending" | "finishing";

export function MeetingFileImport({ id }: { id: string }) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [file, setFile] = useState<File | null>(null);
  const [done, setDone] = useState(0);
  const [total, setTotal] = useState(0);
  const [skipped, setSkipped] = useState(0);
  const [error, setError] = useState("");
  const cancelled = useRef(false);
  const refused = useRef(false); // an answer no retry can change: stop sending

  // the same ending as a live recording: close the transcript, then write the summary and the map
  const complete = useScopedMutation(
    async (v: { duration_ms: number; parts: number; skipped: number }) => {
      const closed = await meetingIntelService.completeRecording(id, v);
      const analysed = await meetingIntelService
        .analyseAll(id)
        .catch(() => null);
      return { closed, analysed };
    },
    {
      invalidate: [
        ["pi", "meeting-intel", id],
        ["pi", "meeting-intel"],
      ],
      success: ({ closed, analysed }) => {
        const gaps =
          closed.skipped > 0
            ? ` ${closed.skipped} part${closed.skipped === 1 ? "" : "s"} could not be transcribed.`
            : "";
        if (analysed === null)
          return `Transcript saved. The summary could not be written: press “Analyse with pi”.${gaps}`;
        return analysed.insights === 0
          ? `Transcript and summary saved: nothing worth noting.${gaps}`
          : `Transcript, summary and ${analysed.insights} finding${analysed.insights === 1 ? "" : "s"} saved for review.${gaps}`;
      },
      toastErrors: false,
      onSuccess: () => setPhase("idle"),
    },
  );

  async function sendPart(
    index: number,
    audio: Blob,
    durationMs: number,
  ): Promise<boolean> {
    for (let attempt = 1; attempt <= TRIES; attempt++) {
      try {
        await meetingIntelService.uploadPart(id, {
          index,
          offsetMs: index * PART_SECONDS * 1000,
          durationMs,
          audio,
        });
        return true;
      } catch (e) {
        if (e instanceof ApiError && e.code === "MEETING_PART_ANALYSED")
          return true;
        if (e instanceof ApiError && FINAL_STATUSES.includes(e.status)) {
          if (e.status !== 422) {
            refused.current = true;
            setError(
              e.status === 409
                ? "This meeting has already been reviewed. Start a new one."
                : "This file can no longer be added to the meeting.",
            );
          }
          return false;
        }
        if (attempt < TRIES) await sleep(1500 * attempt);
      }
    }
    return false;
  }

  async function start() {
    if (!file) return;
    setError("");
    setSkipped(0);
    setDone(0);
    cancelled.current = false;
    refused.current = false;
    if (file.size > MAX_FILE_BYTES) {
      setError(
        "This file is too large to read in the browser (the limit is 700 MB). Record the meeting again with the recorder, or send a shorter file.",
      );
      return;
    }
    setPhase("reading");
    let samples: Float32Array;
    try {
      samples = await mono16k(file);
    } catch {
      setError(
        "The sound could not be read from this file. Use an MP4, MOV, WebM, M4A, MP3 or WAV file whose sound this browser can play.",
      );
      setPhase("idle");
      return;
    }
    const perPart = PART_SECONDS * SAMPLE_RATE;
    const parts = Math.ceil(samples.length / perPart);
    if (parts === 0) {
      setError("This file has no sound.");
      setPhase("idle");
      return;
    }
    setTotal(parts);
    setPhase("sending");
    let sent = 0;
    let missed = 0;
    for (let i = 0; i < parts; i++) {
      if (cancelled.current) break;
      const slice = samples.subarray(i * perPart, (i + 1) * perPart);
      const ok = await sendPart(
        i,
        wav(slice),
        Math.round((slice.length / SAMPLE_RATE) * 1000),
      );
      if (ok) sent += 1;
      else missed += 1;
      setDone(i + 1);
      setSkipped(missed);
      if (!ok && refused.current) break;
    }
    if (sent === 0) {
      if (!refused.current)
        setError("Nothing could be transcribed from this file. Try again.");
      setPhase("idle");
      return;
    }
    setPhase("finishing");
    complete.mutate({
      duration_ms: Math.round((samples.length / SAMPLE_RATE) * 1000),
      parts: sent,
      skipped: missed,
    });
  }

  const busy = phase !== "idle";
  return (
    <Card>
      <CardBody className="space-y-3">
        <div>
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <FileVideo className="size-4" aria-hidden /> Add a recorded meeting
          </h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Choose a video or audio file of the meeting. pi listens to it,
            writes the transcript, and picks out the problems, what each side
            needs and what was decided. The sound is read in your browser and
            only the words are kept: the video file itself is not uploaded or
            saved.
          </p>
        </div>
        <input
          type="file"
          accept="video/*,audio/*,.mp4,.mov,.webm,.m4a,.mp3,.wav"
          disabled={busy}
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          aria-label="Meeting video or audio file"
          className="block w-full text-sm file:mr-3 file:rounded-md file:border file:border-border file:bg-surface file:px-3 file:py-1.5 file:text-sm"
        />
        {error && <Notice tone="danger">{error}</Notice>}
        {phase === "reading" && (
          <p className="text-xs text-muted-foreground" role="status">
            Reading the sound from the file… this can take a minute for a long
            meeting.
          </p>
        )}
        {phase === "sending" && (
          <div role="status" className="space-y-1">
            <progress
              className="h-2 w-full"
              value={done}
              max={total}
              aria-label="Transcribing"
            />
            <p className="text-xs text-muted-foreground">
              Transcribing part {Math.min(done + 1, total)} of {total}
              {skipped > 0 ? ` (${skipped} could not be read)` : ""}. Keep this
              page open.
            </p>
          </div>
        )}
        {phase === "finishing" && (
          <p className="text-xs text-muted-foreground" role="status">
            Writing the summary and the requirement list…
          </p>
        )}
        <div className="flex gap-2">
          <Button disabled={!file || busy} onClick={() => void start()}>
            Transcribe and analyse
          </Button>
          {phase === "sending" && (
            <Button
              variant="secondary"
              onClick={() => {
                cancelled.current = true;
              }}
            >
              Stop here
            </Button>
          )}
        </div>
      </CardBody>
    </Card>
  );
}
