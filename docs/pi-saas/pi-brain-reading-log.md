# pi-brain-v3.pdf: what has been read, by whom, and what is built from it

Honest record, updated as the work goes. "Read by me" means I read the page text myself. "Script"
means a program parsed it. "Audit" means a separate agent compared it with the code and reported.
The PDF has 448 pages; per-page text is extracted with `pypdf`.

| Pages | Part | Read by me | Script | Audit | Built from it |
|---|---|---|---|---|---|
| 10-11 | 0 What pi is | **yes, in full (2026-10-23)** | handbook | yes | prompt (`spec_handbook.py`), Workzap facts |
| 12-13 | 1 Constitution | **yes, in full (2026-10-23)** | handbook | yes | `constitution.py`, linter, gates |
| 14-18 | 2 Voice and languages | **yes, in full (2026-10-23)** | handbook | yes | linter voice rules, `style.py`, `language.py` |
| 19-22 | 3 Conversation engine | **yes, in full (2026-10-23)** | handbook | yes | `flow.py`, `decisions.py`, `followup_policy.py` |
| 23-26 | 4 Problem model, taxonomy | **yes, in full (2026-10-23)** | taxonomy (code) | yes | `problems.py`, `taxonomy.py` |
| 27-29 | 5 Documents, quote, payment | **yes, in full (2026-10-23)** | handbook | yes | `brain_docs*.py`, `brain_payments.py` |
| 30-34 | 6 Safety, edge cases | **yes, in full (2026-10-23)** | handbook | yes | `safety.py`, `safety_guard.py`, `brain_followups.py` |
| 35-36, 418-422 | 7.0 and 7.N to 7.Q (overlays, unlisted industry, angles, size) | **yes, in full (2026-10-23)**; now in pi's prompt |
| 37-417 | 7 Industry playbooks (211) | **no, not page by page by me**; 8 audit agents read the pages against the packs (2026-10-23) | `build_industry_packs.py` | content faithful; parser faults found and fixed (Arabic glosses, line-break hyphens, 6 wrong problem subtypes); 25+ spot checks, 20 detection probes | 211 packs + 11 overlays |
| 423-429 | 8 Self-learning brain | **yes, in full (2026-10-23)** | - | yes | `learning*.py`, `experience_*.py`, `learning_drift.py`, `learning_miner.py`, `critique.py`, never-say, review queue, metrics |
| 430-433 | 9 Implementation plan | partly (tool table, 9.2) | - | yes | `brain_config.py`, routes |
| 434-438 | 10 Golden, red-team, rubric | 434-435 yes | handbook (10.1) | yes | `tests/integration/test_pi_golden.py` |
| 439-445 | 11 Command playbook | yes (441-445) | - | yes | `.claude/commands`, `.claude/agents` |
| 446-448 | Appendices A-D | yes | - | yes | prompt assembly (spec guidance, emergency numbers) |

## Parts 0 to 2 (pages 10-18), what was built from reading them

Public promises P1-P26, the constitution, voice rules, languages: the specification text is in pi's
prompt every turn (`spec_handbook.py`). In code: the linter (disclosure, one question, 60 words,
no hype, one exclamation per conversation and only for a festival greeting, canonical phrases not
repeated, banned phrases, "the team reads this chat"), R-LANG-08 salam and Eid replies, R-LANG-07
voice-note line, R-LANG-04 `amount_value` (lakh, crore, hazar), R-LANG-06 `date_estimate` (kal,
parson, seasons), R-MEM-05 "what do you keep", R-FUP-02 one confirmation after "stop".
Not code, and yours: the native-speaker review of 2.5.1 (30 chats per language, two reviewers).

## Still to do from the audits (not built yet)

Built after reading Part 8: critique step (switch `brain.critique`, off by default), drift monitor
(weekly, freezes learning), question-wording miner, "Never say this", the weekly review queue
(`/pi/brain-learning/queue`), more 8.13 metrics, handback line, refund, bank-details, discount,
payment-method and wrong-number answers, video notice.

Built after re-reading Part 8 (2026-10-23): settings tuning (job 7, `learning_tuning.py`, timing
settings only, one step a week), the grader model (job 1, `learning_grader.py`, switch
`brain.grader`, off by default), the 5x weight of a staff correction and the staff route
`POST /pi/brain-learning/problems/{id}/correct`.

Built after that (same day): voice variants (job 6, `learning_voice.py`, moments "acknowledge" and
"correct", English seeds, canonical wording is the baseline, retired after two weeks worse, no
fallback to another language), learning from document edits and win/loss notes on quotes
(`learning_docs.py`, always HIGH, for the drafter only, never the chat), link confirm/reject and
the per-industry link threshold (`learning_links.py`, `/links`, `/links/{id}/decide`), the problem
board picture, the tap-to-correct list and the progress card (`brain_visuals.py`,
`brain_visual_queue.py`, `brain_visual_routes.py`; English and Roman Urdu only, drawn with a Latin
font), and a Problems tab on the Brain screen (correct a title or area, confirm or reject links).

Still not built: Roman Urdu seed phrasings for voice variants (written by a native speaker, then
added), pictures in Arabic or Urdu script (needs a font and text shaping), Urdu script as its own
language code, kickoff slot list, sticker and reaction handling, edited/deleted messages,
long-message split, pattern surfacing and team links, S3 to S2 and the clarify counter. Not
verified against real WhatsApp: the list message and the picture link are tested with a fake
provider only. None of this changes the constitution, and learning stays frozen until it is
switched on per workspace.

## Part 7 coverage check (2026-10-23)

Every industry and overlay section of the PDF was compared word by word with its pack file (all 222).
Real content words in the PDF that are in no field of the pack: 20, in 14 packs (before the fixes:
about 190 in 110 packs). What is still missing is a few English glosses of Arabic terms whose
glyphs the PDF stores unreadably (for example the meaning of `azeema`). The pack builder now keeps
local-word glosses (`signal_glosses`, 372 in 159 packs), quoted signals with their following words
(`L plate`), and treats a lost ")" as a list separator. What pi receives per turn: up to 5,200
characters for the primary industry (all care rules, seasons, 14 words, 14 problem phrases,
questions, scope, local words, one voice example) and 2,000 for each secondary one.
Still true: nobody read pages 37-417 page by page; the comparison above is by words, not meaning.
