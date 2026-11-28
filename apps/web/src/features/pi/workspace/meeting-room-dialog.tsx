"use client";

import { useState } from "react";
import { Video } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input, NativeSelect } from "@/components/ui/input";
import { Checkbox, Label } from "@/components/ui/controls";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/overlays";
import { Notice } from "@/components/app/states";
import { customersService } from "@/features/customers/service";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { ApiError } from "@/services/api-client";
import { meetingRoomService, ROOM_REFUSED } from "../meeting-room-service";
import { AgentAvatar } from "../agents/agent-avatar";
import { AgentChooser } from "../agents/agent-chooser";
import { agentFor, useAgents } from "../agents/use-agents";

/**
 * Open a video room: a title, and a confirmation that everyone who joins will be told the call is
 * transcribed by pi (an AI). No video is recorded; the words are kept as text.
 */
export function StartRoomDialog({
  open,
  onClose,
  onOpened,
}: {
  open: boolean;
  onClose: () => void;
  onOpened: (meetingId: string) => void;
}) {
  const [title, setTitle] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [language, setLanguage] = useState("");
  const [customer, setCustomer] = useState("");
  const [agentKey, setAgentKey] = useState("pi");
  const [choosing, setChoosing] = useState(false);
  const agents = useAgents(open);
  const agent = agentFor(agents.data, agentKey);
  const customers = useScopedQuery(
    ["customers", "meeting-picker"],
    () => customersService.list({ pageSize: 100 }),
    { enabled: open },
  );
  const options = useScopedQuery(
    ["pi", "meeting-room", "options"],
    () => meetingRoomService.options(),
    { enabled: open, retry: false },
  );
  const audio = options.data?.audio === true;
  const canRecord = options.data?.record === true;
  const [recordVideo, setRecordVideo] = useState(false);
  const make = useScopedMutation(meetingRoomService.open, {
    invalidate: [["pi", "meeting-intel"]],
    toastErrors: false,
    onSuccess: (out) => {
      setTitle("");
      setAgreed(false);
      setRecordVideo(false);
      setLanguage("");
      setCustomer("");
      setAgentKey("pi");
      onOpened(out.meeting.id);
    },
  });
  const failure =
    make.error instanceof ApiError
      ? (ROOM_REFUSED[make.error.code ?? ""] ??
        "Could not open the room. Try again.")
      : make.error
        ? "Could not open the room. Try again."
        : "";
  const ready = title.trim().length > 0 && agreed && !make.isPending;
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent size="md">
        <DialogHeader
          title="Start a video room"
          description="Meet your customer in a video room. pi is present as an AI assistant, listens, and writes the transcript."
        />
        <DialogBody className="space-y-3">
          <div>
            <Label htmlFor="room-title">Title</Label>
            <Input
              id="room-title"
              value={title}
              maxLength={200}
              disabled={make.isPending}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="For example: Tiles order review"
            />
          </div>
          <div>
            <Label htmlFor="room-customer">Customer (optional)</Label>
            <NativeSelect
              id="room-customer"
              value={customer}
              disabled={make.isPending}
              onChange={(e) => setCustomer(e.target.value)}
            >
              <option value="">Not linked yet</option>
              {(customers.data?.items ?? []).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </NativeSelect>
            <p className="mt-1 text-xs text-muted-foreground">
              When linked, pi already knows this customer: it asks &ldquo;Am I
              speaking with &hellip;?&rdquo; and uses what it knows only after a
              clear yes.
            </p>
          </div>
          <div>
            <Label htmlFor="room-agent">Agent</Label>
            <button
              id="room-agent"
              type="button"
              disabled={make.isPending}
              onClick={() => setChoosing(true)}
              className="flex min-h-12 w-full items-center gap-3 rounded-lg border border-border bg-surface px-3 py-2 text-left shadow-sm transition-colors hover:border-border-strong hover:bg-surface-muted disabled:opacity-60"
            >
              <AgentAvatar agent={agent} size="md" />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-semibold">
                  {agent.name}
                </span>
                <span className="block truncate text-xs text-muted-foreground">
                  {agent.tagline || "Choose how pi listens"}
                </span>
              </span>
              <span className="text-xs font-medium text-primary">Change</span>
            </button>
          </div>
          <div>
            <Label htmlFor="room-language">Language people will speak</Label>
            <NativeSelect
              id="room-language"
              value={language}
              disabled={make.isPending}
              onChange={(e) => setLanguage(e.target.value)}
            >
              <option value="">Mixed or not sure</option>
              <option value="ur">Urdu (and Roman Urdu)</option>
              <option value="en">English</option>
              <option value="hi">Hindi</option>
            </NativeSelect>
            <p className="mt-1 text-xs text-muted-foreground">
              Telling pi the main language makes the transcript more accurate.
            </p>
          </div>
          <label className="flex items-start gap-2 text-sm">
            <Checkbox
              checked={agreed}
              disabled={make.isPending}
              onCheckedChange={(v) => setAgreed(v === true)}
            />
            <span>
              {audio
                ? "Everyone who joins will be told that pi (an AI) is in the room, that the call is transcribed, and that each person's voice is recorded briefly to write the transcript and then deleted."
                : "Everyone who joins will be told that pi (an AI) is in the room and that the call is transcribed."}
            </span>
          </label>
          {canRecord && (
            <label className="flex items-start gap-2 text-sm">
              <Checkbox
                checked={recordVideo}
                disabled={make.isPending}
                onCheckedChange={(v) => setRecordVideo(v === true)}
              />
              <span>
                <span className="font-medium">
                  Record this call for my team.
                </span>{" "}
                The whole call, video and audio, is saved in your storage and
                your team can watch it later. Everyone who joins is told first
                and has to agree on the join page. Leave this unticked and no
                video is ever recorded.
              </span>
            </label>
          )}
          {failure && <Notice tone="danger">{failure}</Notice>}
        </DialogBody>
        <DialogFooter>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={!ready}
            loading={make.isPending}
            onClick={() =>
              make.mutate({
                title: title.trim(),
                consent: agreed,
                language,
                customer_id: customer || null,
                ...(agentKey !== "pi" ? { agent_key: agentKey } : {}),
                ...(recordVideo && canRecord ? { record_video: true } : {}),
              })
            }
          >
            <Video /> Start room
          </Button>
        </DialogFooter>
        <AgentChooser
          open={choosing}
          onOpenChange={setChoosing}
          value={agentKey}
          title="Choose an agent for this room"
          onSelect={(a) => setAgentKey(a.key)}
        />
      </DialogContent>
    </Dialog>
  );
}
