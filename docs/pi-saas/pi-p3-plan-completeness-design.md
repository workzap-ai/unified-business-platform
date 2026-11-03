# P-3 design: industry plan-completeness scorer (scripted; no thresholds, no verification claims)

Status: DESIGN DOCUMENT, 2026-10-30, branch `pi/e-p3-plan-design`. Lane E (owns `evalkit/**`). Nothing is
implemented: no code, no evalkit change, no model call. Owner conditions: the scorer is designed now;
**no industry verification threshold and no minimum case count is defined here** (D5 is pending), and no
industry is claimed verified.

**What a scripted score is.** Every result this scorer can produce on scripted or hand-written plans checks
the scorer and the structure of a plan. It is not real AI quality. A real model's plans would be measured
only in P-5 Stage 3, after separate approval. Reports must label scripted numbers "scripted".

## 1. What "a complete plan" means (the elements to score)

From the owner's requirement 3 and B7.4: modules, workflow, implementation steps, dependencies, roles,
a realistic next action, and constraints honoured. For each element: what the repo already stores, and
whether a scorer can read it.

| Element | Where it lives today (read from the code) | State |
|---|---|---|
| E1 modules | `BoxDraft.components` (catalogue `key`, `phase`, `problems`); stored as `content["components"]` (`brain_docs.py:99-105`, `box_doc.py`). Catalogue is closed: `solutions.CATALOGUE` (`solutions.py:26`) | stored, structured |
| E2 problem coverage | `check_solution`: every problem is addressed or in `wont_do` (R-DOC-02/03/04, `brain_docs.py:219-245`); `structure_issues`: every problem has ideas, a cluster and a place in the order (`box_doc.py:286`) | stored, already checked in code |
| E3 workflow / order | `order_of_work` (`box_doc.py:144`): owner rank first, then `blocks` links moved ahead; each step has `why` | stored, derived from problem links |
| E4 phases | `BoxDraft.phases` (names), components carry `phase` 1 to 4 (`MAX_PHASE`) | stored |
| E5 dependencies | only problem-to-problem `blocks` links, as ordering. No build-to-build or external dependency (accounts, data, devices, people) | **partial** |
| E6 roles | no field. Roles appear only inside free text, and the safety rules forbid third-party names | **not stored** |
| E7 implementation steps | not stored. Components are one catalogue sentence; phases are names | **not stored** |
| E8 next realistic action | `needs` (what Workzap needs from the owner, max 6) is the nearest thing; no "next action" field | **partial** |
| E9 constraints honoured | constraints are planned for B2a (budget, staff, deadline, cannot-change); FT-C1 will reject ideas that violate a confirmed constraint. `needs` and `wont_do` exist | **depends on B2a / C1** |
| E10 industry fit | `industry` on the customer, packs and `entry` ideas (`expert_advisor.pack_examples`); catalogue wording takes the sector (`catalogue_text(key, language, sector)`) | stored, loosely linked |

Other plan-shaped outputs: the expert advisor returns `Advice(ideas, question, causes, problem, ...)`
(`expert_advisor.py:304`): ideas and one question, not a plan. The older solution document
(`SolutionDraft`: components, covers, wont_do, needs) is the smaller form of the same data. The Box is the
plan this scorer reads first; ideas are scored by FT-A3 (relevance), not here.

**Consequence for the design.** E5, E6, E7 and E8 cannot be scored for presence until the plan carries
them, and today the plan format deliberately forbids price, date, promise and "will". So the scorer is
built in two layers: layer A reads what exists now; layer B is specified here but activates only if the
owner approves adding those fields (an owner decision, question Q1).

## 2. Scorer design

**Input:** a stored Box or document `content` dict (as produced by `solution_content` / the Box builder)
plus the case's expected record. **Output:** per element a result of `present` / `absent` /
`not applicable`, with the evidence (the key or the text span), never one blended number. A blended
"completeness percentage" would hide a missing element; the report keeps the elements apart, as the other
evalkit scorers keep recall and precision apart.

**Layer A (reads current fields, deterministic, no model):**

| Check | Rule | Needs language-specific text? |
|---|---|---|
| A1 modules present | `components` non-empty; every `key` in the catalogue | no |
| A2 each component answers a problem | `problems` non-empty and refs known | no |
| A3 every stated problem handled | in a component, in `wont_do`, in a cluster, and in the order (reuse the `structure_issues` and `check_solution` results as the evidence, do not reimplement) | no |
| A4 phases coherent | phases named once per used phase number, component phase in 1 to 4 | no |
| A5 order respects blocks | a problem that `blocks` another comes first in `order` (re-derive from links; compare) | no |
| A6 left-alone reasons | each `wont_do` has a problem ref and a plain reason | no |
| A7 needs asked, not invented | `needs` non-empty when the case marks facts as missing; none of the needs is a fact the case says the owner already gave (redundant-ask check, shared with P-2) | partly |
| A8 the owner's own facts reused | a figure or tool the owner stated in the case appears in the plan text | yes (see section 3) |
| A9 expected modules covered | the case lists, for the industry, which module keys a competent plan must include and which are acceptable alternatives | no |
| A10 forbidden content absent | price, date, outcome promise, "will", jargon, third-party names (reuse `check_solution`, `box_text_issues`, the redactor) | yes |

A9 is the only check that needs human-written expectations per case. It must allow alternatives (a set
per slot), because "one right plan" is not true for a business problem.

**Layer B (needs fields the plan does not have today; specification only):**

| Check | Rule |
|---|---|
| B1 steps | each component has an ordered step list, each step one action by a named role |
| B2 dependencies | each step lists what it needs first (another step, a fact from the owner, an account, data) |
| B3 roles | each step names a role (owner, manager, staff role, Workzap reviewer); never a person's name |
| B4 next action | exactly one realistic first action for the owner, doable without Workzap, stated without a price or promise |
| B5 constraints | each constraint in the record (B2a) is either honoured by the plan or named under `wont_do` with the reason; a violated confirmed constraint is a hard failure, not a lower score (per the approved plan) |

## 3. Detecting elements per language, deterministically

Principle: prefer structure over words. Layer A mostly reads keys, refs and numbers, so it is
language-independent. Words are needed only for A8 (reuse of the owner's facts), A10 (forbidden text) and
the future Layer B text. Method for those, the same as the existing scorers:

1. Compare **normalised tokens**, not translations: figures (digits, with Urdu, Arabic-Indic and
   Devanagari digits mapped to ASCII), product and tool names, places. These carry across languages.
2. Case files hold the expected figures and tools **in the case's own language**, so no translation is
   needed. The scorer never calls a model.
3. For each language the forbidden-word and promise banks are the repo's existing banks
   (`constitution.PROMISE`, `JARGON`, `MONEY_IN_TEXT`); where a language has no bank, the check is
   reported "not covered for this language", never passed.
4. Layer B cues (illustrative only, to be reviewed by a native reader per language before use, **not
   decided**): English "first / then / after / needs / by the owner"; Roman Urdu "pehle / phir / uske baad /
   zaroorat / maalik"; Urdu script "پہلے / پھر / اس کے بعد / ضرورت / مالک"; Arabic "أولاً / ثم / بعد ذلك /
   يحتاج / المالك"; Hindi "पहले / फिर / उसके बाद / ज़रूरत / मालिक". A cue list can only show that a step
   *looks* sequenced; it cannot judge whether the step is sensible. That judgement is not scripted.

Known limits by language: the repo's problem-cue and promise banks are strongest in English and Roman
Urdu (CLAUDE.md and the plan's own audit); Urdu script, Arabic and Hindi are weak, and the `PROMISE` bank
has no Hindi entry that I could confirm without a per-language read. The report must say so per language.

## 4. Negative controls (the scorer must fail on these)

Written as plans the scorer must mark, so a scorer that passes everything is caught:

1. empty plan: no components, no `wont_do` (A1, A6 fail);
2. a component whose `problems` list is empty (A2);
3. a stated problem missing from clusters and order (A3);
4. `blocks` link A to B with B placed before A (A5);
5. a plan with a price, a date, "will", or "we guarantee" (A10);
6. a plan that asks for a fact the case record already holds (A7);
7. a plan that reuses none of the owner's figures or tools although the case has two (A8);
8. a plan for the wrong industry (modules from a different trade) (A9);
9. a plan with a third-party name in a step (B3);
10. a plan that violates a confirmed constraint but scores well elsewhere: the report must show a hard
    failure, not a pass (B5);
11. a plan padded to look complete: fifteen generic steps that name no problem (must not raise any score;
    each step needs a problem ref);
12. each control repeated in each reported language, so a language-specific blind spot shows.

## 5. Worked examples (written out; hand-authored, scripted)

These are examples of the case and expected-record shape. They are not data, not verification, and none
counts toward any industry.

**Example 1, English, retail (a case that should score "present" on A1 to A6, A8).**
Owner: "I run a shoe shop in Lahore. I count stock by hand every Sunday and I still run out of sizes 8 and
9. Staff are two people. I can spend about Rs 50,000."
Expected record: problems `stock_out` (figures: sizes 8, 9; frequency: weekly count); constraints: staff
2, budget stated (the plan must not repeat the figure; money appears only on the quote); modules acceptable
for the slot "stock": any of {`inventory_tracker`, `low_stock_alert`} (catalogue keys to be named from
`solutions.CATALOGUE` when the case is written). Expected result: A1 present, A3 every problem handled, A8
present only if the plan text carries "sizes 8 and 9" or "Sunday count".

**Example 2, Roman Urdu, services (a plan with a defect the scorer must report).**
Owner: "Mere salon mein booking WhatsApp pe aati hai, kabhi kabhi do log ek hi time pe aa jate hain. Aur
customers ka phone number copy mein likhte hain." Plan has one component for bookings and none for the
notebook, and no `wont_do`. Expected: A3 absent for the notebook problem (not in a component, not in
`wont_do`), A6 absent. The scorer returns two `absent` results with evidence, not a low number.

**Example 3, Urdu script, clinic (language coverage honesty).** Same shape as example 1 with Urdu text and
a figure written with Urdu digits. Expected: the figure is matched after digit normalisation; the
forbidden-word check reports "not covered for this language" if no Urdu bank exists, and the overall
report shows that gap rather than a pass.

**Example 4, English, a constraint conflict (Layer B, B5).**
Owner: "We cannot change the billing system; it is a legacy tool." A plan that includes a component that
replaces billing. Expected: hard failure on B5 regardless of the other elements.

**Example 5, Arabic and Hindi (shape only).** One case each, same checks, expected values written in the
case's language; their purpose is to show a scorer error in a non-Latin script (digit mapping, right to
left token order), not to measure the language.

## 6. Current coverage (honest)

Read from the repo at `cc462c5` and from the D5 proposal on branch `pi/d-decision-docs`:

- **There are no plan or solution cases in evalkit.** `evalkit/cases/` holds only `extraction.json`: 132
  cases (Development 69, Held-out 60, Regression 3). They carry `expected`, `industry`, `kind`,
  `language`, `messages`, `recorded`, `regression`. They test what pi *noted*, not what it *planned*.
  The FT-A3 plan (30 scripted solution cases) is not built.
- **Industry coverage of those 132 cases:** 89 industries appear. 68 have one case, 20 have three, one
  has four. **No industry has 10 cases.** Per the D5 proposal's own status line, every industry is "not
  yet measured".
- **The 211-industry check** (`docs/pi-saas/pi-211-industry-check.csv`, 211 rows): columns are
  `industry_id, pack_stored, pack_version, solution_stored, solution_version, probes,
  identified_on_probe, retrieved_on_probe, tool_word_lines, ending_repeat`. Counted from the file:
  solution stored 211 of 211; identified on every probe 179 of 211; retrieved on a probe 207 of 211. It
  measures **detection and stored text**, not plan completeness. It has no column for modules, steps,
  dependencies, roles or next action. Nothing in it can be read as an industry being verified.
- No real-model plan has ever been scored. Prior real-model testing (a 26-scenario suite) predates
  the Box and the key is revoked.

## 7. Representative cases per industry: question list for D5 (no answers decided)

This document sets no number. The owner (D5) decides each of these:

1. **What counts as an acceptance criterion for a plan?** Which elements must be present (Layer A only, or
   Layer B too), and is a missing element a fail or a reported gap?
2. **Which case types must an industry have?** Candidates: a single clear problem; several problems in
   one message; a list; a correction; a constraint that rules out the obvious fix; a vague owner who
   needs a question first (where "no plan yet" is the right answer); mixed language; a follow-up in a
   later chat. Which are required per industry and which per sector?
3. **How many cases per industry and per case type**, and how is "enough" justified? (The D5 proposal
   already raises a count question; this list does not answer it.)
4. **Sector or industry?** With 211 industries, is acceptance per industry, per sector group, or per
   industry only for those the business serves (RT29, served trades)?
5. **Who writes the expected module sets (A9)?** A domain reviewer per sector, since a wrong expectation
   makes a wrong test, and pack text for regulated trades (pharmacy, infant formula, NGOs, microfinance)
   needs a human reviewer in any case.
6. **How are alternatives expressed** so that a competent but different plan is not marked wrong?
7. **Is a "no plan, ask one question" outcome a pass** for a vague case, and how is it labelled?
8. **Language:** which languages must each industry's cases cover, given only English and Roman Urdu
   currently have enough cases to be measured at all?
9. **Held-out discipline:** does the plan case set get its own Development, Regression and Held-out split
   (the same stable hash on the case id), and who may open Held-out?
10. **Real-model step:** which plan cases go to Stage 3 first, and what separate approval does that need?

Until these are answered, the report prints every industry as "not yet measured" for plan completeness.

## 8. Dependencies, owner decisions and limits

- **Depends on:** FT-A2 (constraint scorer, merged), FT-A3 (relevance scorer and the 30 scripted solution
  cases, planned), B2a (constraints, for B5), FT-REQ (requirement sheet), D5 (industry criteria and any
  threshold), the `grader` agreement test for anything judged by a model. Layer B depends on an owner
  decision to extend the plan format (Q1).
- **Outstanding owner decisions:** Q1 extend the plan with steps, dependencies, roles and a next action
  (this conflicts with today's rules that forbid dates, promises and "will"; wording must stay "would");
  the D5 questions above; who labels expectations and who reviews care text.
- **Lane and files:** lane E: new `evalkit/plan_scorers.py` and `cases/plans.json` and tests only, read-only
  use of `brain_docs.py`, `box_doc.py`, `solutions.py`. No production code, no migration. A new unit test
  file must not share a name with an integration test file (CLAUDE.md).
- **Limits of this document:** read from the code and the files at `cc462c5`; no plan was scored; the
  language cues are illustrative and unreviewed by native readers; `solutions.CATALOGUE` keys in the
  examples are placeholders to be filled from the file when cases are written; coverage counts for the
  132 cases come from the D5 proposal and were not re-counted here.
