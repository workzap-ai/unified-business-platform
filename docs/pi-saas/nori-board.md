# Nori Platform board (pi side)

Status: built and tested offline on branch `feat/nori-platform-board` (off `feat/nori-bridge`). Not
deployed, not enabled anywhere. Needs migrations `0063_pi_nori_board` (two new tables), `0064_pi_nori_item_chat` (one nullable column) and `0065_pi_nori_forward` (five additive columns).

nori is Workzap's own product. Its users write to the Workzap number on WhatsApp: a feature they
need, a problem, feedback, a module idea. pi **only listens and passes it on**: each such message
becomes a card on the "Nori Platform" tab of the team board in the Workzap workspace, with the nori
workspace, the person and the department. The Workzap team works the cards like any other board card
(assign, move, done). pi's brain, linter and decision gates are not touched.

## Three ways a card appears

| Source | How | `source` on the card |
|---|---|---|
| nori pushes it | `POST /api/pi/nori-board` (signed, see below) after nori filed the item in its requirements inbox | `nori` |
| a number on the board registry writes to pi | the bridge hook files the message and answers one line; pi's sales brain never runs for it | `whatsapp` |
| the team adds it | "Add requirement" on the board (`POST /api/v1/pi/nori-board/items`) | `manual` |

The registry is the list of numbers on the board's "Nori numbers" panel (workspace, person,
department, on/off). Messages from numbers not on it behave exactly as before: nori's `identify`
decides (the credits bridge), otherwise the brain.

## Gates: off unless all of these are true

Same as the credits bridge (`docs/pi-saas/nori-bridge.md`) plus one flag:

| Gate | Where | Default |
|---|---|---|
| `NORI_BASE_URL`, `WORKZAP_BRIDGE_SECRET` (16+ chars) | server env | unset: the door answers 503 `not_configured`, the hook does nothing |
| `NORI_BRIDGE_KILL=true` | server env | unset; kills the door and the hook |
| `response_rules.nori_bridge.enabled` is exactly `true` | per workspace | `false` |
| `response_rules.nori_bridge.board` is exactly `true` | per workspace | `false` |

```sql
-- paste into the Neon SQL editor yourself, by the Workzap workspace's pi_settings.id
UPDATE pi_settings s
SET response_rules = s.response_rules
  || jsonb_build_object('nori_bridge',
       COALESCE(s.response_rules->'nori_bridge', '{}'::jsonb) || '{"enabled": true, "board": true}'::jsonb)
WHERE s.id = '<pi_settings id of the Workzap workspace>'
RETURNING s.id, s.response_rules->'nori_bridge';
```

The setting can also be saved with `PATCH /api/v1/pi/settings/response_rules`
(`{"value": {"nori_bridge": {"enabled": true, "board": true}}}`).

## The door: nori to pi

`POST https://<pi api host>/api/pi/nori-board`, header `X-Workzap-Signature: sha256=<hex HMAC-SHA256
of the raw body>` (same secret and recipe as `nori-send`). JSON body, at most 8 KB:

```json
{"ref": "rq-12", "kind": "feature", "title": "Van sales module", "text": "We need van sales",
 "workspace": "Mendeez", "person": "Ali", "department": "Sales", "phone": "923001234567",
 "priority": "normal", "url": "https://nori.example.com/help/requests/12", "ts": 1767000000000}
```

`ref` (1 to 80 of `A-Za-z0-9_.:-`), `kind` (`feature|problem|feedback|module|question|change|note`),
`workspace` and one of `title`/`text` are required. `url` must be https on nori's own host.
`ts` is epoch seconds or milliseconds within 10 minutes.

Answers: `200 {"ok":true,"id":"<card id>","created":true|false}` (`false`: that `ref` was filed
before, nothing changed, so retries are safe), `503 not_configured|disabled`, `413`, `401
bad_signature|stale`, `409 replay` (the same ts and signature twice: use a fresh `ts` per attempt),
`400 bad_json|bad_ref|bad_kind|bad_text|bad_item|bad_priority|bad_phone|bad_url`, `429 rate_limited`
(the workspace's `send_per_minute`, default 60), `500 internal_error`.

Order of checks and the audit rows follow the send door (`nori_board/door.py`). Audit rows (kind
`board` in `pi_nori_bridge_log`) hold the outcome and a masked number, never the text; replay keys
live 24 hours, audit rows 90 days.

## The numbers door: nori tells pi about a team member

`POST https://<pi api host>/api/pi/nori-numbers`, same header, secret, 8 KB limit and `ts` rule as
the board door. Same gates (server variables, kill switch, `nori_bridge.enabled` and `board` on).

```json
{"ref": "nori-member:12", "workspace": "Mendeez", "person": "Sara", "role": "Head of Stock",
 "department": "Stock", "phone": "+92 300 777 0002", "active": true, "ts": 1767000000000}
```

`ref` (1 to 80 of `A-Za-z0-9_.:-`), `workspace` (1 to 120) and `phone` (7 to 15 digits after `+`,
spaces and dashes are removed) are required; `person` 0 to 120, `department` 0 to 80, `role` 0 to 60,
`active` a real boolean (default true). The registry's key is the phone number in the workspace:
a repeat updates the row. The role is stored in brackets after the person ("Sara (Head of Stock)").

- A new number is added with source `nori`.
- A number the team added by hand keeps source `manual`. nori may switch it off but never back on:
  the team's own switch wins.

Answers: `200 {"ok":true,"created":true|false}`, `400 bad_json|bad_ref|bad_workspace|bad_phone|
bad_item`, `401 bad_signature|stale`, `409 replay` (fresh `ts` per attempt), `413`, `429
rate_limited` (shares the board's per-minute count), `503 not_configured|disabled|ambiguous`.
Audit rows use kind `board` and hold the outcome and a masked number only.

## Sending a registry person's card to nori (default OFF)

Migration `0065_pi_nori_forward` (additive columns). With `response_rules.nori_bridge.forward`
exactly `true` (plus `enabled` and `board`), the worker's sweep (about every minute) posts a card
to nori's requirement inbox: `POST <NORI_BASE_URL>/api/pi/board-card`, same signature, secret and
`ts` rule as the other doors, body `{ref, card_id, text, kind, person?}`.

- `ref` is nori's own ref for the number, kept when nori pushes it (`nori-link:...` or
  `nori-member:...`). A number added by hand has none and is never sent.
- `card_id` is pi's card id, nori's idempotency key (a repeat answers `duplicate: true`).
- `text` is the board card's redacted text (card numbers, passwords and ID numbers removed), up to
  5000 characters. The phone number is not sent (nori reads it from the ref).
- 200 marks the card sent. 400 (for example `unknown_ref`) is final: the reason is kept in
  `pi_nori_items.forward_note` and the card is not retried. 401, 429, 5xx and timeouts are retried
  up to 6 times. A card older than 24 hours is no longer sent.
- Turning the flag on later sends cards still owed from the last 24 hours.
- Erasing a customer in pi clears the pi card but cannot delete the copy nori already holds.

## The registry path (a number on the board writes to pi)

In the bridge hook, before nori's `identify`: if the workspace has `board` on and the sender is on
the registry and switched on, pi claims the WhatsApp message id and files the card in one savepoint.
The message then goes on through pi's normal intake, so it **appears in the inbox as a chat**: the
runtime puts that chat in human mode (pi's brain stays silent), links the card to the chat
(`pi_nori_items.conversation_id`, migration `0064`), and sends `I'm pi, an AI assistant. I've passed
this to the Workzap team.` once per chat (queued like any outbound message). The card shows
"Open chat"; the team replies from the inbox as in any human takeover. A failure saves nothing and
the person gets `... I could not save that just now. Please send it again.` A repeat of the same
message id files nothing and sends nothing. An emergency or a "stop" from such a number is not
filed: pi's own pre-model gates answer it. Only text messages reach the hook; a photo, voice note or
file still goes to pi's normal pipeline (see Not covered).

The kind of a message that arrives without one is a hint from a keyword list in English and Roman
Urdu (`service.classify`): problem, feature, question, feedback, else note. The team reads the whole
text on the card.

## Privacy

Card text is stored with card numbers, passwords, ID and account numbers and third parties' contact
details taken out (`safety.redact_pii`). The card shows the sender's number masked. The registry
holds the full number (needed to recognise the sender) and shows it in full only to people with
`pi.work.manage`.

## The team's API (Owner OS and pi app, same routes as the team board)

`GET /pi/nori-board/numbers` (`pi.work.read`), `POST /numbers`, `PATCH /numbers/{id}`, `DELETE
/numbers/{id}`, `POST /items` (`pi.work.manage`). The board itself is `GET /pi/team-board?kind=nori`;
each card has a `nori` object (null for other kinds) with `item_kind, workspace, person, department,
phone_mask, source, url`. Nori cards are never closed by the board's automatic sync; the team moves
them.

## Not covered (honest list)

- Photos, voice notes and files do not reach the board: the bridge hook only sees text messages.
  nori's plan (not confirmed with its owner) is to send such people to its web form.
- A message from a registry number is filed even if it is a greeting; there is no spam filter beyond
  the on/off switch of the number.
- No WhatsApp or email alert to the team for a new card yet: only the in-app notification
  (`pi.nori.item`, for people with `pi.work.read`) and the board count.
- The frontend (`apps/web`, `apps/pi`) was type-checked and linted, not exercised against the API.
- Migration `0063` chains after `0062_pi_nori_bridge_log`. `pi/meeting-brain` has its own `0062`
  (`pi_meeting_pi_mode`): whoever merges both must re-chain one of them.

## Rollback

Immediate: `NORI_BRIDGE_KILL=true` and restart. Per workspace: set `board` to false. Code: revert the
deployment; `alembic downgrade 0062_pi_nori_bridge_log` drops `pi_nori_items` and `pi_nori_numbers`
(the cards stay as plain team-board cards).

## A photo or file with the card (default OFF)

pi never stores a customer's media (it keeps the provider's media id and fetches on demand behind the
app login). Nori cannot log in, so with `response_rules.nori_bridge.forward_media` exactly true (and
`forward` on) the forwarded card carries `files: [{kind, url, name?}]`, one entry, where `url` is
`<INTEGRATIONS_PUBLIC_BASE_URL>/api/pi/nori-media/<token>`.

- The token is `<card id>.<expiry>.<tag>`: HMAC with the bridge secret, domain-separated, 30 days. It
  cannot be moved to another card or extended.
- `GET /api/pi/nori-media/<token>` is public but answers the same plain 404 for everything that is
  wrong: bad or expired token, bridge off or killed, `forward`/`forward_media` off, card without a
  WhatsApp message, file gone at the provider. It streams the file with `attachment`, `nosniff`,
  `no-store`; nothing is copied or cached.
- No link is made unless `INTEGRATIONS_PUBLIC_BASE_URL` is an https address.
- Migration 0066 adds `pi_nori_items.message_id` (nullable), set when the chat is linked to the card.
- Size is not sent (pi does not know it); nori applies its own 25 MB cap when it opens the link.
- Turn it on only after nori's door accepts `files`.

## The whole chat to nori (default OFF)

With `response_rules.nori_bridge.forward_messages` exactly true, the worker sweep offers every message
of a registry person's chat to nori's `POST /api/pi/board-message` (signed like board-card):
`{ref, message_id, direction in|out, from person|team|pi, text, at, person?, card_id?, files?}`.

- Only numbers that carry nori's own ref (`pi_nori_numbers.nori_ref`); a number added by hand is never
  sent. Greetings kept in the chat without a card are sent too.
- `text` is redacted like board cards; `at` is pi's save time (ms); `message_id` is pi's message id;
  `card_id` links a message that also became a card; files reuse the signed media link
  (`forward_media`).
- Only the last 24 hours are owed, so switching the flag on does not back-fill old chats.
- Ledger `pi_nori_thread` (migration 0067): one row per message, sent once, up to 6 tries, a 400/413
  from nori is final and its reason is kept in `note`.
- Nori's own flag (`PI_MESSAGES_ENABLED`) must be on first: a disabled door answers 503, which the
  shared breaker counts as a failure.
- Erasing a customer in pi cannot delete nori's copy (nori has its own erase button).
