# Traceability matrix: pi-brain-v3, pi-industry-solutions, pi-platform-spec, pi-platform-spec-1

Stage 1, documentation only. Companion file: `trace-base-specs.csv` (854 rows, one per requirement). The v1.4-v1.6 specs are covered by `trace-v14-v16.*` (another agent), not here.

Code was checked on two trees: branch `pi/ps-flow` (worktree `.cache/lanes/flow`) and `origin/main` 954441c4 (worktree `.cache/lanes/s1matrix`). Cited code exists on both for every row, and no row differs between them (the extra ps-flow modules are isolated and not wired in).

## Counts per status per spec (all 854 rows)

| Spec | Rows | Implemented | Partial | Missing | Blocked | Unverified |
|---|---|---|---|---|---|---|
| pi-brain-v3 | 382 | 290 | 65 | 0 | 15 | 12 |
| pi-industry-solutions | 292 | 272 | 11 | 1 | 3 | 5 |
| pi-platform-spec (pp.1-140) | 83 | 49 | 25 | 0 | 1 | 8 |
| pi-platform-spec-1 (Book 5, pp.141-189) | 97 | 58 | 17 | 1 | 16 | 5 |
| **Total** | **854** | **669** | **118** | **2** | **35** | **30** |

Split by origin:

- 478 rows come from `rule_index.json`: 371 Implemented, 74 Partial, 1 Missing, 18 Blocked, 14 Unverified.
- 165 rows are new requirements not in the 478: 90 Implemented, 41 Partial, 1 Missing, 17 Blocked, 16 Unverified. Of these, 97 are Book 5 (platform-spec-1), 50 are Part A and Books 2-4 (platform-spec), and 18 are brain-v3.
- 211 rows are the industry entries of Addendum 2 Part 4: 208 Implemented, 3 Partial.

`pi-platform-spec-1` is `pi-platform-spec` plus Book 5. Its pp.1-140 are identical text, so rows for those pages sit under `pi-platform-spec`.

## Method and what "Implemented" means

- **Status rule.** Implemented requires the cited code to exist and a named test that asserts. Prompt-only is Partial. Anything I could not check is Unverified.
- **478 index rows, mechanical checks.**
  - Every cited file and symbol was checked on both trees (0 missing).
  - Every cited test exists and contains an assert (0 missing; 9 rows cite no test).
  - A static link was required between the test and the code symbol or rule id.
  - 14 DONE rows have no such link and are marked Unverified.
  - The 20 rubric rows RUB-1..20 are downgraded to Partial, because the only test checks that the grader lists the item.
  - 45 Implemented rows are flagged "thin test" because every cited test is 1-2 lines.
- **Semantic limit.**
  - I read the first cited test of only 10 random Implemented index rows.
  - 3 asserted the whole rule (Job S1, R-VOICE-06, VAL-1).
  - 7 asserted something narrower, such as a classifier or a constant (RT16, R-NOTE-08, P17, R-PRIV-06, R-ROUTE-01, RUB-3, RUB-18).
  - A full semantic pass over all 478 rows was not done. Treat Implemented as "named asserting test linked to the code", not "proved complete".
- **New rows.** Tests were found by importing the module and calling the symbol, ranked by name overlap with the behaviour. Where a test is named for the behaviour, the row is Implemented. Where tests only call the symbol, the row is Unverified.
- **Industry rows.** The 211 Part 4 entries were parsed from the PDF text and compared with `packs/solutions/*.json` on problem number, category, sub-type, and the presence of ideas, build, ask-first, free-stops, never-say and sample reply.
  - 208 match exactly.
  - 3 packs carry one extra problem versus the PDF: jewellery (a custom pre-orders problem), bakeries-mithai (the same), catering (a seasonal-dip problem).
  - The pack text itself was not compared word for word.
- **Source text.** The main checkout has no `docs/pi-saas/spec-text`. I used the identical copy in lane `a1`, an old extraction with private-use glyphs stripped. `pi-industry-solutions` p.50 has no extractable text.

## Sections not covered (explicit, not a complete audit)

- **brain-v3 pp.35-422 (Part 7):** the 211 industry playbooks. Only existence is tested (`test_every_industry_in_the_spec_is_loaded`); their text was not compared with the PDF.
- **brain-v3 Parts 0-6 and 8-11 prose:** covered through the index, plus a scan of 183 modal-verb sentences. I read the 75 with the lowest overlap against the index and added rows B3-*; the other 108 were not individually reviewed. Appendix A (prompt template), B (rule index) and C (glossary) were not traced. Part 11 playbook is process rows only.
- **industry-solutions:** pp.1-8 (contents) were not traced. Parts 1-3 (pp.9-25) are covered only by the 81 index rows. In Part 4 only structure was compared, not the wording of ideas and builds. Page 50 is unreadable.
- **pi-platform-spec Book 1 (pp.11-90):** mapped by id only. All 164 ids resolve to the index except R-SOL-10 and R-OFFER-07, which I added. Prose differences from brain-v3 were not diffed.
- **pi-platform-spec Books 2-4:**
  - Book 2 Part 4.6 worked examples and Part 8 retail playbook are not traced.
  - Book 2 Part 7 library content and Part 12 website copy are traced as single rows.
  - Book 3 (pp.116-131) is covered only through the addendum-2 index rows, not re-diffed.
  - Book 4 Parts 1-4 (root-cause narrative) and Part 7 ("check it yourself") are not traced beyond one row.
- **platform-spec-1 Book 5:**
  - Part 9 question banks are one row (Partial; content not diffed).
  - Part 1.3, Part 8 worked chats, Part 10 prompt text and Part 13 recheck table are not traced line by line.
  - Part 15 decisions are 13 Blocked rows (D1-D13).

## Verification results worth knowing

- The index's own test (`test_pi_rule_index.py`) already guarantees that cited paths and tests exist. I re-verified this on ps-flow and main, with symbol-level checks.
- Book 5 is mostly built since the 2026-10-27 audit: dials, moves, hypothesis ledger, think plan and lint, map builder/render/share/edit, Solution Box (`can_offer`, lifecycle, document), idea filter G1-G8, retrieval by sub-type.
- Not built: the dashboard auto-account and login (client_account, device_trust, login_attempt, auth_code, send_login_link), map charts (Part 4.6), the dial_state, idea_log and question_log tables, and the 7-day idea check-back.
- S_ADVISE (Book 2) is retired in code (`flow.RETIRED`), consistent with Book 5 11.1.

## Superseded rows (27 flagged in the CSV, column superseded_by)

- R-SELL-01, R-SELL-02 and R-SELL-04 are replaced by Book 2 R-ANS/R-SOL and Book 5.
- R-OFFER-01, SPEC-3.7, P7 and P8 are replaced by the Book 2/4 offer, then the Book 5 Solution Box.
- R-ASK-02 is narrowed by the Book 2 4.4 question budget and Book 5 3.4.
- Book 2 rows R-SOL-01, PS-4.1-LADDER, PS-6.1-RANK, PS-4.4-BUDGET, PS-9.1-ADVISE and PS-9.3-PROGRESS are narrowed or retired by Book 3 RVAL ("exactly 2") and Book 5.
- B5-5.4-WORDING: v1.6 Part 18 removes the "you can say no" clause from offers.
- I only noticed supersession; other later rules were not exhaustively searched. See `trace-v14-v16`.

## Top 20 gaps, ranked by severity

1. **Dashboard login (B5-4.9, ST1-ST12, 10.12): not built and in conflict with decisions made elsewhere.** The spec sets password to the WhatsApp number and says pi tells it to the owner. The built customer portal uses a WhatsApp code plus Face ID, and the 2026-10-27 audit advised against the spec's design. Security-critical and undecided.
2. **R-OFFER-07 and R-SOL-10 are spec rules missing from `rule_index.json`, with no test.**
3. **Test strength.** 14 index rows have tests with no demonstrable link (R-PRIV-01, R-QUOTE-05, R-DEC-04, RT17, L7, 9.9, SL-3, SL-9, SPEC-3.5, P13, P-LANGS-8, A2-1.8-IDEA-LENGTH, -HOWTO, -NOTHING-TO-LEAD-TO). 45 rows rest on 1-2 line tests. The 20 RUB rows are not behaviour-tested. R-PRIV-01 and R-QUOTE-05 are constitutional.
4. **Ten PROMPT-ONLY rules** contradict "rules are enforced in code": R-PRIV-08, R-VOICE-11, R-ASK-04, R-ASK-05, R-CANT-01, R-CANT-02, X5, P3, P16, P20.
5. **Linter holes on safety-adjacent rules:** R-PROM-02/03 (decisions and forecasts phrased otherwise), R-SOL-09 (regulated advice in stored ideas is not rejected), R-ANS-02, R-ECHO-01/02, R-ASK-03, R-MEM-02.
6. **Solution catalogue unconfirmed (A2-2.5-2, PS-7.2).** Addendum 1 Part 7.2 is not in the repo, and the catalogue was derived from the phrase bank. This drives every "Workzap can build X" claim (R-SOL-07, R-BUILD).
7. **Stored solution packs still carry tool-word and "automatically" lines** (audit F1: 356 and 492 strings). Only the runtime guard stops them (Part A.7, B5-14).
8. **Learning release gate is weaker than specified:** Job 9 (the gate is a script, not run per change, and replay grades stored replies rather than re-running them), L14, 8.8 (no named-entity pass), Job 8, Job 5.
9. **Book 5 evaluation not run:** the 633-row replay (B5-12.4, C1-C12), MT1 extraction accuracy (no 200-conversation corpus), and G31-G33/G38-G42 only partly tested.
10. **App.D open decisions (13).** D-4 retention and D-6 Meta templates block go-live; D-1 SLA, D-3 review exemptions and D-9 model naming change what pi may say.
11. **Part 15 decisions D1-D13 are unconfirmed**, including the Book 5 ideas cap (decision 5, flagged "pending Workzap approval" in the spec).
12. **Book 5 tables missing:** dial_state, idea_log and question_log, so there is no audit trail of dials or ideas. Model tools are in-process functions, not model-callable tools (B5-10.13).
13. **Map charts (B5-4.6-CHARTS): Missing.** No root-cause tree, timeline, exposure or priority chart.
14. **A2-FIX-5 (Missing):** bridge openers and build phrasings are not learned from owners' responses.
15. **Acceptance tests not individually present:** G16, G25-G27, G29, G30, G31-G33, RT31, RT33, RT36, RT39, RT40 and RT42 have no test named for them. They are covered only by behaviour-named tests (PS-G16, PS-G25-G30, PS-RT30-RT41).
16. **Solution ladder word caps (PS-4.1) and question budget (PS-4.4) are not enforced;** the spec's own Book 5 narrows them.
17. **Engagement metrics and dashboard panels partial** (B5-11.5, 8.11.1, 8.13): no lexicon explorer, questions-per-problem and similar gaps.
18. **Neighbours table, question banks and Roman Urdu review** (B5-9.20, 9.BANK, SPEC-2.5.1) lack a review process and a native-speaker QA owner.
19. **Part A is audit-once:** hypotheses 4, 7 and 8 and the live-path columns of the 211 table need production data (PS-A.2, -A.4, -A.6).
20. **Fidelity of data:** three packs deviate from the PDF (jewellery, bakeries, catering); the 211 brain-v3 playbooks and the Part 4 wording were not diffed; the 7-day check-back (PS-11.3) is not built, and tool-failure behaviour (B3-6.11) is only partly asserted.

## Owner-decision conflicts

- **Dashboard login:** Book 5 4.9 and Part 15 decision 2 (still unchanged in v1.6) against the CLAUDE.md rule "never ask for password or OTP", the built customer portal and the audit's F7 advice.
- **Ideas cap:** Book 5 decision 5 (2 per problem, 8 per business) against Book 3 VAL (4 per conversation) and A2-2.5-1 ("confirm the numbers"). The spec says pending. CLAUDE.md treats it as in force. Confirm.
- **Offer shape and wording:** the Brain v3 "no solution before S5" and the Book 2/4 offer line ("Mana bhi kar sakte hain") against the Book 5 Solution Box and v1.6 Part 18, which removes "you can say no". Check `d7-offer-wording-x1-x2.md`.
- **Solution catalogue** (A2-2.5-2): Addendum 1 Part 7.2 must be confirmed by Workzap.
- **Brain v3 "pi is not a solver" (B3-0.3, P7, P8)** against Solution Mode and Book 5 Part 7.
- **App.D-1 to D-13 and Part 15 D1-D13:** all unresolved. D-7 (shared workspaces) and D-9 (naming the model) also affect existing behaviour.
