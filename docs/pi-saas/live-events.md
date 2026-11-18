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
- **Publishing never hurts a message.** Best effort: half a second at most, every error swallowed,
  nothing awaited by the customer's turn. A Redis outage means the next poll finds the change.
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

1. Set `PI_EVENTS_ENABLED=true` on the API service and on `pi-worker` (Railway). No migration.
2. Open the pi inbox, send a message from a test number: it should appear within a second. If the
   browser's network tab shows `/pi/events/stream` ending quickly or failing, polling carries on.

## Not known yet

- Whether the Vercel rewrite in front of `/api/v1/pi-app` passes a stream through unbuffered. The
  watchdog above is what protects the screen if it does not.
- The Owner OS web inbox still polls (`apps/web`); it can use the same endpoints.
- `handoff` events exist in the stream but nothing publishes them yet.
