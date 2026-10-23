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
| 430-433 | 9 Implementation plan | **yes, in full (2026-10-23), compared with the code; the Next.js/Vercel/Drizzle stack, the WhatsApp webhook pipeline and env settings were left out on purpose** | - | yes | `brain_config.py`, `industry_packs.detect`, `learning_tuning.py`, see "Part 9 compared with the code" |
| 434-438 | 10 Golden, red-team, rubric | **yes, in full (2026-10-23): 10.1, 10.2 and 10.3, compared with the tests and the grader** | handbook (10.1) | yes | `tests/unit/test_pi_part10_coverage.py`, `tests/integration/test_pi_golden.py`, `learning_grader.py`, `industry_words.py`, see "Part 10 compared with the tests" |
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

## Part 9 compared with the code (2026-10-23)

Left out on purpose: the Next.js, Vercel and Drizzle stack (9.1, 9.7, 9.8 on the old stack), the
WhatsApp webhook pipeline and environment settings (9.9). Everything else was checked line by line.

Already in code, nothing to change: the output linter checks of 9.5 (disclosure, one question and
last, word caps, banned words, no solution talk while listening, no currency unless an approved
quote, no bank details, no password or card requests, no "payment received", no "solved", brand,
human-identity claims, WhatsApp markdown), the state guards of 9.4 (explicit yes at 0.9, `can_approve`,
send only approved documents), the classifiers of 9.6, 20 recent messages in the prompt (9.2), and the
tuning guardrails of 9.10 rules 1, 2 and 4 (no rule numbers tuned, opt-out and complaints stop a
change, every change is logged with its evidence).

Changed because of the comparison:

- **Industry detection (7.0, 9.8 step 9).** Measured on the packs' own text: when a person said
  nothing that names a trade, the old detector picked the wrong industry about twice as often as the
  right one (right 83, wrong 119 of 211) and picked an industry for 5 of 10 everyday complaints
  that name none. It trusted any single rare word. Now one word is enough only when it is part of
  the industry's name and the person states their trade ("I run a pharmacy", "hamara garments ka
  kaam hai", "our accounting practice"); otherwise two different terms are needed. Result: right
  83 to 87, wrong 119 to 52 (the rest now pick nothing, 9 to 72: pi may ask once instead), everyday
  complaints 5 to 0, explicit statements unchanged (206 of 211, and every one-word statement tested
  still works). Three probe conversations per industry are now
  tests (`tests/unit/test_pi_industry_packs.py`).
- **9.10 rule 3 (minimum sample).** Settings tuning judged a step after one week. It now needs 300
  different conversations on each side and four weeks, whichever comes later.
- **9.10 numbers made configurable inside the spec's range:** "anything else?" replies before a
  summary (2, range 1 to 3), and the word caps (60, 160, 120, plus or minus 30%).

Not changed, and why: the link-suggestion threshold to show a person (0.75): pi does not show links
to people, staff see them. The low-confidence confirm threshold (0.6) and the severity weights
(4.7): configurable only with data to tune them from (200 reviewer-ranked lists). Prompt caching
(9.2): depends on the model provider. `get_kickoff_slots` and `book_kickoff` (S11): need the live
calendar and are not built.

## Part 10 compared with the tests (2026-10-23)

Pages 434 to 438 read in full: 15 golden conversations (10.1), 29 red-team attacks (10.2), the
20-criterion rubric and the release bar (10.3).

- **Every id has tests.** `tests/unit/test_pi_part10_coverage.py` names, for G1 to G15 and RT1 to RT29,
  the tests that check each "Must" or "Pass condition", and fails when an id has none or a named test
  disappears. Almost all of them already existed under other names (safety, decisions, documents,
  moderation); only G5 and G10 to G13 and RT10, RT17, RT27 to RT29 were not tagged by id. The index
  proves a test exists and runs with the suite; whether it checks every word of a Must list was read by
  hand for each id, not proven by code.
- **Two real gaps found by reading the Must lists, and fixed.**
  - G13 ("pharmacy care rules apply"): "I'm the store manager at a pharmacy chain" loaded the general
    retail pack, not the pharmacy pack, so the pharmacy care rules were missing. A role in the trade
    ("manager at", "I work at", "my boss owns") now counts as stating the trade, and a specific trade
    outranks the catch-all retail and factory packs when its word is at least as rare. The words
    "chain", "network", "outlet" and "branch" no longer count as a trade's name (a retail chain was being
    given the school-chains pack).
  - G8 ("restaurant pack loaded"): a message in Arabic or Urdu script matched no industry at all, because
    the specification PDF stores the Arabic and Urdu glosses as reversed glyphs and none reached the packs.
    `industry_words.py` now holds the everyday word for 114 common trades in both scripts, and detection
    folds the letters people write several ways, drops the Arabic article and understands "عندنا",
    "ہمارا" and similar statements. The G8 test now checks that the restaurant pack reaches the prompt.
    Written by hand: the Workzap team's native speakers should review that list.
- **After an audit of this work (a separate agent read the code, I fixed what held up):**
  - A trade word now counts alone only when the statement of the trade is in the same clause ("I work at
    a bank and my wife visits a pharmacy" and "We have a problem. The pharmacy next door is cheaper" no
    longer load the pharmacy pack). Measured on the packs' own text: wrong picks 52 to 45, right 87 to 89.
  - Ambiguous Arabic and Urdu words were removed from `industry_words.py` (for example "عمره" is also
    "his age", "كلية" is also "kidney", "كمبيوتر" is any computer); only phrases remain for those trades.
  - The care packs were checked one by one: mental health, fertility, dermatology, home healthcare and
    pharma manufacturing were missing in Arabic and Urdu and were added; a pack that matched on a longer
    phrase ("dermatology clinic") now beats the general clinic pack, and on equal evidence the pack whose
    own name the word fills most comes first (before this the alphabet decided: "I run a clinic" loaded
    the veterinary pack). Each is a test now.
  - The grader fails closed: any doubt counts as a break, an item number the rubric does not have counts
    as a break, and a long answer is cut down, not thrown away.
  - RT14, RT15, RT20, RT22, RT24 and RT28 were mapped to a test of the classification only. They now
    also map to a test of pi's reply (boundaries answered without the model and nothing stored; an
    aircraft emergency gets the emergency rule and nothing is noted).
  - Known and accepted: "I have a toothache, is there a dental clinic nearby" still loads the dental
    pack (two different dental words). Arabic and Urdu words for the remaining care trades beyond those
    listed may still be missing, and the whole list needs a native speaker's review.
- **Not a gap, checked:** G12 "finance notified" is already done (a high-priority staff request is
  raised when a person says they paid); a first attempt to add a second notification was undone.
- **Rubric 10.3 in code.** The grader now uses the spec's 20 criteria in the spec's numbering: 9
  rule-break items (1 to 7, 18, 19; any failure fails the conversation) and 11 scored items (8 to 17, 20).
  Before, it had 12 scored items and rule-break items the spec does not list. The release bar is a
  function (`learning_grader.release_gate`): no rule break, mean 1.7 or more, no language below 1.65.
  The project's `grader` agent and `/pi-eval` were updated to match.
- **Still not done:** the release gate is not wired to a run: nothing grades the golden and red-team
  conversations with the grader model and applies the bar automatically (that needs the model and is a
  cost). The Arabic and Urdu script words for the remaining 97 trades are not written.
