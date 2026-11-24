# pi video rooms (PMB-5 Phase 1: listen-only)

Part of PMB (`pi-meeting-brain.md`), plan PMB-5. Branch `pi/meeting-rooms-phase0`. Migration **0073**
(additive). Status: backend built and tested locally; the room page in the web app is the next step.
What was proven live against Stream is in `pi-room-phase0.md`.

## What it is

A room is a video call we host (Stream Video) that staff and customers join from the browser. pi
does not speak in this phase: the provider hears the call and, after it ends, hands back a
transcript (one finished sentence per line, with the id of who spoke). That transcript goes through
the same analysis and review as every other meeting, and nothing reaches the Problem Map until a
person approves. Zoom, Meet and Teams stay on the Recall bot; rooms are for calls we host.

## Flow

1. Staff (`pi.meetings.record`) opens a room: `POST /pi/meeting-intel/rooms` with a title and
   `consent: true` (everyone in the room is told the call is transcribed). A meeting is made with
   `source = native`, and a room with a random call id (names no workspace or meeting).
2. Staff join: `POST /{id}/room/token` returns a token for their own staff id (`s_<user>`) and this
   one call. A guest uses the existing meeting link (`meeting_guests`), agrees to be recorded, and
   then `POST /public/meeting-room/token` (header `X-Guest-Token`) returns a token for their own
   guest id (`g_<guest>`). Tokens last two hours and name one call.
3. The call runs. The call type `pi_room` turns transcription on by itself; recording is off.
4. The host ends it: `POST /{id}/room/end` (no one in the room can end it, mute or remove anyone: the
   call type grants only join, read, audio, video, screenshare).
5. The provider calls `POST /public/stream/webhook` (signed: HMAC-SHA256 hex of the body with the API
   secret, header `X-Signature`). `call.session_started` / `call.session_ended` move the room;
   `call.transcription_ready` stores the transcript, redacted, one line per sentence, labelled by the
   room's user id (staff row = role `staff`; a guest = role `unknown`, never assumed to be the
   customer). The meeting becomes `analysing`; an empty transcript becomes `failed`.
6. If the callback never arrives, `GET /{id}/room` asks the provider once the call has ended.

## Rules in force

- Off unless the workspace has `brain.meeting_intel` AND `brain.meeting_room` (and guests also need
  `brain.meeting_guests`), and `STREAM_API_KEY` + `STREAM_API_SECRET` are set. Flags are not turned on
  by this code.
- The callback has no login; its only control is the signature, checked before the body is read. With
  no secret it refuses everything. Unknown or foreign calls change nothing.
- The transcript address from a callback is fetched only if it is `https` on the provider's own CDN.
- Idempotent: a retried callback stores nothing twice (same speaker, start and text).
- Erase: deleting a meeting or erasing a customer deletes the call (transcript and recording) at the
  provider first and refuses with `ROOM_DELETE_UNAVAILABLE` if it cannot; no words stay behind.
- Audit: `pi.meeting_room_opened`, `pi.meeting_room_ended`, `pi.meeting_room_failed`.

## Not in this phase

pi speaking (Phase 2), recording copy and playback, monthly minute caps and a kill switch (Phase 3),
a re-transcription of the audio for Urdu (Stream captions have no Urdu: see `pi-room-phase0.md`),
a real two-browser test of the guest token's limits, and the web room page.

## Code and tests

`pi_meetings/room_provider.py` (provider, tokens, signature), `room_routes.py`, `native_ingest.py`,
`erase.py`, models `PiMeetingRoom` and `PiMeetingParticipant.stream_user_id`, migration
`0073_pi_meeting_rooms.py`. Tests: `tests/unit/test_pi_room_provider.py`,
`tests/integration/test_pi_meeting_rooms.py` (fake provider).

## Apply order

Run 0073 on the real database BEFORE deploying this code. Set `STREAM_API_KEY` and `STREAM_API_SECRET`
on the API and worker services (done), and register the callback URL
`https://<api>/api/v1/public/stream/webhook` in the Stream dashboard for the events
`call.session_started`, `call.session_ended`, `call.transcription_ready`.
