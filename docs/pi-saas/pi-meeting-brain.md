# PI Meeting Brain (PMB)

Meeting Intelligence built inside the existing pi codebase. It feeds the same brain
(Customer Memory, Problem Map, approval desk) that WhatsApp uses. There is no second memory system.

Branch: `pi/meeting-brain`. Flag: `response_rules.brain.meeting_intel` (default off, needs `pi_mode = "brain"`).

## Phases

| Phase | Scope | Status |
|---|---|---|
| PMB-0 | Stabilise: fix stale tests, record baseline | Done (see below) |
| PMB-1 | Meeting-to-Brain core: tables, ingest, transcribe, analyse, approve, apps/web UI | Done except stored audio: data layer, analysis, brain bridge, API, UI, transcript import, **browser recording with speech-to-text** (below) |
| PMB-2 | Brain strengthening: speaker-to-owner mapping, contradiction detection | Not started |
| PMB-3 | Zoom and Google Meet via platform APIs (no bot) | Not started |
| PMB-4 | Native video (LiveKit) | Not started |

## Decisions (owner, 2026-11-05)

- Native video: hosted SDK (LiveKit by default).
- Zoom and Meet: platform APIs after the meeting, no bot.
- Recordings: S3 or R2 with presigned URLs.
- Phase 1: Meeting-to-Brain core.
- UI: `apps/web` first; `apps/pi` later as a thin view over the same API.

## Baseline (2026-11-05, origin/main dc909471, disposable Postgres on :55432)

- Unit suite on clean main: 20,009 passed, 3 failed. All 3 were stale tests after commit 5e4eef66:
  - `test_pi_flow`: `advance_flow` reads `turn._exploration`.
  - `test_pi_live_fixes`: `without_repeats` returns `""` when nothing new is left.
  - `test_pi_roman_urdu_noted`: `solution_context.build` returns `{}` early for practical solution requests.
  Fixed in tests only (commit bdf372f3); the 3 files now pass (99 tests).
- Brain integration (`tests/integration/*brain*.py`, 10 files): 81 passed in 254 s.
- Full integration suite (193 files): not yet run.
- Production: alembic 0056. Migration for PMB-1 will be 0057 (check `alembic heads` first).

## Reuse (no duplicates)

- Memory writes: `pi/memory_ledger.py` (`record_decision`, `redacted`); meeting facts use a namespaced
  `subject_ref` such as `meeting:<id>:...` because `pi_decisions.kind` is fixed in production.
- Problem Map: `pi/problems.py` (`apply_ops`, `check_ops`). Lines from a speaker not mapped to the
  customer land as `draft` / `pi_inferred`.
- Approval desk: `pi_saas/requests.py raise_request`.
- Jobs: ARQ (`worker.py`, `core/jobs.py`), idempotent job ids `meeting:<id>:<stage>`, resumable after a restart.
- Storage: `integrations/providers/s3.py` with `scoped_key`.
- Erase and export: every new table must be added to `brain_erase.py` and the customer export.

## Rules that apply to meetings

- AI conclusions are stored with a `basis` (stated, inferred, estimate, recommendation) and never
  written to memory as customer facts without approval.
- Redact card, ID, phone and email before storing; roles, not third-party names.
- Audit records hold ids only, never transcript text (audit truncates at 300 chars).
- Recording needs explicit consent per meeting. Proposed default: audio kept 90 days, transcript until customer erase.
- A quote or document derived from a meeting still needs reviewer approval; the module never prices.

## Needed from the owner before activation

S3 or R2 bucket and keys, STT provider keys and budget, consent and retention decision, and (for
production) the migration pasted by the owner. Phase 3 needs a Zoom app and Google OAuth verification.

## Recording and speech-to-text (built 2026-11-06)

- Browser: `apps/web` `meeting-recorder.tsx`. Microphone, or microphone plus a shared call tab (online
  meetings). The recording is cut into self-contained parts of 4 minutes; each part is sent on its own
  (3 tries, then skipped and counted) and the screen is kept awake. Needs `microphone=(self)` and
  `display-capture=(self)` in the `Permissions-Policy` header (`next.config.ts`).
- API: `recording_routes.py`. `POST /pi/meeting-intel/{id}/recording/parts` (multipart: `index`,
  `offset_ms`, `duration_ms`, `file`) transcribes one part through `LLMManager.transcribe` (alias
  `stt`) and writes redacted, timestamped segments at ordinals `index * 1000 + n`, so sending a part
  again replaces it. `POST .../recording/complete` moves the meeting to `analysing`; the existing
  Analyse button and review flow are unchanged. No migration: it uses the 0057 tables.
- Parts of at most 8 MB, so the provider's 25 MB limit and request timeouts never apply to a long meeting.
- Consent is checked again on every part. A reviewed meeting is not reopened (409).
- Speech-to-text cannot tell speakers apart: every segment belongs to "Speaker 1" of unknown role, so
  nothing is treated as the customer's own words until a person confirms the speaker (PMB-2 adds the
  mapping). Segment times inside a part are proportional to text length (an estimate); part offsets are exact.

### Live meetings (Zoom, Google Meet, in person) and the complete transcript

Decision (owner, 2026-11-06): live capture from the browser, no bot and no platform approval. The person
shares the Zoom or Meet tab or screen with its audio (and the microphone) in the recorder; the other side
is heard through the shared audio.

- **Live requirement mapping.** After each part is transcribed the browser calls
  `POST /pi/meeting-intel/{id}/analyse/part/{n}`: one cheap model call over that part plus 6 earlier lines
  for context. New findings are added to the review list; earlier and reviewed ones are never touched, and the
  same part twice does not double anything (`analyse.store_part`). They are proposals only: nothing reaches the
  customer's memory before approval. The whole-meeting analysis ("Analyse with pi") is still available once the
  recording is finished and reasons across parts; its chunks now run four at a time.
- **A call or a quiet minute does not stop it.** An unreadable or silent part is skipped; the meeting is marked
  failed only if nothing has been heard yet. A failed live analysis never changes the meeting.
- **The page refreshes by itself** every 15 s while recording (newest 200 lines, findings, "N mapped").
- **Complete transcript, any length.** `GET .../transcript?offset=&limit=` pages through every line
  (`total`, `next_offset`); `GET .../transcript/download` is one text file of the whole meeting; the detail view
  reports `segments_total` and the UI reads on to the last line. Parts are capped at 400 (about 26 hours).
- A part already heard and analysed cannot be re-sent (409 `MEETING_PART_ANALYSED`), so insights never point at
  rewritten lines; the recorder counts such a retry as sent.
- Not covered: a tab closed or a computer asleep during the meeting loses the part being recorded (parts already
  sent are kept). Unsent parts are not saved to the browser's storage yet.
- **Platform real-time APIs (Zoom RTMS, Meet Media API) and a notetaker bot were not chosen.** They need app
  approval, or reverse the "no bot" decision; Zoom and Meet transcripts after the meeting through their APIs
  (PMB-3) remain open.

### Saved recordings, summary and the requirement map (built 2026-11-06)

- **Save the recording** is the person's choice on the recorder (consent is checked again on every part).
  Migration `0059_pi_meeting_media` adds `pi_meeting_media` (one row per stored part: key, size, position,
  keep-until date) and `pi_meeting_media_data` (audio bytes when there is no bucket). **Apply 0059 in Neon
  BEFORE deploying this code** (the owner pastes it; it has been run up, down and up on the disposable DB).
- **Hybrid storage** (owner decision): with an S3/R2 bucket connected (Settings -> Integrations) audio and
  video both go to the bucket under `t/<tenant>/e/<env>/meetings/<meeting>/<kind>/<part>` and play from
  one-hour signed links. With no bucket, audio only is kept in the database (150 MB cap per meeting) and played
  from `GET .../recording/media/audio/{n}/file` (authenticated, byte ranges); video is refused with 409
  `MEETING_VIDEO_NEEDS_STORAGE`. Video is recorded in 2-minute parts, audio parts ride with the transcription.
- **Consent to save**: separate from consent to record. `POST .../recording/save-consent` sets
  `media_consent_at` / `media_consent_by` on the meeting; until then no part is stored (audio with `keep` is
  simply not saved, the words still are; video gets 422 `MEETING_MEDIA_CONSENT_REQUIRED`). The recorder asks
  for it when "Save the recording" is ticked and falls back to words only if it cannot be recorded.
- **Playback permission**: `pi.meetings.recording` (owner, admin, manager; backfilled in 0059). Listing and
  playing parts need it, not just `pi.meetings.read`; each opening/listening is audited with ids only.
- **Known exception**: the transcript is redacted before it is stored, but saved audio/video is the original
  recording (it cannot be redacted). That is why saving needs its own yes and its own permission.
- **Retention**: default 90 days (`response_rules.brain.meeting_retention_days`, 30 to 3650). The date is
  recorded on every part; a purge step in the pi sweep (`pi_meetings/retention.py`) removes a meeting's recording (bucket objects, database audio, part rows) once every part is past its date; the transcript, findings and map stay. A bucket that cannot be reached is retried on the next sweep. Database audio is also capped per workspace (1 GB).
- **Delete / erase**: deleting a meeting removes bucket objects first (if the bucket cannot be reached nothing is
  deleted, 409 `RECORDING_DELETE_UNAVAILABLE`), then database audio, then rows. This runs for every meeting, even
  one whose `recording_key` is empty. Customer erase (`POST /pi/brain-erasure/{id}`) removes the customer's bucket
  objects first and refuses with the same 409 (nothing erased) if the bucket cannot be reached; database audio goes
  with its rows. Replacing a part under a different key removes the old object first or abandons the change.
- **Summary and requirements are saved as soon as the meeting ends**: Stop closes the transcript and runs the
  whole-meeting analysis (summary, problems, root causes, impact, requirements, decisions, actions, open
  questions), all stored as reviewable findings; nothing reaches the customer's memory before approval.
- **Requirement map**: the new Map tab arranges the findings in five lanes (what is wrong, what it costs, what
  is needed, decided and next, still open) and connects findings that come from the same part of the
  conversation (same source line or within two lines). It only arranges; the Problem Map in the customer's
  memory is still written by approving a finding on the Review tab.

### Not built yet (needs the owner)

- **Audio and video are saved only when the person chooses to** (see above). By default the audio is held in
  memory for the one speech-to-text call and dropped.
- A speech-to-text key must be configured for alias `stt` (OpenAI `whisper-1`, Groq or Gemini). Without one,
  a part answers 502 `MEETING_TRANSCRIBE_FAILED` and nothing is stored.
- Transcription runs inside the request (a part takes seconds). Moving it to an ARQ job (`meeting:<id>:<stage>`)
  is only needed once parts get long or numerous.

## PMB-4: meeting link (phases 1 and 2 built, the web pages not)

**Built (phase 1, migration 0060, flag `response_rules.brain.meeting_guests`, default off):** invite and guest tables, staff routes `POST/GET/DELETE /pi/meeting-intel/{id}/invite` and `DELETE .../guests/{id}`, public routes `GET/POST /public/meeting-join/{token}` (look, then join with consent; per-IP and per-token rate limits), hashed tokens, a link that closes with the meeting, expiry, revoke and a guest limit, erase and delete clean up. **Built (phase 2):** `POST /public/meeting-join/{guest_token}/parts` takes one minute of a guest's own microphone (webm/mp4/ogg, up to 2 MB), redacts and transcribes it and stores the words as that guest's lines; the audio is never kept. A guest token works only while the guest is not removed, the link is not revoked (an expired link only stops NEW people joining), the meeting is open and the flag is on, and it reads nothing. Line numbers: the host's four-minute part owns `[i*1000, i*1000+500)` and the guests who spoke in those four minutes share `[i*1000+500, i*1000+1000)`, six lines per (guest slot, minute), so sorting by number is sorting by time, a guest part replaces only itself, and the host's re-send (now limited to its own half) never removes guest lines. The host's analysis of a part reads the whole thousand, so guests are included. Revoking a link closes it even after it expired and stops its guests. **Not built:** the staff invite card and the public join page (mic recording in the browser).

One link per meeting; everyone who opens it records their own microphone into the same meeting, so the
transcript has a real speaker for each person.

**Flow.** Staff press "Invite" on a meeting (needs `pi.meetings.record`) and copy the link
`/join/<invite>`. A guest opens it (no sign-in), sees what is recorded and who sees it, gives a name
(optional: "Participant 2" otherwise) and ticks consent. Their browser records the mic and sends 60-second
parts; the page shows only "recording" and a stop button, never the transcript or other guests.

**Server.**
- `pi_meeting_invites` (hash of the invite token, expiry, revoked_at, max guests) and `pi_meeting_guests`
  (name redacted, hash of the guest token, consent_at, a speaker slot 1..20). Tokens are random, stored only
  as hashes, shown once. Migration 0060, additive.
- Public routes `/api/v1/public/meeting-join/...` take the token, never a session; they can only (a) join
  (b) send parts to THIS meeting, (c) leave. No read route exists for a guest. Per-IP and per-guest rate
  limits, part size and count caps, one active guest per token, invite closes when the meeting is closed
  or revoked, and a guest token dies with the meeting.
- A guest part reuses the staff pipeline (redaction, speech-to-text, `keep` is never offered to guests).
  Speaker = the guest's participant row (`role` stays `unknown` until staff map it). Segment order is by
  time: the part's ordinal slot is `(offset_minute * 20 + guest_slot)`, so parts from different people
  interleave by when they were spoken.
- Staff see who joined, can remove a guest (their lines stay unless deleted) and revoke the link.
- Customer erase and meeting delete also remove invites and guests.

**Web.** A public `/join/[token]` page outside the signed-in shell (its own layout, its own
Permissions-Policy `microphone=(self)`), and an "Invite" card on the meeting page.

**Risks to review before release.** A public write endpoint (abuse, cost of speech-to-text per part,
cross-tenant isolation, token leakage in logs and referrers), consent per participant, and what a guest
is told. Gate behind `response_rules.brain.meeting_guests` (off by default); `rule-auditor` on the diff.

**Order of work.** (1) migration, models, token helpers, invite and join routes with tests for isolation,
expiry, rate limits; (2) guest parts with time-ordered segments; (3) staff invite UI; (4) public join page;
(5) audit and a live two-person test.
