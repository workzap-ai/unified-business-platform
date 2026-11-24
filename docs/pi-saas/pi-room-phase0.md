# PMB-5 Phase 0: what the Stream spike proved (2026-11-24)

Throwaway spike, not in the repo (local page and a small Python server, test calls deleted). Plan: the PMB-5 plan
(Stream Video rooms, pi listens and speaks). This file records only what was verified against the real Stream API,
and what is still open.

## Verified (real calls)

| Check | Result |
|---|---|
| Server keys: create, read, hard-delete a call | Works. |
| `@stream-io/video-react-sdk` 1.46.4 peer deps | React 17-19, matches Next 16 / React 19. The browser client is `@stream-io/video-client` (its own version, 1.67.2); 1.46.4 is the React SDK's version, not the client's. |
| Python agent joins a call (`getstream[webrtc]` 8.2.0, `getstream.video.rtc`) | Works. Needs `AsyncStream`, not `Stream`. Join takes about 3 to 5 s (once per call). |
| Agent publishes audio (`AudioStreamTrack`, `PcmData`) | A browser participant heard it. `flush()` exists on the track (barge-in candidate, not yet tested). |
| Live captions (`startClosedCaptions`) | Work. Each event has `id`, `text`, `start_time`, `end_time`, `speaker_id` (the Stream user id), `language`. There is no is-final flag: each event is a finished segment of 1.5 to 9 s. It arrives about 1 s after `end_time`. |
| Caption repeats | The same segment can arrive twice (same start time, later text). Idempotency key: the caption `id`, and a repeat replaces the earlier text. |
| Webhook signature | `getstream.webhook.verify_signature(body, signature, secret)` accepts a good HMAC-SHA256 hex and rejects a bad one. |

## Findings that change the plan

1. **Urdu.** `startClosedCaptions` accepts `auto en fr es de it nl pt pl ca cs da el fi id ja ru sv ta th tr hu ro zh ar tl he hi hr ko ms no uk bg et sl sk`. **`ur` is not accepted.** With `auto`, Urdu speech came out sometimes in Urdu script (good), sometimes in Devanagari Hindi, sometimes garbled. With `en`, Urdu came out as unrelated English. Decision for Phase 1: live captions use `auto` for the live view and for turn-taking only; the stored transcript for analysis is re-transcribed from the recording by our own STT (`app/ai` transcribe), which understands Urdu. Pi must never answer an Urdu customer from a caption it cannot trust: low-confidence or script-mixed segments are treated as unclear.
2. **One agent per call.** Pressing "Ask pi to join" four times put four `pi_agent` participants in the room. The room job must refuse a second join (heartbeat row, unique per call).
3. **Guest token scope is NOT proven.** `create_call_token(user, call_cids=[...])` did not stop a read of a different call (the call-info GET returned 200 for both). Do not rely on the claim alone. Plan: a custom call type with a locked-down `guest` role (join, audio, video, no call admin), unguessable call ids (uuid), tokens minted by our API only after the invite and consent are checked, short expiry. A real join-another-call test is a Phase 1 item.
4. **Caption language and wake name.** The wake-name check works on text; mis-heard names are expected, so "address pi" needs a fuzzy match plus a staff command path.

## Not yet verified

- Recording start, download, delete (needs a call with a participant; Phase 1).
- Barge-in with `flush()` and the time to silence.
- Latency and cost of text-to-speech: the `OPENAI_API_KEY` set on Railway is rejected by OpenAI (401), so TTS was not exercised. A working key (or the dashboard key store) is needed before Phase 2.
- Two real people on two devices; iOS autoplay; a call longer than a few minutes.

## Go / no-go

Go for Phase 1 (listen-only rooms), with the Urdu decision above. Go for Phase 2 only after TTS latency and barge-in are measured with a working key.
