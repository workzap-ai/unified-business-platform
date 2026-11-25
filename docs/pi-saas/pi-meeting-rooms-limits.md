# Video rooms: limits, removing a guest, and the pause switch

Part of PMB-5 (`pi-meeting-rooms.md`). Branch `pi/meeting-rooms-phase3`. Migration **0075** (additive).

## Why

A live call costs money for every minute and every person, and a call nobody closes ran for six
hours in the first live test. A guest also had no way to be removed except ending the call for
everyone. These are now enforced in code (`pi_meetings/room_limits.py`), not by habit.

## What it does

| Limit | Value | Where enforced |
|---|---|---|
| Call length | 90 minutes | worker sweep `close_rooms` (every 30 s) ends the call; transcript is then written as usual |
| People per room | 8 different people | `staff_token` and `guest_token` refuse a new person (`MEETING_ROOM_FULL`); someone already seated can re-enter; removing a person does not free the seat |
| Month allowance | `brain.meeting_room_month_minutes` (0 or unset = 600) | `open_room` refuses (`MEETING_ROOM_MONTH_LIMIT`) once the month's call minutes (UTC month) are used |
| Pause switch | `brain.meeting_room_kill` | no new room, no staff or guest token (`MEETING_ROOM_PAUSED`, 503); the sweep ends every live call of that workspace. Ending a call by hand still works |

**Removing a guest.** `POST /pi/meeting-intel/{meeting}/room/people/{participant}/remove` (record
permission): blocks the person's room user at the provider (`/video/call/pi_room/{id}/block`, kicks
them and stops a rejoin), sets `removed_at`, and refuses them a new token (`MEETING_ROOM_REMOVED`).
Staff cannot be removed this way (`MEETING_ROOM_STAFF`). A provider failure removes nothing. The
staff room page lists the people (refreshed every 10 s while live) with a Remove button.

## Changes in shared code

- Migration 0075: nullable `removed_at` on `pi_meeting_participants`. Apply BEFORE deploying.
- `RoomProvider.block_user`; the `GET .../room` reply gains `people` and `limits`.
- `policy.py`: flags `meeting_room_kill` (bool) and `meeting_room_month_minutes` (0 to 100000).
- Audit events: `pi.meeting_room_person_removed`, `pi.meeting_room_closed` (`why`: `time_limit` or `paused`).

## Verified

`block` endpoint checked live against the real provider (a user that never connected answers 404,
which is treated as "nothing to remove"; the token refusal covers that case). Not yet exercised:
a real guest being kicked from a live browser call. Tests: `tests/integration/test_pi_meeting_rooms_limits.py`.

## Not built

Per-file chunking above 25 MB, a heartbeat alert for a dead worker, and a per-person mute.
