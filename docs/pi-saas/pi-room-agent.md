# pi room agent (pi speaks in video rooms): what is built, what is not proven

Branch `pi/room-speaks`. Off by default. Nothing here is live until the owner says "merge kro".

## How it works
Host presses "pi speaks" in a live room (`POST /api/v1/pi/meeting-intel/{id}/room/pi`, needs
`brain.meeting_room_speak` on the workspace) -> a separate service, `pi-room-agent`, claims the room
(`room_agent_claim.py`, one agent per call, 30 s lease renewed every 5 s) -> joins as `pi_agent`,
hears each person's audio, cuts it into turns (`room_vad.py`), transcribes each turn with Whisper
(`room_speech.py`), decides whether to speak (`room_turns.py`), and answers through the same gate as
every spoken reply (`voice.py`). pi's first words are always the AI disclosure, composed in code.
Mute, mode and intake are read from the room row every beat; a mute cuts pi off mid-sentence.

## Files (apps/api)
`room_turns.py` when to speak - `room_vad.py` audio to turns - `room_speech.py` turn to voice -
`room_agent.py` the SDK-free core - `room_agent_sdk.py` the process (the only SDK importer) -
`room_agent_claim.py` DB claim and orders - migration `0076` - `Dockerfile.room-agent`,
`requirements-room-agent.txt` - TTS in `app/ai` (`LLMManager.synthesize`).

## Verified (tests)
Unit: turns 27, VAD 8, speech 14, agent core 9, TTS gateway 9. Integration: claim/lease/mute/pause 8
plus the 29 existing room tests. Rules proven in tests: disclosure first, unsafe reply becomes the safe
line, silent unless named (or lone customer in intake), no talking over anyone, mute and talk-over cut
pi off, STT/TTS outage is silence, spoken phone numbers are redacted before the model sees them.

## NOT verified (needs the Linux service and a working OpenAI key)
1. `room_agent_sdk.py` against a live call (join, `connection.on("audio")`, `add_tracks`, `flush`).
2. OpenAI TTS: model `gpt-4o-mini-tts` and raw `pcm` at 24 kHz are assumed; the platform key answered 401.
3. Latency (turn end to first audio), barge-in feel, Urdu STT accuracy per short turn.
4. pi's own lines are not yet stored in the meeting transcript (only what people say is, from the recordings).
5. The room page has no "pi speaks / mute" buttons yet (API only).

## To go live
Apply migration 0076 first. Create Railway service `pi-room-agent` from `apps/api` with
`RAILWAY_DOCKERFILE_PATH=Dockerfile.room-agent` and the same env as the worker (DATABASE_URL,
STREAM_API_KEY/SECRET, OPENAI_API_KEY). Turn on `meeting_room_speak` for one workspace.
