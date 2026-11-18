# Nori support mode (pi answers a nori user)

Status: pi side built behind flags, OFF everywhere. Needs nori's read-only `workspace_info` door
(contract below) before the replies can carry workspace facts. Code:
`apps/api/app/modules/pi_saas/nori_support/`.

## What it does

A person on the Nori Platform **registry** (`pi_nori_numbers`, see `nori-board.md`) writes to pi on
WhatsApp. Today pi files a card and stays silent. With `response_rules.nori_bridge.support = true`
pi answers them itself as nori support:

- questions about nori and their own workspace (plan, trial, subscription, credits, nori's health)
  are answered **only from nori's facts**;
- what they need or what is broken is noted and passed to the Workzap team (the card is filed exactly
  as before; the reply says so);
- a fact pi does not have is never guessed: pi says it will check with the team.

The sales brain never runs for a registry number (unchanged). Every other number is untouched.

## Flags (per workspace, `response_rules.nori_bridge`, exact `true`, default OFF)

| Flag | Effect |
|---|---|
| `support` | the support reply described here (needs `enabled` and `board`) |
| `remind` | trial/subscription reminders to the workspace owner (built in a later step) |

`NORI_BRIDGE_KILL=true` turns support off at once (the acknowledgement path remains).

## Order of work for one message

1. The bridge hook files the card (unchanged) and puts the chat in human mode.
2. Fixed gates, no model: advice that is not pi's to give (legal, medical, tax...) and card, password
   or ID typed in chat get a fixed line from `safety.py`.
3. `workspace_info` from nori (read-only, cached 10 minutes in the process, never stored).
4. One small model call (`pi_nori_support`, alias from the workspace's router alias): the rules, then
   nori's facts and the last 8 messages as **data**, then the person's message.
5. `guards.vet`: reply dropped (acknowledgement sent instead) unless it passes: at most 700
   characters; no card/password/OTP/ID/bank words; no link except nori's own host; every number in
   it appears in nori's facts or the person's own words; every month name likewise; at most one
   question and it is last; the first reply of a chat says "I'm pi, an AI assistant" (added when the
   model forgot, in the person's language).
6. Per chat at most 40 support replies a day. Any exception returns to the acknowledgement.

## nori contract: `workspace_info` (read-only)

`POST /api/credits/pi`, same HMAC and `ts` rules as `identify`. Request
`{"action":"workspace_info","from":"<digits>","ts":...}`. Answer `200`:

```json
{"ok": true, "known": true, "workspace": {
  "id": "...", "name": "Mendeez Demo",
  "business": {"industry": "retail", "summary": "...", "country": "PK"},
  "owner": {"name": "...", "phone": "923..."},
  "plan": "Starter", "status": "trial|active|expired|suspended",
  "trial_ends_at": "2026-11-20T10:00:00Z", "subscription_ends_at": null,
  "credits": 120, "credits_low": false,
  "health": {"status": "ok|degraded|incident", "note": null, "updated_at": "..."}}}
```

Unknown number: `{"ok": true, "known": false}`. Every field nori does not have is `null`. pi never
shows the owner's phone to the model; it is used only by reminders.

## Rollback

Set `support` to false (or `NORI_BRIDGE_KILL=true`): replies stop, cards and the acknowledgement stay.
No migration in this step.

## Tests

`tests/unit/test_nori_support_guards.py`, `tests/integration/test_nori_support_flow.py` (fake nori with
`workspace_info`, fake model). Disposable database only.
