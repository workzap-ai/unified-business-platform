# Audit of the existing pi against pi-platform-spec-1.pdf (Part A)

Date: 2026-10-27. Read-only: no code, pack, prompt or database was changed. Method: the spec text was
extracted with `pypdf` (189 pages) and read in full for Part A, Book 1 Parts 0-1, Book 5 Parts 1-7, 11, 13-15.
Every finding below names a file and line. Items marked CANNOT CHECK need production data (see the last section).

## Summary (five lines)

1. The spec's central worry (new packs overruled by an old prompt) is **mostly not true here**: the reply path has one
   assembly (`service_conversation.py:4876`), the rewrite call reuses it (`:5042`), and packs, overlay and library are all read.
2. What **is** true: the stored solution packs still carry the tool-word and "automatically" lines (hypothesis 9 FOUND), and old
   English "Noted" / "anything else getting in the way" fallbacks still exist (Part 14 removal list FOUND).
3. Book 5's new engine is **mostly missing**: no dials, no 16 moves, no hypothesis ledger, no goal verb, no map versions, no
   Solution Box. A problem map and a customer dashboard exist but are a different design (see F6, F7).
4. The dashboard login in Book 5 (username + WhatsApp number as password) **conflicts with what is already built and with
   safety** (F7). I recommend not doing it as written. This needs your decision.
5. Confidence: high on code findings (quoted), none yet on live-chat behaviour (not read; see "Cannot check").

## Hypotheses table (A.2)

| # | Hypothesis | Verdict | Evidence |
|---|---|---|---|
| 1 | Old "listen first" rule later in prompt than Solution Mode | NOT FOUND in prompt text (grep for "do not suggest / never suggest / only listen / listen first" in `service_conversation.py`, `brain_prompt.py`, `flow.py` matched only comments). The listening gate is code (`flow.py:44`) and is superseded by `spec/supersession.json` | grep, `flow.py:44` |
| 2 | Two prompts active at once | NOT FOUND for replies: `system_for(context)` once at `service_conversation.py:4876`, same text reused at `:5042`. Other model calls are separate purposes (docs, critique, learning, proposal writer, website KB) | `grep complete_structured` (16 sites) |
| 3 | Packs stored, never retrieved | NOT FOUND: 211 solution files + 211 industry packs are read by `industry_packs.py`, `solution_ideas.py`, `solution_library.py`. Retrieval quality is another matter (F2) | `packs/solutions` = 211 files |
| 4 | Retrieved but cut off | CANNOT TELL without a real final prompt | needs production capture |
| 5 | Industry never identified | PARTLY: routing probe of 5,908 phrasings: 94% right with the model's category, 39% from words alone (`tests/unit/test_pi_cross_industry_routing.py`) | existing ratchet test |
| 6 | Old guard blocks solutions | NOT FOUND as a blocker; `asks_for_document` (G28) and the ask gate answer first. But S_ADVISE (added earlier) is entered by nothing | `flow.py:22` |
| 7 | Learned data teaches old behaviour | CANNOT TELL: production learning tables were runs 7, lessons 0, learned packs 0, feedback 0 on 2026-10-26, so little to poison | earlier read-only check |
| 8 | Stale prompt/cache/deploy | CANNOT TELL; a per-reply stamp exists (`learning_audit.py:38` `prompt_version()`, `:61` `pack_versions()`), deploys are Railway auto from main | |
| 9 | Stored solution pack carries tool words / "automatically" | **FOUND** (F1) | counts below |
| 10 | Model/settings mismatch | FOUND and fixed earlier: Claude refused `temperature`; fallback chain order set by you in the database | commits b03fbd8, f7029a3 |

## Findings

**F1. Stored solution pack defects (A.3 step 8).** Counted with a regex over every string in `packs/solutions/*.json`
(211 files, 28,253 strings): 356 strings contain a banned tool word (dashboard, system, software, platform, ERP, module,
automation, integration, CRM, portal, analytics, app) in 124 of 211 files; 492 strings contain "automatic / khud-ba-khud" in
168 of 211 files. Worst file: `cloud_kitchens_and_virtual_brands.json` (19). Overlay: 0 of 86 strings. Library: 10 of 401.
The spec found 413 and 210 of 211; my counts differ (different regex, and strings are counted, not lines), so **the stored pack is not
identical to the one the spec describes**, which the spec calls a finding in itself. A runtime guard exists
(`solutions.banned_tool_words` used at `constitution.py:1094` and `solution_rules.py:289`), so these lines are mostly caught
before sending, but they remain in the data and can still be copied by the model.

**F2. 211-row table (A.4), partial.** `pack_stored` 211/211 industry (`packs/industry` holds 222 files: 11 extras are not industries and
should be listed), `solution_stored` 211/211. `retrieved_on_probe` and `final_prompt_contains` need the live path: CANNOT CHECK yet.
`tool_word_lines` and `ending_repeat` per industry can be produced from the same counting script (kept in the scratchpad). I will
output the full 211-row CSV in step 4.

**F3. Offer lives in more than one place.** Fixed offer text: `decisions.py:203-208`, `decisions.py:240-241`, `fixed_lines.py:39-40`,
`golden_replies.py:12`. Offers are gated by decisions (R-OFFER-01/03/04), per set of problems, not appended to every reply
(good), but they are **not yet gated by Book 5's B1-B7 / R1-R3 rule**, and the offer wording says "solution document and quote",
not "Solution Box".

**F4. Part 14 removal list: found.**
- English "Noted" openers / "anything else getting in the way": `language.py:350`, `:355`, `:366`; `constitution.py:2081-2082`
  (`"Noted. What else is getting in the way?"`).
- Roman Urdu text that starts with English "Noted.": `language.py:351`, `:367`.
- Fixed fallback notices exist for **three languages only** (en, roman_ur, ar) in `language.py` (0 entries for ur, hi, fr, fa, es),
  so a French or Hindi chat gets an English or Roman Urdu line (spec class C6).
- `RSELL01/02/04`: already superseded in `spec/supersession.json`.
- "End the reply with the offer": not found as a default ending.

**F5. Prompt/version stamp exists.** `learning_audit.py:38,61,117-118` records prompt and pack versions with each reply
(`learning_models.py:166-167`). Good; A.8 point 4 is already met. Daily drift run (A.7 last bullet): not found.

**F6. Book 5 engine vs what exists.**

| Book 5 item | Present? | Note |
|---|---|---|
| 4 live dials, 16 moves, move log, hypothesis ledger, thinking step | No (0 matches for openness / trust_trend / hypothesis) | new build |
| Goal verb and retrieval by (industry, sub-type, goal verb, cause) | No (0 matches for goal_verb) | `taxonomy.py` lacks overstock/ageing and clearance sub-types (decision 7) |
| Idea filter G1-G8 | Partly: `check_idea`, `is_owner_action`, relevance gate (false-serve 12%), but no goal check (G1) and no map check (G8) | extend |
| Problem Map data: nodes + typed links + version | Partly: `pi_problems`, `pi_problem_links` (`problem_models.py`) | links use types `same_root_suspected, causes, same_area, duplicate_across_contacts, blocks` and status `suggested/confirmed/rejected` (`taxonomy.py:101-104`), the spec wants `causes, worsens, competes, same_root, blocks, symptom_of` and `owner_said/pi_inferred/confirmed`; no `map_version` table |
| Map as image on WhatsApp | Partly: `brain_visuals.py` draws a board and progress card; **Latin font only, so Urdu/Arabic get text only** (docstring) | spec needs Noto Naskh and RTL |
| Solution Box (living, versioned, one per business) | No: documents are per set of chosen problems (`brain_docs_models.py`) | new `solution_box` and states |
| canOffer, noMoney, mapSupport, mapNumbers guards | Partly (noMoney exists as price policy) | new guards |
| Removing S_ADVISE (Book 5 11.1) | **Conflict**: I added `S_ADVISE` earlier; Book 5 removes it and replaces it with S_LISTEN_THINK, S_MAP_SHARE, S_BOX_OFFER, S_BOX_DRAFT, S_RETURN, S_HOLD | resolve in step 3 |

**F7. Dashboard login: the spec's design vs what is built.** Already live: the `/customer` portal (`pi_customer/`): WhatsApp code, then
camera Face ID or optional fingerprint (`second_step.py`), signed cookie, lockout (`_lock`, `_failed`), never passwordless.
Book 5 asks for: username from the name, **password = the owner's WhatsApp number**, plus a one-time code on a new device.
Risks: (a) a phone number is public, so the number alone is a weak first factor (the spec admits this and adds the new-device code);
(b) it would be a second, weaker login beside the one that exists; (c) pi creating accounts and announcing a username in chat is fine,
but the password must never be echoed. **Recommendation:** keep the existing portal and its two-step sign-in, show the Problem Map and
Solution Box inside it, and give the owner a one-tap signed link from WhatsApp. Do not build a number-as-password login unless you
choose to after reading this. (Decision 2 in Book 5 asks for your approval of exactly this.)

**F8. Conflict Register (A.5), initial.**

| Id | Old | New | Wins today | Proposed |
|---|---|---|---|---|
| C01 | Brain v3 RSELL01/02/04 (no solution while listening) | Book 2 RANS/RSOL answer first | New (supersession.json + G28) | Already resolved; delete the dead text from `constitution.py` comments and `spec_handbook` |
| C02 | `value_line.py:13` four ideas per conversation | Book 5 decision 5: 2 per problem, up to 8 per business | Old (4) | Change to 8 only after you approve decision 5 |
| C03 | `decisions.py` offer per set when yes gate allows | Book 5 B1-B7 / R1-R3 | Old | Replace by `can_offer` |
| C04 | Per-problem Depth Meter as an offer trigger / "set board" | Map and Box | Old | Remove per Part 14 |
| C05 | CLAUDE.md non-negotiable "no solution before S5 and explicit yes" | Book 2/5: answer on request in the first sentence | Code follows Book 2 | Update CLAUDE.md after approval (you said the specification wins; this is a newer specification) |
| C06 | Fixed English fallback lines | Language lock | Old | Translate into the eight priority languages or build in the model's own language |

## What could not be checked, and why

- Real message logs and final prompts of the two (now three) live chats; industry identification on every recorded chat; the last 50
  replies' versions; whether production runs the code I read. These need a **read-only** query against the production database
  (the same way as earlier checks: `default_transaction_read_only = on`). I did not do it without your yes.
- Retrieval on 3 probes per industry through the live path (needs the disposable database + real model; the real model costs money,
  so I will ask first and use the cheap 30-sample).
- Whether the existing `apps/pi` problem-map page is what clients see or only the team (the file header says "the team's Problem Map").

## Proposed fix list (ordered, each tied to a finding; nothing is applied until you approve)

1. F1: rewrite the 356 tool-word strings and 492 "automatically" strings in place with versioning and a rollback copy (A.7 bullet 2).
2. F4/C06: remove the English "Noted…" fallbacks and make every fixed line available in the eight priority languages.
3. F3/C03/C04: `can_offer` (B1-B7, R1-R3), one offer per set, "Solution Box" wording; remove the old triggers (Part 14).
4. F6: build, in order: goal verb and the two new sub-types, thinking step with dials and moves, hypothesis ledger, map versions with
   the spec's link types, deterministic layout and RTL-capable image, Solution Box states.
5. F7: put the map and box into the existing portal; one-tap link; no number-as-password.
6. C02/C05: change the ideas cap and CLAUDE.md only after your decisions 5 and 2.
7. Daily drift run of A.3 steps 2, 4, 8, and the four upload checks (A.8).
8. Step 4 of the spec: unit tests, red-team, then the 211-industry replay with three postures (633 runs, mostly scripted, one cheap real-model sample).

## Production read-only check (2026-10-27, counts only, no message text or numbers read)

Run through `railway run --service pi-worker` with `SET default_transaction_read_only = on`. Database is at `0046_pi_business`.

| Check | Result |
|---|---|
| Conversations by state | S1 10, S2 7, none 3, S3 2, S4 1, X_HUMAN 1, S5 1 (25 total) |
| A.2-5 industry identified (customers with 3+ inbound messages) | **empty for 11 of 18 (61%)**, set for 7. Across all customers 104 have no industry. Hypothesis 5: **FOUND** |
| A.9 / A.8-4 audit stamp on the last 50 AI replies | **only 13 of 50 carry a stamp** (one prompt version `3e542364ddef`, builds `5bb4295`, `ce6139e`, `5bee026`). 37 replies cannot be traced to a prompt/pack version. **FOUND** |
| Phrases in the last 284 AI replies | opener "Noted": 8; filler ("anything else getting in the way"): 4; tool-word regex hit: 29 (includes pi's own "Workzap makes software" identity line, so an upper bound); "automatically": 2; offer-ish ("solution document"/"quote"): 30 |
| A.216 conversations at the offer step with fewer than 3 problems | 1 of 1 (one problem known) |
| Replies per day | 24 Oct 139, 25 Oct 87, 26 Oct 30 |

Not done: the full replay of every recorded chat's first 3 messages and capture of the final prompt for each message (prompts are not stored,
by design only identifiers are, `pi_reply_audits`). A final-prompt capture needs the real model; I will do it on the disposable stack in step 4.

## Corrections and follow-up after the read-only check (2026-10-27)

- **F1 corrected.** The first count (356 strings) included metadata that pi never says: `tool_words`, `keys`, owner `words`, and `never_say`.
  Counting only the fields pi can speak (`workzap_build.text`, `free_stops`, `ask_first`, `quick_ideas*`, `extra_ideas`, `sample_reply`):
  **113 strings with a tool word in 56 files, and 492 strings with "automatic/khud-ba-khud" in 168 files** (490 of them in `workzap_build.text`).
  At run time a build is also re-phrased from `keys` through the phrase bank, so `workzap_build.text` is not always spoken as stored.
- **Audit stamp (A.8 point 4).** Stamps exist only from 26 Oct (`pi_reply_audits`: 13 rows, all on 26 Oct), because stamping runs in brain mode only
  (`learning_audit.py:10`). Before that no reply carries a version. Not a defect to fix now, but "every reply carries a version" is true only from 26 Oct.
- **Industry empty.** Workzap tenant: 14 customers without an industry, 8 with. Industry is stored only when `industry_packs` is on, which is recent, so
  older customers are empty by design. New chats since the switch are filled.
- **Fallback line fixed** in `constitution.py` (`FALLBACK_LISTENING`) and the "Noted…/anything else getting in the way" notices in `language.py`.

## The 211-row table (A.4), scripted, 2026-10-27

Full table: [pi-211-industry-check.csv](pi-211-industry-check.csv). Probes: three first messages per industry written from the pack's own
`signals` (English, Roman Urdu, mixed), run through `industry_packs.detect`. No model was used.

- pack stored 211 of 211; solution entry stored 211 of 211.
- Industry identified on at least 2 of 3 probes: **207 of 211** (pass mark: every industry). Gaps: `cold_chain_logistics`,
  `electricity_and_power_contractors`, `general_contractors`, `solar_epc_and_installers` (1 of 3 each: neighbouring trades share words).
- Tool-word lines in spoken fields after the rewrite: 7, all in `quick_ideas` and all about a tool the owner already has (an aggregator app, a
  portal, a platform payout); the run-time rule allows a tool word the owner used, so these are kept on purpose.
- "automatically" endings: 0 files.
- `final_prompt_contains` (does the block survive into the final prompt) needs the real prompt path: not part of this scripted run.
