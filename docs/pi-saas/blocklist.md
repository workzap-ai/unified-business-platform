# pi blocklist

Numbers pi no longer answers. Added after a flood of bulk-created Indonesian numbers
(`+62 895636626xxx` and neighbouring ranges, 14 to 16 Nov 2026) that each sent one black image and
nothing else. Every image cost a vision call, and with the AI providers out of quota each one also
told the sender "I couldn't open that file".

## What it does

- A row is one exact number, or a range: the start of a number, at least six digits (so a country
  code alone, `62` or `92`, can never be blocked by accident).
- A message from a blocked sender is dropped in `process_pi_event` before `persist_inbound`. It is
  not stored, no customer or chat is created, no model is called, nothing is sent back. The webhook
  event is closed as `processed` and the rule counts the try (`hits`, `last_hit_at`).
- The check fails open: if the lookup errors (for example the table is not migrated yet) it runs in
  a savepoint, logs `pi_blocklist_unavailable` and the message is handled as before.
- Blocking from the inbox or the API also closes the sender's open chats (their messages stay as a
  record). Unblocking switches the row off and keeps it; blocking it again switches it back on.
- Every change is written to the audit log (`pi.number_blocked`, `pi.numbers_blocked`,
  `pi.block_updated`, `pi.number_unblocked`).

## Where

| Part | Place |
|---|---|
| Table | `pi_blocked_contacts`, migration `0068_pi_blocklist` (additive, new table only) |
| Rules and lookup | `apps/api/app/modules/pi_saas/blocklist/` (`models.py`, `service.py`, `routes.py`) |
| Inbound hook | `runtime._blocked_sender`, called in `process_pi_event` |
| API | `GET /pi/blocklist`, `GET /pi/blocklist/suggestions`, `POST /pi/blocklist`, `POST /pi/blocklist/bulk`, `POST /pi/blocklist/from-conversation/{id}`, `PATCH` and `DELETE /pi/blocklist/{id}` |
| Permissions | read `pi.read`; block, unblock, edit `pi.settings.manage` |
| pi app | Settings, Blocklist (`/settings/blocklist`); a "Block this number" button in the inbox chat header |

`GET /pi/blocklist/suggestions` lists ranges (first nine digits) with at least three open chats that
only ever sent media and no text, and are not blocked yet: the mark of a bulk-created flood. The
Blocklist page shows them with a "Block this range" button.

## Rolling it out

1. Apply migration `0068_pi_blocklist` to the real database first (paste
   `alembic upgrade 0067_pi_nori_thread:0068_pi_blocklist --sql` into the Neon SQL editor, when the
   owner asks). Deploying the code first is safe (the check fails open) but blocks nothing.
2. Deploy. Open Settings, Blocklist: the flood ranges appear under "Possible flood".
3. Block the ranges that are the flood. Do not block a whole country.

Not done: the Owner OS web app (`apps/web`) has no Blocklist screen; its PI workspace can use the
same API.
