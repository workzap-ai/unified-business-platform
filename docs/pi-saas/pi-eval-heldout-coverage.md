# Held-out set: coverage, gaps and results (2026-10-30)

Held-out grew from 21 to 60 cases (102 cases in all). The three kinds of statement are kept apart.

## 1. What was added (a fact about the data)

- 39 new cases, all new text for businesses written fresh. No message appears in two splits (checked:
  0 shared between Development and Held-out), and every case id is unique.
- The split rule is unchanged: Held-out is the stable hash of the case id (25% share) and Regression is
  every case tagged `regression`. To get 39 new Held-out cases the authoring script appended a number to an
  id until its hash fell in Held-out (`carwash_correction_en_3`, `dent_multi_en_5` ...). The number carries
  no meaning and was chosen without reading any result. The 63 earlier cases did not move.
- 38 of the 39 new cases use an industry that none of the first 63 cases used (so it is in neither
  Development nor Regression); the 39th reuses `unknown_business_owner`. Twelve industries of the first 63
  cases have cases in both Development and Held-out, because that set put three cases of each industry
  through the hash.
- Scorers, thresholds and the extraction code were not changed. One reference note was wrong (a 9-word
  title, the code allows 8); the note was fixed, not the rule.

## 2. Coverage of Held-out (60 cases, 106 expected problems)

| axis | count |
|---|---|
| language | English 25, Roman Urdu 23, Urdu script 8, Arabic 4 |
| kind | single 21, list 18, correction 8, constraints 4, mixed 3, multi-turn 3, rant 3 |
| cases with two or more problems | 26 |
| figures to keep (e.g. "12 of 45", "2,000 rupees", "15 baar") | 51 |
| corrections of a figure (e.g. "5 nahi 15", "not 15%, 25%") | 8 |
| constraints labelled (budget, staff, "cannot change X") | 4 cases, 9 constraints |
| owner-said cause / hypothesis-only cause labelled | 2 / 1 |
| industries | 52 |

## 3. Gaps (what the set cannot show)

1. **No Held-out cell reaches its minimum.** S4 wants 30 cases per language: Held-out has 25 English, 23 Roman
   Urdu, 8 Urdu script, 4 Arabic. S5 wants 15 per kind: only single and list reach it. Any single industry has
   at most 3 cases (S2 wants 10). So no language, kind or industry claim can be made from Held-out yet.
2. **Hindi is 0**, and Arabic has 4 cases in all. Arabic-Indic digits are not used anywhere (all figures are
   written with 0-9), so a message with digits like ٤ is untested.
3. **Constraints are labelled but not scored.** The scorer measures recall, precision, kept figures, applied
   corrections and unsupported causes. Nothing reads `expected.constraints`, because pi has no constraints
   field yet (B2 has not started). The labels are there so the scorer can use them when B2 exists.
   **Update (FT-A2, 2026-10-30):** a scorer now reads them. `constraints_kept` counts a labelled constraint as
   kept when its words and numbers survive in the record's `constraints` list or its own words; the four
   Held-out constraint cases gained a reference `constraints` list in their recorded notes (the only change to
   existing cases), and the reference result is 9 of 9 kept for Held-out. This still measures the scripted
   reference, not a model.
4. **Unsupported-cause coverage is thin**: one hypothesis-only case and two cases with a stated cause, so the
   0 unsupported causes in the table means little.
5. **Development is now smaller than Held-out** (39 against 60). Tuning data should not be the small side;
   Development needs to grow, with new text, before the next tuning round.
6. **Single-turn bias**: three Held-out multi-turn cases, none with a correction in a later turn that also
   changes a figure noted in an earlier turn.
7. **The reference notes were written by the same author as the cases.** That is why the results below are
   a check of the code and the scorers, never of a model.

## 4. Results (scripted replay: reference notes through the real extraction path, no model)

| split | cases | problem recall | precision | figures kept | corrections kept | unsupported causes |
|---|---|---|---|---|---|---|
| development | 39 | 100% | 100% | 100% | 100% | 0 |
| held_out | 60 | 100% | 100% | 100% | 100% | 0 |
| regression | 3 | 100% | 100% | 100% | 100% | 0 |

These numbers say the extraction path keeps what a correct note contains (caps, per-note checks, the
known-title filter) for Roman Urdu, Urdu script and Arabic text too. They say **nothing** about how often a
model produces such notes. Before the case was fixed, one Held-out case scored 0/1 because the reference
title was too long: an authoring error, shown here because the first run is the one that counts as a finding.
Full per-group tables: `pi-eval-baseline.md`.

## 5. What is needed to turn this into a real measurement

- Owner approval of S1-S7 and T1-T11 in `pi-eval-thresholds-proposal.md` (all still PENDING).
- A working OpenAI key and a budget for a real-model sample (30 cases first). Nothing has been spent.
- More Held-out cases per language (Urdu script, Arabic) and a Hindi set if Hindi is in scope.
- Who may read Held-out results, and how Held-out reads are logged (`evalkit.access_log.append`, the append-only writer; `splits.held_out_access` only builds a record).

## 6. Development set: coverage after FT-A1 (2026-10-30)

Development grew from 39 to 69 cases (132 cases in all: 69 Development, 60 Held-out, 3 Regression). Gap 5
above (Development smaller than Held-out) is closed by this. The Held-out facts in sections 1 to 5 are
unchanged: no Held-out case was added, changed or read for this work.

- 30 new cases, all new text for businesses written fresh; 30 industries that no earlier case used (49
  industries in Development in all). Each id was given a number suffix until its hash fell in Development
  (`oud_correction_ar_3`, `insure_rant_hi_6` ...); the number carries no meaning. No message of the new cases
  appears in any other split, and ids are unique. The one message Development shares with another split is the
  old pair of the `acc_correction_en` / `reg_correction_figure` conversation (Regression is a deliberate copy).
- The 102 earlier cases are byte-identical (the diff of `extraction.json` is additions only).
- Hindi (Devanagari) is data only: pi understands it but does not write it. The scorer splits words with the regex word class,
  which breaks Devanagari at its vowel signs, so the Hindi reference notes are matched through the English words
  of their titles (`any` keywords) and figures are kept by their number. That is a limit of the scorer, left as
  it is.

| axis | count |
|---|---|
| language | English 24, Roman Urdu 18, Urdu script 11, Arabic 8, Hindi 8 |
| kind | single 21, list 17, correction 9, rant 7, multi-turn 6, constraints 5, mixed 4 |
| expected problems / cases with two or more | 117 / 32 |
| figures to keep | 47 |
| corrections of a figure | 9 |
| constraints labelled | 5 cases, 14 constraints |
| industries | 49 |

Scripted result for Development (reference notes, no model): problem recall 100%, precision 100%, figures
kept 100%, corrections kept 100%, 0 unsupported causes. Every new reference note was checked to survive the
real extraction path (titles at most 8 words, owner words and a valid category present).

## 7. Development set: second FT-A1 round (2026-10-31)

Development grew from 69 to 98 cases (161 cases in all: 98 Development, 60 Held-out, 3 Regression). Target
of the round: Hindi 15, Arabic 15, Urdu script 20; result Hindi 16, Arabic 16, Urdu script 21, plus 3 Roman
Urdu cases. No Held-out case was added, changed, read or printed. The 132 earlier cases are byte-identical
(the diff of `extraction.json` is additions only, checked by comparing the parsed list with the one in git).

**Honest limits.** These 29 cases are **agent-drafted, unreviewed**: one author (an AI agent), no native
speaker or human reviewer has read them, and the reference notes were written by that same author. Each new
case says so in `recorded.origin`. A human reviewer must still check the wording, the labels and the
category of every case before any number from them is quoted outside the team (checklist below).

- 29 new cases, new text, 29 industries from the 211-industry list that no earlier case used (one case each), written as realistic owner messages: single problems, lists of 3 to
  6, rants, a voice-transcript style message without punctuation (Hindi and Urdu), corrections in each
  language ("10 nahi, 100" style), figures with local magnitude words (lakh, crore, hazar and their scripts),
  English words mixed into Hindi, Arabic and Urdu, constraint cases (budget, staff, "cannot change X"), one
  multi-turn case per script language, and one Arabic case that uses Arabic-Indic digits (٢٠ to ٢٠٠), which no case
  had before.
- Ids that hashed into Held-out got a number suffix (`genset_correction_hi_4`, `bus_single_ar_2` ...); the rule
  is unchanged and the number carries no meaning. All 29 are Development by `splits.split_of`.

| axis (Development, 98 cases) | count |
|---|---|
| language | English 24, Roman Urdu 21, Urdu script 21, Arabic 16, Hindi 16 |
| kind | single 26, list 24, correction 13, rant 11, multi-turn 9, constraints 8, mixed 7 |
| expected problems / cases with two or more | 182 / 49 |
| figures to keep / corrections of a figure | 71 / 13 |
| constraints labelled | 8 cases, 23 constraints |
| industries | 78 |

Scripted replay of the 29 new cases (reference notes through the real extraction path, no model, no
network, no database): n = Hindi 8, Arabic 8, Urdu script 10, Roman Urdu 3; problem recall 100%, precision
100%, figures kept 100%, corrections kept 100%, constraints kept 100% in each, 0 unsupported causes. **This is
a check of the code and the scorers, not of any extractor**: the replay returns the author's own notes, so a
language cannot fail it. Nothing in the extraction path is a non-model fallback (`problem_extract.extract`
returns [] when the model call fails), so there is no extractor to fail a language without a model; the weak
non-Latin extraction the plan expects can only be shown by the real-model sample (FT-REPLAY). The one
language-dependent code gate in the path was run on the new messages: `wants_extraction` (5 or more words)
is true for 29 of 29, and `thin_message` is true for 0 of 29.

What a human reviewer must check: (1) the wording reads as a native owner would write it, in particular the
Hindi spelling with nukta and the Arabic and Urdu mixed-language forms; (2) each `any` keyword and each
labelled figure matches what the owner really said; (3) the category of each note; (4) the constraint
strings are the owner's words; (5) that the cases with a cause (`juice_single_hi`, `fishmkt_single_ur`,
`aircon_correction_ru`) are labelled correctly as owner-said or hypothesis only; (6) that Devanagari
figures are only checked by their number because the scorer splits Devanagari at its vowel signs (unchanged).
