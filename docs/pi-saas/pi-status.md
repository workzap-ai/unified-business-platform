# pi status, one page

Dated 2026-10-26. Written from the code, the tests and the rule index at origin/main `5bee026`
(plus the docs commits that carry this page). It says what is checked and what is not. Where this
page and `pi-rule-coverage.md` differ, the coverage page is the one a test compares with the index.

## 1. Live

On origin/main, built and tested offline. I could not see what Railway has deployed, so "live" here
means "on origin/main", not "confirmed running in production".

- **Document and quote ask.** Asking for the solution document or quote is the yes from any
  listening step once a problem is noted. pi confirms without a question. A bare "yes" with two or
  more problem groups still asks "all or some" once.
- **Solution mode.** Ideas on an ask (two, as plain sentences, owner actions), the owner-approved
  generic library when no industry entry has an idea, one question at most before ideas, an apology
  first for an impatient owner, a churn signal logged and answered with ideas.
- **Linter rules.** Answer first, no echo and no restating, no verdict openers, no "please be
  patient", closed questions never asked again, requests left open are answered first, never reveal
  Workzap's internal methods, neutral and polite Roman Urdu (R-GEN-01, R-TONE-04, R-SPELL-01). These
  now also run in Urdu script, Arabic, Hindi, French, Spanish and Persian.
- **One prompt per reply type.** Brain mode has its own system prompt without the account-manager
  sales flow. Other workspaces keep the same prompt. Every brain reply is stamped with the prompt
  version, pack versions and build id.
- **Follow-ups.** A reminder never carries new ideas, and a message pi starts itself is not sent
  twice to the same person within 24 hours. Replies are never held back.
- **Data.** 211 industry packs and 211 solution entries, every problem with an opening question, no
  tool word in a Workzap build sentence, sample replies rewritten (a distinct opener per sector).
  One owner-added fashion entry ("price asked in DM, then silence") that is not from the PDF.

## 2. Held

- **Pushes** to origin/main were held by the API testing session during the owner's live test.
  Railway deploys each push and a pi-worker deploy cancels chats in flight.
- **Real-model checks.** The last valid replay was on `02662d7` (8 industries: 7 right, 0 errors).
  Every later replay is invalid because the OpenAI key was revoked (HTTP 401). The effect of the
  prompt split, `b33ef19` (ideas close with the offer) and later changes is checked by unit and
  integration tests only.
- **Owner decisions.** R-OFFER-07 and R-SOL-10 are excluded by the owner. The solution catalogue
  stays a draft. G4 (the `supersession.json` open question) is waiting for the owner. The generic
  library and the fashion entry are recorded as owner-approved deviations from the spec text in
  `packs/library/owner_rewrites.json`; I read that record, I did not confirm the approval.
- **Should pi ask "what kind of business is it?"** once its industry guess is shaky, before a second
  problem is noted? Not decided. It would change the flow. Detection is better without it but not
  solved (see the open list).

## 3. Numbers

| Check | Result | Where it comes from |
|---|---|---|
| Unit tests | 4725 passed, 2 deselected (old scheduler tests that fail on settings) | run 2026-10-26 on this tree |
| `ruff`, `mypy` | clean (420 source files) | run 2026-10-26 |
| Rule index | 478 rules: DONE 406, PARTIAL 43, PROMPT-ONLY 10, HUMAN 18, MISSING 1 | `pi-rule-coverage.md` |
| Offline audit, 211 industries | packs and solutions stored 211 of 211; present in the prompt block whenever retrieved; 205 of 211 picked on at least 2 of 3 probe messages | `scripts/pi_audit_report.py` |
| Integration suite on the test DB | 627 passed, 1 skipped, 2 failed (one known flake, one real, see section 5) | run 2026-10-26 |

Industries still picked on fewer than 2 of 3 probes: catering_and_event_food,
packaged_food_and_fmcg_brands, pharmaceutical_manufacturing, solar_panels_inverters_and_batteries,
sports_goods_and_fitness_equipment_retail, used_car_dealers.

## 4. Open, by lane

**Linter and prompt (Learn to Pi session).** R-ANS-02 (only an acknowledgement opener to a yes/no
question is caught), R-ECHO-01 ("once per problem" not counted), R-ECHO-02 (the three-new-problems
exception), R-TONE-02 (reply wording is the model's; prompt owner). Eight older Brain rules still
carry "prompt owner" and ten "linter hardening session" in the coverage page.

**Solutions and detection (PI-Brain session).** R-SOL-03 (reassurance wording unchecked), R-SOL-04
(stored industry-entry ideas not checked against the person's own words), R-SOL-09 (a stored idea
that is regulated advice is not rejected by the idea guard), P-LANG-PIN (`detect_language` still
returns only en, roman_ur or ar), A2-2.1 (overlays hold one entry; sector neighbours not built),
A2-FIX-2, A2-2.4-SECTOR, A2-3.10, A2-4-DATA. Industry detection from problem words alone is still
the weakest part: in the last valid real-model replay one of eight industries was wrong.

**Learning (Learn to Pi session).** A2-FIX-5 is the one MISSING rule: openers and build phrasings
are not learned from owners' responses. Also A2-3.3, Job S3, SL-4.

**Docs and index (this session).** The index and coverage page are current. The audit report
(Part A.6) exists only as the numbers above and the offline script, not as a document.

**Workzap owner.** Fifteen items in the coverage page need a decision or a check only the owner can
make (for example A2-2.5-1 to 3, the provider data-retention setting).

## 5. Integration run

One full run of `tests/integration/test_pi_*.py` on the disposable database (port 55432), no real
model, on origin/main `5bee026` on 2026-10-26: **627 passed, 1 skipped, 2 failed** in 20 minutes 47
seconds.

| Failure | What it is |
|---|---|
| `test_pi_solution_gaps_db.py::test_g5_promotion_needs_a_non_negative_score_and_the_best_live_rate` | The known flaky test: it fails in a full run and passes alone, in two reruns. Order-dependent, in the solution-learning lane. |
| `test_pi_learning_gaps_db.py::test_every_reply_can_be_traced_to_what_it_used` | A real failure, every time, also alone. Since the reply stamp moved to send time, an audit row exists before the test sets its lesson and example, and `stamp()` returns that row. The product path reads the real data at send time; the test's setup order is out of date. Learn to Pi session to fix. |

The courtesy-stop test the API testing session listed as flaky passed in this run.
