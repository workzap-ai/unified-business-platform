"use client";

import { useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  DoorOpen,
  Mic,
  MicOff,
  PhoneOff,
  Presentation,
  UserMinus,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardBody, Skeleton } from "@/components/ui/display";
import {
  PageHeader,
  PageShell,
  RequirePermission,
} from "@/components/app/page";
import { EmptyState, ErrorState, Notice } from "@/components/app/states";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useUrlState } from "@/hooks/use-url-state";
import { ApiError } from "@/services/api-client";
import {
  meetingRoomService,
  ROOM_REFUSED,
  type MeetingRoom,
  type RoomCredentials,
  type RoomPerson,
} from "../meeting-room-service";
import { MeetingRoomCall } from "../room/meeting-room-lazy";
import { PiAvatar } from "../room/pi-avatar";
import { MeetingInvite } from "./meeting-invite";

/**
 * A staff member's side of a video room (`/pi/meeting-intel/room?meeting=<id>`): enter the call,
 * send the link to the customer, and end it for everyone. The words are not read from this page:
 * when the call ends the video service sends the transcript to the server, which hands the meeting
 * to analysis and review like any other.
 * Backend: apps/api/app/modules/pi_meetings/room_routes.py.
 */

export function MeetingRoomPage() {
  return (
    <RequirePermission permission="pi.meetings.record" area="pi">
      <RoomView />
    </RequirePermission>
  );
}

function failure(e: unknown): string {
  if (e instanceof ApiError)
    return ROOM_REFUSED[e.code ?? ""] ?? "That did not work. Try again.";
  return e ? "That did not work. Try again." : "";
}

function RoomView() {
  const [url] = useUrlState({ meeting: "" });
  const id = url.meeting;
  const [credentials, setCredentials] = useState<RoomCredentials | null>(null);
  const [left, setLeft] = useState(false);
  const key = ["pi", "meeting-room", id];
  const status = useScopedQuery(key, () => meetingRoomService.status(id), {
    enabled: id.length > 0,
    // after the call ends, wait for the transcript to arrive
    // while the call is live, keep the list of people fresh
    refetchInterval: (query) => {
      const room = query.state.data?.room;
      if (room && room.live) return 10_000;
      return room && room.state === "ended" && room.transcript_state !== "done"
        ? 5_000
        : false;
    },
  });
  const enter = useScopedMutation(() => meetingRoomService.staffToken(id), {
    toastErrors: false,
    onSuccess: (c) => {
      setLeft(false);
      setCredentials(c);
    },
  });
  const remove = useScopedMutation(
    (participantId: string) =>
      meetingRoomService.removePerson(id, participantId),
    { invalidate: [key], toastErrors: false },
  );
  const mute = useScopedMutation(
    (input: { participantId: string; muted: boolean }) =>
      meetingRoomService.mutePerson(id, input.participantId, input.muted),
    { invalidate: [key], toastErrors: false },
  );
  const present = useScopedMutation(
    (input: { start: true } | { stop: true } | { step: number }) =>
      "start" in input
        ? meetingRoomService.startPresenting(id)
        : "stop" in input
          ? meetingRoomService.stopPresenting(id)
          : meetingRoomService.presentGo(id, { step: input.step }),
    { invalidate: [key], toastErrors: false },
  );
  const setPi = useScopedMutation(
    (input: { mode?: "off" | "speak"; muted?: boolean; intake?: boolean }) =>
      meetingRoomService.setPi(id, input),
    { invalidate: [key], toastErrors: false },
  );
  const end = useScopedMutation(() => meetingRoomService.end(id), {
    invalidate: [key],
    toastErrors: false,
    onSuccess: () => setCredentials(null),
  });

  const back = (
    <Button variant="secondary" asChild>
      <Link href={`/pi/meeting-intel?meeting=${id}`}>
        <ArrowLeft /> Back to the meeting
      </Link>
    </Button>
  );
  if (!id)
    return (
      <PageShell>
        <EmptyState
          title="No room selected"
          description="Open a room from a meeting."
        />
      </PageShell>
    );
  if (status.isLoading)
    return (
      <PageShell>
        <Skeleton className="h-72 w-full" />
      </PageShell>
    );
  if (status.isError)
    return (
      <PageShell>
        <ErrorState onRetry={() => void status.refetch()} />
      </PageShell>
    );
  const room = status.data?.room ?? null;
  if (!room)
    return (
      <PageShell>
        <PageHeader title="Video room" actions={back} />
        <EmptyState
          title="This meeting has no video room"
          description="Start a video room from the meetings list."
        />
      </PageShell>
    );

  const ended = room.state === "ended" || room.state === "failed";
  const enterButton = (
    <Button onClick={() => enter.mutate(undefined)} loading={enter.isPending}>
      <DoorOpen /> {left ? "Enter the room again" : "Enter the room"}
    </Button>
  );
  return (
    <PageShell>
      <PageHeader
        title="Video room"
        description="Staff and customers meet here. pi is present as an AI and writes the transcript. It speaks only when you switch it on, and you can mute it at any moment."
        actions={
          <div className="flex flex-wrap gap-2">
            {back}
            {!ended && (
              <Button
                variant="danger"
                loading={end.isPending}
                onClick={() => {
                  if (
                    window.confirm(
                      "End the call for everyone? This cannot be undone.",
                    )
                  )
                    end.mutate(undefined);
                }}
              >
                <PhoneOff /> End for everyone
              </Button>
            )}
          </div>
        }
      />
      {Boolean(
        enter.error ||
        end.error ||
        remove.error ||
        mute.error ||
        present.error ||
        setPi.error,
      ) && (
        <Notice tone="danger" className="mb-3">
          {failure(
            enter.error ??
              end.error ??
              remove.error ??
              mute.error ??
              present.error ??
              setPi.error,
          )}
        </Notice>
      )}
      {ended ? (
        <Card>
          <CardBody className="space-y-2" role="status">
            <p className="flex items-center gap-2 text-sm font-medium">
              <CheckCircle2 className="size-4 text-success" aria-hidden />
              {room.state === "failed"
                ? "The room could not be opened"
                : "The call has ended"}
            </p>
            <p className="text-sm text-muted-foreground">
              {room.transcript_state === "done"
                ? `The transcript is ready (${room.lines} line${room.lines === 1 ? "" : "s"}). Open the meeting to review it.`
                : room.state === "failed"
                  ? "Nothing was recorded."
                  : "pi is writing the transcript. This page updates by itself."}
            </p>
            {room.record && room.state !== "failed" && (
              <p className="text-sm text-muted-foreground">
                {room.recording === "saved"
                  ? "The recording is saved: open the meeting to watch it."
                  : room.recording === "failed"
                    ? "The recording could not be saved (no storage space or it was too large). The transcript is kept."
                    : "The recording is being saved. It appears on the meeting page in a few minutes."}
              </p>
            )}
          </CardBody>
        </Card>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[1fr_20rem]">
          <Card>
            <CardBody className="space-y-3">
              {credentials ? (
                <MeetingRoomCall
                  credentials={credentials}
                  onLeft={() => {
                    setCredentials(null);
                    setLeft(true);
                  }}
                />
              ) : (
                <>
                  {left ? (
                    <p className="text-sm text-muted-foreground">
                      You left the call. It is still open for the others.
                    </p>
                  ) : (
                    <div className="space-y-2">
                      <p className="text-sm font-medium">How this works</p>
                      <ol className="list-decimal space-y-1 pl-5 text-sm text-muted-foreground">
                        <li>
                          Press <strong>Enter the room</strong>. Your browser
                          asks for the microphone only then; the camera is
                          optional.
                        </li>
                        <li>
                          Make an invite link (right side) and send it to your
                          customer.
                        </li>
                        <li>
                          Optional: let pi speak. It tells everyone it is an AI
                          first, and you can mute it at any moment.
                        </li>
                        <li>
                          When you finish, press{" "}
                          <strong>End for everyone</strong>. The transcript is
                          ready about a minute later.
                        </li>
                      </ol>
                    </div>
                  )}
                  {enterButton}
                </>
              )}
            </CardBody>
          </Card>
          <div className="space-y-4">
            <MeetingInvite id={id} room audio={room.audio} />
            <PiSpeaks
              pi={room.pi}
              busy={setPi.isPending}
              onChange={(input) => setPi.mutate(input)}
            />
            <PiPresents
              present={room.present}
              piHere={room.pi.here}
              busy={present.isPending}
              onStart={() => present.mutate({ start: true })}
              onStep={(step) => present.mutate({ step })}
              onStop={() => present.mutate({ stop: true })}
            />
            <RoomPeople
              people={status.data?.people ?? []}
              minutes={status.data?.limits.minutes ?? 90}
              seats={status.data?.limits.people ?? 8}
              removing={remove.isPending}
              muting={mute.isPending}
              onMute={(participantId, muted) =>
                mute.mutate({ participantId, muted })
              }
              onRemove={(participantId) => {
                if (
                  window.confirm(
                    "Remove this person from the call? They will not be able to come back.",
                  )
                )
                  remove.mutate(participantId);
              }}
            />
          </div>
        </div>
      )}
    </PageShell>
  );
}

/** pi shows a recap in the room as its video. You start it, move it and stop it. */
function PiPresents({
  present,
  piHere,
  busy,
  onStart,
  onStep,
  onStop,
}: {
  present: MeetingRoom["present"];
  piHere: boolean;
  busy: boolean;
  onStart: () => void;
  onStep: (step: number) => void;
  onStop: () => void;
}) {
  return (
    <Card>
      <CardBody className="space-y-3">
        <div className="flex items-center justify-between gap-2">
          <h2 className="flex items-center gap-2 text-sm font-medium">
            <Presentation className="size-4" aria-hidden /> pi presents
          </h2>
          {present.on && (
            <span
              className="rounded-full bg-muted px-2 py-0.5 text-xs"
              role="status"
            >
              Slide {present.index + 1} of {present.total}
            </span>
          )}
        </div>
        {present.on ? (
          <>
            <p className="text-sm">{present.heading}</p>
            <div className="flex flex-wrap gap-2">
              <Button
                variant="secondary"
                size="sm"
                disabled={busy || present.index === 0}
                onClick={() => onStep(-1)}
                aria-label="Previous slide"
              >
                <ChevronLeft /> Back
              </Button>
              <Button
                size="sm"
                disabled={busy || present.index >= present.total - 1}
                onClick={() => onStep(1)}
                aria-label="Next slide"
              >
                Next <ChevronRight />
              </Button>
              <Button
                variant="secondary"
                size="sm"
                disabled={busy}
                onClick={onStop}
              >
                Stop presenting
              </Button>
            </div>
          </>
        ) : (
          <>
            <p className="text-xs text-muted-foreground">
              pi shows a short recap as its own video: what your team approved
              from this customer&rsquo;s earlier calls, and what was noted in
              this call. Everyone in the room sees it. Check who is in the room
              first.
            </p>
            <Button
              size="sm"
              variant="secondary"
              disabled={busy || !piHere}
              onClick={onStart}
            >
              <Presentation /> Show the recap
            </Button>
            {!piHere && (
              <p className="text-xs text-muted-foreground">
                Available once pi is in the room with its voice on.
              </p>
            )}
          </>
        )}
      </CardBody>
    </Card>
  );
}

function PiSpeaks({
  pi,
  busy,
  onChange,
}: {
  pi: MeetingRoom["pi"];
  busy: boolean;
  onChange: (input: {
    mode?: "off" | "speak";
    muted?: boolean;
    intake?: boolean;
  }) => void;
}) {
  const on = pi.mode === "speak";
  const state = !on
    ? "pi is listening only"
    : pi.muted
      ? "pi is muted"
      : pi.here
        ? "pi is in the room and can speak"
        : "pi is joining the room…";
  return (
    <Card>
      <CardBody className="space-y-3">
        <div className="flex items-center justify-between gap-2">
          <h2 className="flex items-center gap-2 text-sm font-medium">
            <PiAvatar expression="micro" size={20} decorative /> pi (AI) voice
          </h2>
          <span
            className="rounded-full bg-muted px-2 py-0.5 text-xs"
            role="status"
          >
            {state}
          </span>
        </div>
        <p className="text-xs text-muted-foreground">
          When on, pi first says out loud that it is an AI. After that it
          answers when someone says &ldquo;pi&rdquo;, or leads when you tick the
          box below. It never quotes prices or asks for payment details. People
          who talk over pi stop it at once.
        </p>
        <div className="flex flex-wrap gap-2">
          <Button
            variant={on ? "secondary" : "default"}
            disabled={busy}
            onClick={() => onChange({ mode: on ? "off" : "speak" })}
          >
            {on ? "Turn pi's voice off" : "Let pi speak"}
          </Button>
          {on && (
            <Button
              variant={pi.muted ? "default" : "danger"}
              disabled={busy}
              aria-pressed={pi.muted}
              onClick={() => onChange({ muted: !pi.muted })}
            >
              {pi.muted ? <Mic /> : <MicOff />}{" "}
              {pi.muted ? "Unmute pi" : "Mute pi"}
            </Button>
          )}
        </div>
        {on && (
          <label className="flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              className="mt-1 size-4"
              checked={pi.intake}
              disabled={busy}
              onChange={(e) => onChange({ intake: e.target.checked })}
            />
            <span>
              Let pi greet and ask questions when one customer is alone in the
              room (no need to say &ldquo;pi&rdquo;)
            </span>
          </label>
        )}
      </CardBody>
    </Card>
  );
}

function RoomPeople({
  people,
  minutes,
  seats,
  removing,
  muting,
  onMute,
  onRemove,
}: {
  people: RoomPerson[];
  minutes: number;
  seats: number;
  removing: boolean;
  muting: boolean;
  onMute: (participantId: string, muted: boolean) => void;
  onRemove: (participantId: string) => void;
}) {
  return (
    <Card>
      <CardBody className="space-y-2">
        <h2 className="text-sm font-medium">People in the room</h2>
        {people.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No one has entered yet.
          </p>
        ) : (
          <ul className="space-y-1">
            {people.map((p) => (
              <li
                key={p.id}
                className="flex items-center justify-between gap-2 text-sm"
              >
                <span className="min-w-0 truncate">
                  {p.label}
                  {p.staff ? " (staff)" : ""}
                  {p.removed ? " (removed)" : ""}
                  {p.muted && !p.removed ? " (muted)" : ""}
                </span>
                {!p.staff && !p.removed && (
                  <span className="flex shrink-0 items-center gap-1">
                    <Button
                      variant="secondary"
                      size="sm"
                      disabled={muting}
                      aria-pressed={p.muted}
                      aria-label={
                        p.muted
                          ? `Let ${p.label} speak again`
                          : `Mute ${p.label}`
                      }
                      onClick={() => onMute(p.id, !p.muted)}
                    >
                      {p.muted ? <MicOff /> : <Mic />}
                      {p.muted ? "Unmute" : "Mute"}
                    </Button>
                    <Button
                      variant="secondary"
                      size="sm"
                      disabled={removing}
                      aria-label={`Remove ${p.label} from the call`}
                      onClick={() => onRemove(p.id)}
                    >
                      <UserMinus /> Remove
                    </Button>
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
        <p className="text-xs text-muted-foreground">
          Up to {seats} people. A call ends by itself after {minutes} minutes.
        </p>
      </CardBody>
    </Card>
  );
}
