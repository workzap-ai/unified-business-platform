# Video rooms: the transcript written from the audio (Urdu and other languages)

Part of PMB-5 (`pi-meeting-rooms.md`). Branch `pi/meeting-rooms-urdu`. Migration **0074** (additive).
Off unless the workspace has `response_rules.brain.meeting_room_audio` (default off) on top of
`meeting_room`.

## Why

The video provider's own captions do not understand Urdu (`ur` is not accepted; `auto` answers in
Urdu, Hindi script, or another language altogether). Phase 0 and the first live test showed lines
like "आपको प्राजाया चाहिए" for Urdu speech. Meetings with Urdu and Roman Urdu customers need a
transcript that is readable, so for a workspace that opts in, our own speech-to-text writes it.

## How

1. **Audio.** With the flag on, a new room's call turns on the provider's *individual recording*
   (`audio_only`): one file per person, named with their room user id (`s_` staff, `g_` guest).
   No video, no mixed track. The room row says `audio = true`.
2. **Consent says so.** The host's dialog, the guest page and the link card tell people, before they
   agree, that each voice is recorded briefly to write the transcript and then deleted. The
   meeting's consent note records it. The old wording ("no audio is saved") is used only when the
   flag is off.
3. **After the call.** The provider's captions are kept as lines (the fallback), and the meeting is
   NOT handed to analysis yet. A worker sweep (`sweep_meeting_rooms`, every 30 s) picks rooms that
   ended at least 45 s ago and are still `pending`; `finish_meeting_room` makes one attempt
   (`native_stt.finalize`):
   - lists the recordings; none yet means "wait" (up to 6 minutes or 12 tries);
   - downloads each file (only from the provider's CDN, at most 25 MB), transcribes it with Whisper
     (`stt_multi` alias: Groq `whisper-large-v3`, OpenAI `whisper-1`) with word times, in the
     meeting's language when it was chosen (Urdu, English, Hindi) or detected;
   - cuts the words into lines at a full stop (Latin, Urdu `۔ ؟`, Hindi `।`), a pause over 1.2 s, or
     400 characters; redacts phone, card and ID numbers; places each line under its speaker and
     time (the file's start relative to the earliest file, plus the word's time);
   - replaces the lines of the people it could read, keeps the provider's lines for the others,
     renumbers everything in the order it was said, and hands the meeting to analysis;
   - deletes the call at the provider (so the recordings and captions are gone there too).
4. **Fallback.** If no file could be read within the limits, the provider's transcript is used,
   exactly as without the flag. A person whose file fails keeps the provider's lines. Silence is not a
   transcript: no one heard means the meeting fails with "No speech was captured".
5. **Nothing is stored.** The audio is held in memory only while it is transcribed.

## What changed in shared code

- `app/ai`: `TranscriptionRequest.timestamps`, `TranscriptionResponse.words`, `manager.transcribe(...,
  timestamps=, max_bytes=)` (additive; the default is the old behaviour), alias `stt_multi` (a larger
  Whisper for Urdu; the usual `transcribe` alias is untouched, so WhatsApp voice notes do not change).
- The call type `pi_room` gets `individual_recording: available` (updated once, on first use).
- Stream is asked for captions in `ur` as `auto` (it rejects `ur`).

## Limits and risks

- A person's file over 25 MB (about 70 minutes of speech) is not transcribed from audio; their
  provider lines stay. Longer calls need chunking (not built).
- Whisper on Urdu mixed with English is good, not perfect; the language choice helps. Staff review
  every finding before anything reaches memory, as for any meeting.
- Cost: provider recording (audio) plus Whisper per minute; watch both before turning it on widely.
- An erase of the meeting or customer still removes the call at the provider first (the call may
  already be gone after a successful transcript; deleting a missing call is not an error).

## Code and tests

`pi_meetings/native_stt.py`, `room_jobs.py` (worker), `room_provider.py` (`recordings`, `download`,
`create_call(audio=)`, `caption_language`), `room_routes.py` (`/rooms/options`, audio flag, webhook
keeps captions as the fallback), `native_ingest.complete`, `app/worker.py`, migration
`0074_pi_meeting_room_audio.py`. Web: language and consent in `meeting-room-dialog.tsx`, guest and
link-card wording. Tests: `tests/unit/test_pi_room_stt.py`, `tests/integration/test_pi_meeting_rooms_stt.py`.

## Apply order

Run 0074 on the real database BEFORE deploying (the ORM selects every column), then deploy API and
worker. Turn `meeting_room_audio` on for a workspace only with the owner's word.
