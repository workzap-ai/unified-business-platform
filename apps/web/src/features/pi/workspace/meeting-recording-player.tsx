"use client";

import { useState } from "react";
import { Film } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/display";
import { Notice } from "@/components/app/states";
import { useScopedQuery } from "@/hooks/use-scoped";
import { clock, meetingIntelService } from "../meeting-intel-service";

/**
 * Plays the saved recording of a meeting: the video parts one after another, or the audio parts
 * when the meeting was recorded without video. The links come from the workspace's own storage and
 * expire after an hour, so they are fetched when the person asks to play, never kept in the page.
 *
 * Backend: apps/api/app/modules/pi_meetings/media_routes.py (GET .../recording).
 */
export function MeetingRecordingPlayer({
  id,
  until,
}: {
  id: string;
  until: string | null;
}) {
  const [open, setOpen] = useState(false);
  const [current, setCurrent] = useState(0);
  const query = useScopedQuery(
    ["pi", "meeting-intel", id, "recording"],
    () => meetingIntelService.recording(id),
    { enabled: open, staleTime: 0, gcTime: 0 },
  );
  const parts = query.data?.parts ?? [];
  const video = parts.filter((p) => p.kind === "video");
  const playlist = video.length > 0 ? video : parts;
  const playing = playlist[Math.min(current, playlist.length - 1)];
  const isVideo = playing?.kind === "video";

  return (
    <Card>
      <CardBody className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-sm font-semibold">Saved recording</h2>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Stored in your own storage
              {until
                ? `, kept until ${new Date(until).toLocaleDateString()}`
                : ""}
              .
            </p>
          </div>
          {!open && (
            <Button variant="secondary" onClick={() => setOpen(true)}>
              <Film /> Play the recording
            </Button>
          )}
        </div>

        {open && query.isPending && (
          <p className="text-xs text-muted-foreground">
            Opening the recording…
          </p>
        )}
        {open && query.isError && (
          <Notice tone="danger">
            The recording could not be opened. Check that the storage is still
            connected and try again.
          </Notice>
        )}
        {playing &&
          (isVideo ? (
            <video
              key={playing.url}
              className="aspect-video w-full rounded-lg bg-black"
              src={playing.url}
              controls
              autoPlay={current > 0}
              onEnded={() =>
                setCurrent((c) => Math.min(c + 1, playlist.length - 1))
              }
            />
          ) : (
            <audio
              key={playing.url}
              className="w-full"
              src={playing.url}
              controls
              autoPlay={current > 0}
              onEnded={() =>
                setCurrent((c) => Math.min(c + 1, playlist.length - 1))
              }
            />
          ))}
        {playlist.length > 1 && (
          <div className="flex flex-wrap gap-1.5" aria-label="Parts">
            {playlist.map((p, i) => (
              <Button
                key={`${p.kind}-${p.index}`}
                variant={i === current ? "default" : "secondary"}
                onClick={() => setCurrent(i)}
              >
                {clock(p.offset_ms) || "0:00"}
              </Button>
            ))}
          </div>
        )}
      </CardBody>
    </Card>
  );
}
