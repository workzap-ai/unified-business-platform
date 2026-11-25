"use client";

import { useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  CheckCircle2,
  DoorOpen,
  PhoneOff,
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
  type RoomCredentials,
  type RoomPerson,
} from "../meeting-room-service";
import { MeetingRoomCall } from "../room/meeting-room-lazy";
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
        description="Staff and customers meet here. pi is present as an AI, listens and writes the transcript; it does not speak."
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
      {Boolean(enter.error || end.error || remove.error) && (
        <Notice tone="danger" className="mb-3">
          {failure(enter.error ?? end.error ?? remove.error)}
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
                  <p className="text-sm text-muted-foreground">
                    {left
                      ? "You left the call. It is still open for the others."
                      : "Your camera and microphone are asked for only after you press the button."}
                  </p>
                  {enterButton}
                </>
              )}
            </CardBody>
          </Card>
          <div className="space-y-4">
            <RoomPeople
              people={status.data?.people ?? []}
              minutes={status.data?.limits.minutes ?? 90}
              seats={status.data?.limits.people ?? 8}
              removing={remove.isPending}
              onRemove={(participantId) => {
                if (
                  window.confirm(
                    "Remove this person from the call? They will not be able to come back.",
                  )
                )
                  remove.mutate(participantId);
              }}
            />
            <MeetingInvite id={id} room audio={room.audio} />
          </div>
        </div>
      )}
    </PageShell>
  );
}

function RoomPeople({
  people,
  minutes,
  seats,
  removing,
  onRemove,
}: {
  people: RoomPerson[];
  minutes: number;
  seats: number;
  removing: boolean;
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
                </span>
                {!p.staff && !p.removed && (
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={removing}
                    aria-label={`Remove ${p.label} from the call`}
                    onClick={() => onRemove(p.id)}
                  >
                    <UserMinus /> Remove
                  </Button>
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
