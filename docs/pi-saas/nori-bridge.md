# nori credits bridge (pi side)

Status: built and tested offline on branch `feat/nori-bridge`; not deployed, not enabled anywhere.
The nori side and its contract live in the nori repo (`docs/credits-pi-contract.md`,
`scripts/credits-pi-simulator.mjs`). Code: `apps/api/app/modules/pi_saas/nori_credits/`.

## What it does

1. **Inbound pre-hook.** For each inbound WhatsApp text message in an enabled workspace, pi first
   calls nori `identify` with the sender's number only. An unknown number (or a failed call) ends
   there and pi carries on exactly as before: no message text leaves pi. For a nori member the message
   goes to `POST /api/workzap/inbound`. If nori answers `handled: true`, pi sends nori's `reply`
   through its normal WhatsApp adapter and the brain does not run for that message. Otherwise pi
   continues unchanged.
2. **Send door.** `POST /api/pi/nori-send` lets nori send a queued credits notification through pi's
   WhatsApp adapter (text, or an approved template when the body carries `template`).
3. **Capture library.** `capture_nori_item(...)`, `nori_item_status`, `nori_item_followups`,
   `nori_item_reply` call nori's requirements inbox for what a member needs or what is broken in
   nori. **Not wired into the brain** (see Extension point).

## Gates: off unless all of these are true

| Gate | Where | Default |
|---|---|---|
| `NORI_BASE_URL` (https origin of nori, for example `https://nori.example.com`) | server env | unset |
| `WORKZAP_BRIDGE_SECRET` (16+ characters, the same secret nori has) | server env | unset |
| `response_rules.nori_bridge.enabled` is exactly `true` | per workspace setting | `false` |
| `NORI_BRIDGE_KILL=true` | server env | unset (kills both doors) |

With either variable missing, the hook returns before any database read or HTTP call and the send
door answers 503 `not_configured`: pi behaves as before. With the flag off the hook makes no HTTP
call to nori (tests assert this).

Optional workspace settings under `response_rules.nori_bridge`: `timeout_seconds` (default 2.5, range
0.5 to 5), `breaker_failures` (5), `breaker_cooldown_seconds` (30), `send_enabled` (true),
`send_per_minute` (60), `capture` (false, reserved for the extension point).

Workzap Connect (`nori_bridge.py`, `NORI_BRIDGE_URL`) is a separate, older bridge. For a connection
whose number it already serves, this hook steps aside (it already posts every message to the same
nori door); do not enable both for the same number.

## Safety behaviour

- **Fail open** on timeout, connect error, non-2xx, 401/403 (bad signature), malformed answer, and an
  open circuit: pi continues as if the hook did not exist.
- **Circuit breaker** (per process): opens after N consecutive failures, one half-open probe after the
  cooldown.
- **Idempotency:** the WhatsApp message id is claimed in `pi_nori_bridge_log` before the text is
  posted; a retry never replies twice.
- **No PII in logs or audit:** numbers are masked (`92***4567`), text is never logged or stored.
- **Counters:** log lines `nori_bridge_metric` with a `metric` key (for example `inbound:handled`,
  `call:timeout`, `send:replay`); `resilience.METRICS.snapshot()` in process.
- **Send door checks, in order:** kill switch and config (503), body 8 KB (413), HMAC over the raw body,
  constant-time (401), a workspace with the flag on (503), body shape (400), timestamp within 10
  minutes (401), replay of timestamp plus signature for 24 hours (409), per-minute limit (429),
  recipient must be a nori member per `identify` or a number that has messaged pi (403), content: at
  most 1000 characters, no link except nori's own host, valid template shape (422), then the send
  (200, or 422/502 with a short reason). Every request after the signature leaves one audit row.
- **The brain is untouched.** No state-machine rule, linter or decision gate changed.

## System replies bypass the reply linter, by design

nori's replies are system messages, like pi's existing opt-out confirmation, not brain output. They
skip the linter (AI disclosure, one question, British spelling) because nori owns the wording, and a
member can change it in nori settings. pi only strips control and direction characters, caps the reply
at 1000 characters and replaces any reply containing a link that is not nori's own host with
"Done. Please open nori to see the details.". Texts nori can send through the inbound door: the
balance (`You have N credits left`), the top-up order (amount and how to pay), "request #N received",
the priority change confirmation, status, the "only the company owner can buy credits" refusal, the
new-builds-not-allowed refusal, the "not set up" text (only for a number pi has just confirmed as a
member, so in practice not sent), and the requirements-inbox replies. Through the send door: low
balance, statement ready, urgent request alert, top-up confirmed, and the team's status, question or
"fixed" messages.

## Staged rollout

0. **Flag off (today).** Deploy the migration `0062` (additive: one new table) and the code. Leave
   `NORI_BASE_URL` and `WORKZAP_BRIDGE_SECRET` unset, or leave the flag false. Verify pi is unchanged.
1. **Test workspace and test number.** Set both variables on the API service. Set
   `NORI_BRIDGE_KILL` unset. Enable the flag on a test workspace only (below). Message from a number
   that is a nori member (balance) and from one that is not; confirm both behaviours.
2. **One pilot client.** Enable on that client's workspace. Point nori's `WORKZAP_PI_SEND_URL` to
   `https://<pi api host>/api/pi/nori-send`. Watch for a week.
3. **More clients,** one at a time.

Enable on a workspace (paste into the Neon SQL editor yourself; Claude does not write to the real
database), by the workspace's `pi_settings.id`, merging so other rules stay:

```sql
UPDATE pi_settings s
SET response_rules = s.response_rules
  || jsonb_build_object('nori_bridge', '{"enabled": true}'::jsonb)
WHERE s.id = '<pi_settings id of the TEST workspace>'
RETURNING s.id, s.response_rules->'nori_bridge';
```

The setting can also be saved through the settings API (`PATCH /api/v1/pi/settings/response_rules`
with `{"value": {"nori_bridge": {"enabled": true}}}`), which validates it.

## Verify with the nori simulator

From the nori repo, read-only calls against deployed nori with the same secret:
`WORKZAP_BRIDGE_SECRET=... node scripts/credits-pi-simulator.mjs --base https://<nori host> --from <member number>`.
It checks the signature refusal, `identify` and the inbound `balance`. For pi's half run
`pytest tests/integration/test_nori_credits_bridge.py` (ports the simulator's scenarios) on the
disposable database. To test the send door end to end, have nori queue a notification to the test
number and confirm WhatsApp delivery and one `sent_text` audit row.

## Monitor

```sql
-- send door outcomes, last day
SELECT outcome, reason, count(*) FROM pi_nori_bridge_log
WHERE kind = 'send' AND created_at > now() - interval '1 day' GROUP BY 1, 2 ORDER BY 3 DESC;
-- inbound: how many messages nori handled, passed or failed open
SELECT outcome, reason, count(*) FROM pi_nori_bridge_log
WHERE kind = 'inbound' AND created_at > now() - interval '1 day' GROUP BY 1, 2;
```

Also watch log lines `nori_bridge_failopen`, `nori_bridge_send_bad_signature` and metrics
`call:circuit_open`, `call:timeout`, `inbound:failopen_*`. A rise in `failopen` or `circuit_open` means
nori is slow or the secret differs; pi keeps working meanwhile. Rows are purged by the bridge
(replay 24 hours, inbound 7 days, audit 90 days).

## Kill switch and exact rollback

- **Immediate:** set `NORI_BRIDGE_KILL=true` on the API service and restart: the hook passes every
  message on and the send door answers 503.
- **Per workspace:** set `response_rules.nori_bridge.enabled` to false (SQL above with `false`).
- **Full:** unset `NORI_BASE_URL` or `WORKZAP_BRIDGE_SECRET`; the module is inert. Ask nori to clear
  `WORKZAP_PI_SEND_URL`.
- **Code and table:** revert the deployment; `alembic downgrade 0061_pi_meeting_analysis`
  drops `pi_nori_bridge_log` (audit and replay keys are lost). Leaving the
  table is harmless.

## Extension point: capture from the brain (not wired)

pi's brain has no narrow hook for "the owner asked pi to tell the Workzap team", and adding one would
touch rules that are never weakened (one question per message, no solution while listening). So
`capture.py` is a library only. To wire it later, from a place that has decided the member explicitly
asked (`capture.explicit_request(text)` is a narrow detector, for example "tell the Workzap team ..."),
build a `NoriClient(read_env(settings), http, workspace_bridge(rules))` for a workspace with the flag
and `capture` on, call `capture_nori_item(client, sender, kind=..., title=..., ...)`, and send
`result.reply` as a system reply. It checks `identify` first and sends nothing for a non-member.
