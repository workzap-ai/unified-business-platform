"use client";

import { useState } from "react";
import { Check, Copy, Link2, UserMinus, Users } from "lucide-react";
import { Badge, Card, CardBody } from "@/components/ui/display";
import { Button } from "@/components/ui/button";
import { Notice } from "@/components/app/states";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { meetingIntelService } from "../meeting-intel-service";

/**
 * The meeting link: send it to the people in the meeting and each records their own microphone
 * into this meeting, so the transcript says who spoke. The link is shown once, when it is made
 * (only a hash of it is kept), works for a day and admits up to ten people; closing it stops
 * everyone sending. Shown only when the workspace has switched meeting links on.
 * Backend: apps/api/app/modules/pi_meetings/guest_routes.py.
 */

const HOURS = 24;
const MAX_GUESTS = 10;

export function MeetingInvite({ id }: { id: string }) {
  const [link, setLink] = useState("");
  const [copied, setCopied] = useState(false);
  const status = useScopedQuery(
    ["pi", "meeting-intel", id, "invite"],
    () => meetingIntelService.inviteStatus(id),
    { refetchInterval: 15_000, retry: false },
  );
  const invalidate = [["pi", "meeting-intel", id, "invite"]];
  const make = useScopedMutation(
    () =>
      meetingIntelService.createInvite(id, {
        hours: HOURS,
        max_guests: MAX_GUESTS,
      }),
    {
      invalidate,
      success: "Link ready: copy it and send it to the people in the meeting",
      onSuccess: (r) => {
        setLink(`${window.location.origin}/join/${r.token}`);
        setCopied(false);
      },
    },
  );
  const close = useScopedMutation(() => meetingIntelService.revokeInvite(id), {
    invalidate,
    success: "The link is closed",
    onSuccess: () => setLink(""),
  });
  const remove = useScopedMutation(
    (guestId: string) => meetingIntelService.removeGuest(id, guestId),
    { invalidate, success: "Removed: they can no longer send audio" },
  );

  // off for this workspace, or not allowed to ask: show nothing
  if (!status.data?.enabled) return null;
  const open = status.data.open;
  const guests = status.data.guests;

  async function copy() {
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
    } catch {
      setCopied(false); // the link is on screen to copy by hand
    }
  }

  return (
    <Card>
      <CardBody className="space-y-3">
        <div>
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <Users className="size-4" aria-hidden /> Invite people to record
          </h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Send a link and each person records their own microphone into this
            meeting, so the transcript says who spoke. They agree before
            recording, see nothing of the transcript, and their sound is not
            kept.
          </p>
        </div>

        {link && open && (
          <div className="space-y-1.5">
            <div className="flex items-center gap-2">
              <input
                readOnly
                value={link}
                aria-label="Meeting link"
                onFocus={(e) => e.currentTarget.select()}
                className="min-w-0 flex-1 rounded-md border border-border bg-surface px-2 py-1.5 text-xs"
              />
              <Button variant="secondary" onClick={() => void copy()}>
                {copied ? <Check /> : <Copy />} {copied ? "Copied" : "Copy"}
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              Anyone with this link can record into the meeting until it is
              closed or ends. Send it only to the people in the meeting. It is
              shown here once.
            </p>
          </div>
        )}
        {!link && open && (
          <Notice tone="info">
            A link is open
            {status.data.expires_at
              ? ` until ${new Date(status.data.expires_at).toLocaleString()}`
              : ""}
            . For your safety it cannot be shown again: make a new one to copy
            it. A new link closes this one and stops everyone who has already
            joined, so do not do it in the middle of a call.
          </Notice>
        )}

        <div className="flex flex-wrap gap-2">
          <Button
            variant={open ? "secondary" : "default"}
            loading={make.isPending}
            onClick={() => make.mutate(undefined)}
          >
            <Link2 /> {open ? "Make a new link" : "Make a link"}
          </Button>
          {open && (
            <Button
              variant="secondary"
              loading={close.isPending}
              onClick={() => close.mutate(undefined)}
            >
              Close the link
            </Button>
          )}
        </div>

        {guests.length > 0 && (
          <ul className="divide-y divide-border rounded-lg border border-border text-sm">
            {guests.map((g) => (
              <li
                key={g.id}
                className="flex items-center justify-between gap-2 px-3 py-2"
              >
                <span className="min-w-0">
                  <span className="font-medium">{g.label}</span>{" "}
                  <span className="text-xs text-muted-foreground">
                    joined {new Date(g.joined_at).toLocaleTimeString()}
                  </span>
                </span>
                {g.removed ? (
                  <Badge tone="neutral">Removed</Badge>
                ) : (
                  <Button
                    variant="ghost"
                    loading={remove.isPending && remove.variables === g.id}
                    onClick={() => remove.mutate(g.id)}
                    aria-label={`Remove ${g.label}`}
                  >
                    <UserMinus /> Remove
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </CardBody>
    </Card>
  );
}
