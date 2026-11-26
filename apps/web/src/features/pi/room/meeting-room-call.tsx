"use client";

import "@stream-io/video-react-sdk/dist/css/styles.css";
import { useEffect, useRef, useState } from "react";
import {
  CallControls,
  CallingState,
  SpeakerLayout,
  StreamCall,
  StreamTheme,
  StreamVideo,
  StreamVideoClient,
  useCallStateHooks,
  type Call,
} from "@stream-io/video-react-sdk";
import { Bot, Video } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Notice } from "@/components/app/states";
import type { RoomCredentials } from "../meeting-room-service";

/**
 * The call itself. Loaded only on a room page (it carries the video SDK, about 4 MB unpacked), and
 * only in the browser. The person has already agreed on the page that shows this: nothing here asks
 * for the camera or microphone until they press Join. pi is shown as present, and the live captions
 * are for the people in the room; the transcript that is kept comes from the server after the call.
 */

/** Tells the page when the call closed under the person (the host ended it or removed them). */
function EndWatch({ onClosed }: { onClosed: () => void }) {
  const { useCallCallingState } = useCallStateHooks();
  const state = useCallCallingState();
  useEffect(() => {
    if (state === CallingState.LEFT) onClosed();
  }, [state, onClosed]);
  return null;
}

function Captions() {
  const { useCallClosedCaptions } = useCallStateHooks();
  const captions = useCallClosedCaptions() as unknown as Array<{
    text?: string;
    speaker_id?: string;
    user?: { name?: string; id?: string };
  }>;
  const lines = captions.slice(-2).filter((c) => c.text);
  return (
    <div
      aria-live="polite"
      className="min-h-10 rounded-lg bg-surface-muted px-3 py-2 text-sm"
    >
      {lines.length === 0 ? (
        <span className="text-muted-foreground">
          Live captions appear here while people speak.
        </span>
      ) : (
        lines.map((c, i) => (
          <p key={i}>
            <span className="font-medium">
              {c.user?.name || c.user?.id || c.speaker_id || "Speaker"}:
            </span>{" "}
            {c.text}
          </p>
        ))
      )}
    </div>
  );
}

export function MeetingRoomCall({
  credentials,
  onLeft,
}: {
  credentials: RoomCredentials;
  // `ended` when the call closed under them (the host ended it or removed them)
  onLeft: (reason?: "ended") => void;
}) {
  const [live, setLive] = useState<{
    client: StreamVideoClient;
    call: Call;
  } | null>(null);
  const [joining, setJoining] = useState(false);
  const [error, setError] = useState("");
  const kept = useRef<{ client: StreamVideoClient; call: Call } | null>(null);
  const left = useRef(false);

  // the client is made only when the person presses Join, and closed when this page goes away
  useEffect(
    () => () => {
      const s = kept.current;
      kept.current = null;
      if (!s) return;
      void s.call.leave().catch(() => undefined);
      void s.client.disconnectUser().catch(() => undefined);
    },
    [],
  );

  async function join() {
    setJoining(true);
    setError("");
    const client = new StreamVideoClient({
      apiKey: credentials.api_key,
      user: { id: credentials.user_id, name: credentials.name },
      token: credentials.token,
    });
    const call = client.call(credentials.call_type, credentials.call_id);
    kept.current = { client, call };
    try {
      await call.join();
      try {
        await call.microphone.enable();
      } catch {
        setError(
          "The browser did not allow the microphone. Allow it for this page to be heard.",
        );
      }
      setLive({ client, call });
    } catch {
      kept.current = null;
      void client.disconnectUser().catch(() => undefined);
      setError(
        "Could not join the room. It may have ended, or the connection failed. Try again.",
      );
    } finally {
      setJoining(false);
    }
  }

  function leave(reason?: "ended") {
    if (left.current) return;
    left.current = true;
    onLeft(reason);
  }

  if (!live) {
    return (
      <div className="space-y-3">
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Bot className="size-4" aria-hidden /> pi (AI) is in this room and
          writes a transcript. It may speak if the host allows it, and says it
          is an AI first.
        </p>
        {error && <Notice tone="danger">{error}</Notice>}
        <Button
          onClick={() => void join()}
          loading={joining}
          disabled={joining}
        >
          <Video /> {error ? "Try again" : "Join the room"}
        </Button>
      </div>
    );
  }
  return (
    <StreamVideo client={live.client}>
      <StreamCall call={live.call}>
        <StreamTheme>
          <div className="space-y-3">
            <p className="flex items-center gap-2 text-xs text-muted-foreground">
              <Bot className="size-3.5" aria-hidden /> pi (AI) is writing a
              transcript of this call.
            </p>
            {error && <Notice tone="danger">{error}</Notice>}
            <div className="h-[60dvh] min-h-72 overflow-hidden rounded-lg">
              <SpeakerLayout />
            </div>
            <Captions />
            <CallControls onLeave={() => leave()} />
            <EndWatch onClosed={() => leave("ended")} />
          </div>
        </StreamTheme>
      </StreamCall>
    </StreamVideo>
  );
}
