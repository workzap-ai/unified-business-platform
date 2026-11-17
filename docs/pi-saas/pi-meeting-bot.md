# pi meeting bot: pi joins a Zoom, Meet or Teams call

Part of PMB (`pi-meeting-brain.md`). Branch `pi/meeting-brain`. Provider: Recall.ai. Status: built and
tested with a fake provider; **not yet run against a live Recall account**.

## What it does

A person with `pi.meetings.record` pastes a Zoom, Google Meet or Teams link on **Meeting intelligence →
Send pi to a call**, confirms that everyone in the call will be told, and presses the button. A bot
joins as **"pi (AI) - Workzap notetaker"**, so the call itself shows that an AI is there, and the host can
remove it at any moment. The provider sends the words as they are said; each utterance becomes a
transcript line with the name the call shows for that speaker (role `unknown`, never "customer" until a
person maps it). When the call ends the meeting goes to the same analysis and review as any other, and
nothing reaches the Problem Map until a person approves it.

pi **listens only**. It does not speak in a call yet (see "Not built").

## Switches and setup (all must be true)

| What | Where |
|---|---|
| `response_rules.brain.meeting_intel` and `response_rules.brain.meeting_bot` | per workspace, default off |
| `RECALL_API_KEY` | Railway env (API service). Never in chat or the repo |
| `RECALL_REGION` | the region the key was created in: `us-west-2` (default), `us-east-1`, `eu-central-1`, `ap-northeast-1` |
| `RECALL_WEBHOOK_SECRET` | one or several `whsec_...` separated by commas (the dashboard endpoint and the per-bot transcript webhook can be signed by different secrets), from Recall dashboard: Developers, API Keys & Secrets, Create Workspace Secret. Without it the callback route refuses everything |
| `INTEGRATIONS_PUBLIC_BASE_URL` | public https origin of the API; the transcript callback URL is built from it |
| Recall dashboard webhook endpoint | `https://<api>/api/v1/public/recall/webhook`, events `bot.*`. Optional: without it the page asks Recall for the status itself while pi is in the call, but the end of the call is noticed only when someone has the page open |

Migration `0070_pi_meeting_bots` (additive: one table, `source` check widened by `teams`) must be applied
BEFORE the code is deployed. It follows `0069_pi_meeting_pi_mode`.

## Rules in code

- Only real `https` Zoom, Google Meet and Teams invitations reach the provider (host and path are
  checked; look-alike hosts, logins in the address, odd ports and other sites are refused).
- Consent is required to send the bot. The call's link is **not stored** (it can carry a passcode): only
  its host and a hash that stops the same call being joined twice. The audit log carries ids, source and
  host, never the link or any words.
- Callbacks are verified by HMAC-SHA256 signature before the body is read. Unknown bot, workspace switched
  off, or a late/out-of-order status changes nothing. A retried utterance is stored once.
- Words are redacted before they are stored (phone, card, ID numbers). Nobody in a call can take the label
  "pi (AI)" or "Speaker 1".
- A status only moves forward. "Denied" and "failed" mark the meeting failed with a plain reason; "done"
  with no speech marks it failed ("No speech was captured"), otherwise `analysing`.
- One call has at most 20,000 lines.

## Code

`pi_meetings/bot_provider.py` (link check, `BotProvider` interface, Recall adapter, signature check) ·
`bot_ingest.py` (status and words into the meeting) · `bot_routes.py` (`POST /pi/meeting-intel/bot`,
`GET /{id}/bot`, `POST /{id}/bot/leave`, public `POST /public/recall/webhook`) · web
`workspace/meeting-send-bot.tsx`, `meeting-bot-card.tsx`. Tests: `tests/unit/test_pi_meeting_bot_provider.py`,
`tests/integration/test_pi_meeting_bot.py`.

Another provider (for example the open-source Vexa) is added by writing one more class with `join`,
`leave` and `status`, and a callback route that calls `bot_ingest`.

## Unverified (facts taken from Recall's documentation on 2026-11-17, not from a live call)

- The request and callback shapes, `Authorization: Token <key>`, region base URLs and the signature scheme.
- Whether `language_code` accepts Urdu in streaming transcription (the default sent is `en`).
- How a Zoom call behaves when the host requires approval, or when the account blocks recording bots.
- Price: pay as you go is quoted at $0.50 per hour of recording; free sign-up credits exist, amount unknown.

## Not built

- pi speaking in the call (needs text-to-speech and Recall "output audio"/"output media"; the existing
  one-question spoken rules in `voice.py` would apply, and the host's mute must be instant).
- Scheduling a bot from the calendar; a "bot stuck waiting" timeout; erasing the provider's copy of the
  media after the call (Recall keeps recordings until deleted; check its retention setting).
