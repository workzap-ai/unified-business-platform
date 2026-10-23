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
| 23-26 | 4 Problem model, taxonomy | earlier sessions | taxonomy (code) | yes | `problems.py`, `taxonomy.py` |
| 27-29 | 5 Documents, quote, payment | earlier sessions | handbook | yes | `brain_docs*.py`, `brain_payments.py` |
| 30-34 | 6 Safety, edge cases | **yes, in full (2026-10-23)** | handbook | yes | `safety.py`, `safety_guard.py`, `brain_followups.py` |
| 35-36, 418-422 | 7.0 and 7.N to 7.Q (overlays, unlisted industry, angles, size) | **yes, in full (2026-10-23)**; now in pi's prompt |
| 37-417 | 7 Industry playbooks (211) | **no, not page by page** | `build_industry_packs.py` | 25+ spot checks, 20 detection probes | 211 packs + 11 overlays |
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

Still not built: weekly settings tuning (job 7), grader model (job 1 rubric), voice variants (job 6),
the problem-board image / interactive list / progress card (8.11.2), Urdu script as its own language
code, kickoff slot list, sticker and reaction handling, edited/deleted messages, long-message split,
extra problem-record fields, pattern surfacing and team links, S3 to S2 and the clarify counter,
5x staff-correction weight, learning from document diffs, link-threshold tuning.
