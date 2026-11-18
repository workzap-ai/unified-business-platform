# pi live events (Server-Sent Events)

The inbox used to find out about a new customer message by asking the server every 5 seconds
(every 3 seconds inside an open chat). Live events let the server say "something changed" the moment
it happens, so the screen refetches at once and polls only as a safety net.

## Safe by design

- **Off by default.** Nothing happens unless `PI_EVENTS_ENABLED=true` is set on the API and the
  worker (and `SECRETS_ENCRYPTION_KEY` exists, which signs the ticket). With it off: nothing is
  published, the ticket call answers `{"enabled": false}`, and every screen polls exactly as before.
- **An event carries no data.** Only a kind, `inbox` or `handoff`: no message, name, number or id.
  The screen reacts by refetching through the normal authenticated calls, which apply every rule
  (assigned-only chats, workspace scope). The stream cannot leak a chat.
- **Publishing never hurts a message.** It runs as a background task (`live_events.fire`): the
  customer's turn and a staff action never wait for Redis, every error is swallowed, and a hanging
  Redis costs nothing. An outage means the next poll finds the change.
- **The screen is told "live" only while a worker is publishing.** The API serves the stream and the
  worker publishes, and both need the flag. The worker leaves a 90-second mark every 20 seconds
  (`live_events.heartbeat`, a cron in `worker.py`); the stream's `ready` and `ping` carry
  `{"live": true|false}` from it. If the flag is on for the API but not for the worker (or the queue
  is inline), `live` stays false and the screens keep polling at the normal rate.
- **No database connection is held.** The screen first calls `POST /pi/events/ticket` (a normal
  authenticated call) and gets a signed ticket good for 60 seconds, bound to one workspace and one
  person. `GET /pi/events/stream?ticket=` then needs no session.
- **Limits.** At most 4 open streams per person and 300 per process, over their own Redis client
  (so streams can never use up the connections the rest of the API shares). Each stream lasts
  about 55 seconds, then the screen asks for a new ticket (this also covers every deploy).
- **The screen never trusts the stream.** It polls slowly (inbox list every 60 s, an open chat
  every 30 s) only while the stream is confirmed alive: a `ready` event, then a `ping` every
  15 seconds. If 40 seconds pass with nothing, or the stream fails, polling returns to 5 s and 3 s.
  After five failures in a row it stops trying for ten minutes.

## What publishes

| Moment | Where |
|---|---|
| A customer message is stored | `runtime.process_pi_event` |
| A reply is sent or fails | `runtime.send_pi_message` |
| Take over, return to pi, close (not "read") | `POST /pi/conversations/{id}/actions/{action}` |

A blocked number (see blocklist.md) never reaches this point.

## Where

| Part | Place |
|---|---|
| Publisher, ticket, stream | `apps/api/app/modules/pi/live_events.py` |
| Endpoints | `apps/api/app/modules/pi/events_routes.py` (mounted for Owner OS and the pi app) |
| Flag | `Settings.pi_events_enabled` (`PI_EVENTS_ENABLED`) |
| pi app | `apps/pi/src/lib/live.tsx` (`LiveEventsProvider`, `useLiveConnected`), used by the inbox |

## Turning it on

1. Set `PI_EVENTS_ENABLED=true` on the API service **and** on `pi-worker` (Railway). No migration.
   Each API replica allows up to 300 streams, each holding one Redis connection: check the Redis
   plan's connection limit against replicas x 300 before a large rollout.
2. Open the pi inbox, send a message from a test number: it should appear within a second. If the
   browser's network tab shows `/pi/events/stream` ending quickly or failing, polling carries on.

## Not known yet

- Whether the Vercel rewrite in front of `/api/v1/pi-app` passes a stream through unbuffered. The
  watchdog above is what protects the screen if it does not.
- The Owner OS web inbox still polls (`apps/web`); it can use the same endpoints.
- `handoff` events exist in the stream but nothing publishes them yet.


## Speed: how many seconds, and where they go

`GET /pi/events/speed?hours=24` (pi app: Health, Speed card) reports aggregates only, no text, name,
number or id:

- **Reply speed**, from rows pi already keeps (`pi_agent_runs`, the message rows and
  `media.send_timing`): the time from the customer's message being saved to pi's reply leaving
  (typical and slowest 1 in 10), split into: waiting for the customer to finish (the burst pause),
  pi thinking, the reply waiting for the sender, sending to WhatsApp, and WhatsApp delivering.
  Replies sent before `send_timing` was recorded count only in the stages that do not need it.
- **Live-update speed**, from samples the open screens report after each event
  (`POST /pi/events/timing`, one every ten seconds at most, kept in Redis, last 300, seven days):
  how long the signal waited on the server (`lag_ms`, one clock) and how long the screen took from
  hearing it to showing the data (`screen_ms`, includes the 0.4 s wait that groups bursts).
  Shown only while live events are on; a "Live" mark in the inbox header says the stream is alive.

Not measured: the time between the customer pressing send and the webhook reaching pi (WhatsApp's
side), and the network time between the server and the browser.
