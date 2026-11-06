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

### Not built yet (needs the owner)

- **The audio is not stored.** It is held in memory for the one speech-to-text call and dropped, so
  `recording_key` stays empty and a meeting can still be deleted. Storing it needs the S3 or R2 bucket and
  keys, and the retention decision (proposed 90 days for audio); the write goes in `upload_part`.
- A speech-to-text key must be configured for alias `stt` (OpenAI `whisper-1`, Groq or Gemini). Without one,
  a part answers 502 `MEETING_TRANSCRIBE_FAILED` and nothing is stored.
- Transcription runs inside the request (a part takes seconds). Moving it to an ARQ job (`meeting:<id>:<stage>`)
  is only needed once parts get long or numerous.
