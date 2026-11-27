"use client";

import { useEffect, useState } from "react";
import { Eye, Ear, MessageCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogHeader,
} from "@/components/ui/overlays";
import type { Agent } from "../meeting-agents-service";
import { SpriteAgent, LIVE_AGENTS, type ScreenState } from "./sprite-agent";

type Mode = "idle" | "hello" | "looking" | "listening";

/**
 * "Meet <agent>": a preview of the character that is in the room. It makes no sound and sends
 * nothing; the buttons only show how it behaves (talks, looks at a shared screen, listens).
 */
export function AgentMeetDialog({
  agent,
  open,
  onOpenChange,
}: {
  agent: Agent | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [picked, setMode] = useState<Mode>("idle");
  const [talk, setTalk] = useState(0);
  const [seen, setSeen] = useState(false);
  const mode: Mode = open ? picked : "idle";
  const level = mode === "hello" ? talk : 0;
  const screen: ScreenState =
    mode === "looking" ? (seen ? "seeing" : "looking") : "none";

  // a made-up voice level while "talking": syllables, with pauses between phrases
  useEffect(() => {
    if (mode !== "hello") return;
    const started = performance.now();
    const id = window.setInterval(() => {
      const t = (performance.now() - started) / 1000;
      const phrase = Math.sin(t * 1.3) > -0.35;
      const syllable = (Math.sin(t * 17) + Math.sin(t * 9.3) + 2) / 4;
      setTalk(phrase ? Math.min(0.9, syllable) : 0);
    }, 60);
    const stop = window.setTimeout(() => setMode("idle"), 5200);
    return () => {
      window.clearInterval(id);
      window.clearTimeout(stop);
    };
  }, [mode]);

  useEffect(() => {
    if (mode !== "looking") return;
    const saw = window.setTimeout(() => setSeen(true), 3200);
    const done = window.setTimeout(() => setMode("idle"), 4400);
    return () => {
      window.clearTimeout(saw);
      window.clearTimeout(done);
    };
  }, [mode]);

  if (!agent) return null;
  const alive = LIVE_AGENTS.has(agent.key);
  const toggle = (m: Mode) => {
    setSeen(false);
    setMode(mode === m ? "idle" : m);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="sm">
        <DialogHeader
          title={`Meet ${agent.name}`}
          description="A preview of how this agent looks and behaves in a room. No sound, nothing is sent."
        />
        <DialogBody className="flex flex-col items-center gap-4">
          {alive ? (
            <SpriteAgent
              agentKey={agent.key}
              level={level}
              speaking={mode === "hello"}
              listening={mode === "listening"}
              screen={screen}
              size={240}
              label={`${agent.name}, an AI agent`}
              className="rounded-2xl bg-surface-muted shadow-sm"
            />
          ) : (
            <p className="py-8 text-sm text-muted-foreground">
              This custom agent uses a tile in the room, not an animated
              character.
            </p>
          )}
          <p
            aria-live="polite"
            className="min-h-5 text-center text-[13px] text-muted-foreground"
          >
            {mode === "hello" && "Talking…"}
            {mode === "looking" &&
              (screen === "seeing"
                ? "Got it, it can see the screen."
                : "Looking at the shared screen…")}
            {mode === "listening" && "Listening…"}
          </p>
          {alive && (
            <div className="flex w-full flex-wrap justify-center gap-2">
              <Button
                variant={mode === "hello" ? "default" : "secondary"}
                onClick={() => toggle("hello")}
              >
                <MessageCircle /> Say hello
              </Button>
              <Button
                variant={mode === "looking" ? "default" : "secondary"}
                onClick={() => toggle("looking")}
              >
                <Eye /> Look at a screen
              </Button>
              <Button
                variant={mode === "listening" ? "default" : "secondary"}
                onClick={() => toggle("listening")}
              >
                <Ear /> Listen
              </Button>
            </div>
          )}
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}
