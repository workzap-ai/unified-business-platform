# One shared evaluation case format for extraction, conversation and plan cases (v1)

Status: PROPOSAL for owner review, 2026-10-30. Documentation only: no evalkit code, case file or test
was changed. Lane E owns `evalkit/**` and the case files. Written for P-2
(`pi-p2-conversation-quality-scorers-design.md`), P-3 (`pi-p3-plan-completeness-design.md`) and FT-A3
(30 scripted solution cases and a relevance scorer). Read from `origin/main` (cc462c5).

Vocabulary: **documented** (this file), **implemented** (none), **scripted-tested** (none yet),
**real-model-verified** (none). A scripted result tests the code and the scorers, never the model.

## 1. What exists today (the format must not break it)

`evalkit/cases/extraction.json` is a JSON list of 132 cases. Every case has exactly these top-level keys:
`id`, `industry` (catalogue key), `language` (`en` 52, `roman_ur` 41, `ur` 19, `ar` 12, `hi` 8), `kind`
(`single` 42, `list` 37, `correction` 18, `rant` 10, `multi_turn` 9, `constraints` 9, `mixed` 7),
`regression` (bool; 3 true: `reg_audit5_four_lines`, `reg_six_problems`, `reg_correction_figure`),
`messages` (owner messages only; 28 cases have more than one), `expected` and `recorded`.

- `expected`: `problems` (each `{id, any: [keywords], figures: [..]}`), `stated` (owner phrases that must
  survive), `missing` (what the owner did not say), `hypothesis_only` (causes that must stay hypotheses),
  `corrections` (`{wrong, right, problem}`), and for 9 cases `constraints` (list of strings).
- `recorded`: `origin` ("reference output written by hand, not model output") and `notes` (the extractor's
  notes: `title`, `title_local`, `user_words`, `summary`, `category`, optionally `cause`, `cause_status`,
  `constraints`, `money_text`).
- No case stores its split. `splits.split_of`: `regression` true gives Regression; otherwise
  `sha256(id)[0] % 100 < 25` gives Held-out, else Development. Today: Development 69, Held-out 60,
  Regression 3. `held_out_access(log, who, why)` builds an append-only record but nothing stores it.
- `scorers.MIN_CASES = 3`: a group with fewer labelled cases is "not yet measured", never "passing".
- `replay` runs the recorded notes through the real extraction path with `ScriptedManager`; no model call.
- Unit tests today (`test_pi_evalkit_heldout.py`): unique ids; no message shared between Held-out and the
  other sets; every case complete; language and kind coverage; the split is still the hash of the id.

## 2. Design rules

1. **Additive only.** The 132 extraction cases and `extraction.json` stay byte-identical. New case types
   go in new files: `cases/conversation.json` and `cases/plan.json`. Ids are unique across all case files.
2. **One envelope, three case types.** A new top-level `case_type` is `"extraction"` (default when absent,
   which is every existing case), `"conversation"` or `"plan"`. Existing `kind` keeps its meaning (the
   scenario shape); new kinds are listed below.
3. **The split is never stored in the case.** It stays `split_of(case)`: Regression if `regression` is true,
   else the hash of `id`. The same function serves all three types, so adding a case never moves another.
4. **Expected values describe what the owner said, never what pi should invent.** A cause the owner did not
   state is listed under `hypothesis_only`.
5. **Synthetic text only** (section 8).
6. **A case says what is expected; a run says what was run.** `mode` belongs to the run and the report
   (section 7), and `recorded.origin` states where a recorded output came from.

## 3. The shared envelope

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | string | yes | unique across all files; lower snake case; the split hash input; never renamed |
| `case_type` | `extraction`/`conversation`/`plan` | no | absent means `extraction` |
| `format_version` | integer | new files: yes; old: absent means 1 | this document defines 2 for `conversation` and `plan` |
| `industry` | string | yes | catalogue key from `packs/industry` |
| `language` | `en`/`roman_ur`/`ur`/`ar`/`hi` | yes | main language of the owner turns; a mixed case adds `languages: [..]` |
| `kind` | string | yes | extraction kinds as today; conversation kinds in section 5; plan kinds in section 6 |
| `regression` | boolean | yes | true only for a past failure; never removed |
| `title` | string | no | at most 8 words, the same rule `check_ops` applies to titles |
| `synthetic` | boolean | new files: yes, must be true | invariant, see section 9 |
| `provenance` | object | new files: yes | `{author, reviewer, created, origin}`; `origin` is `hand_written` |
| `notes` | string | no | free text for reviewers, never read by a scorer |

## 4. Extraction cases (`case_type` absent or `"extraction"`): unchanged

Schema stays exactly section 1. Optional additive fields, allowed only in cases added after this format is
approved: `expected.tried`, `expected.cause`, `expected.expected_outcome` (see section 5.3). No existing
case gains a field.

Worked example (the existing `acc_correction_en`, abridged): `messages` = a statement of "about 10 clients"
then "not 10, it was 100"; `expected.problems[0].figures = ["100"]`;
`expected.corrections = [{"wrong": "10", "right": "100", "problem": "p1"}]`.

## 5. Conversation cases (`case_type: "conversation"`): P-2

New `kind` values: `repeat_trap` (a fact is given early and must not be asked again), `requirement_carry`
(a requirement must survive to the summary and plan), `reask_allowed` (a legitimate re-ask), `idea_depth`
(ideas must go beyond the owner's words), `correction_flow`, `long_list`.

### 5.1 Turns

`turns`: ordered list. Each turn:

| Field | Type | Notes |
|---|---|---|
| `role` | `owner` or `pi` | |
| `text` | string | owner turns are scripted text; pi turns are the **reference reply** (hand-written) in scripted mode |
| `reply_source` | `reference` or `live` | `reference` is used by scripted runs; a real-model run replaces `reference` replies with the model's and stores them in the run output, never in the case file |
| `record_after` | object, optional | the expected record snapshot after this turn (section 5.3) |

The case file never contains a model-generated reply. Owner turns are never model-written either (the
stage 3 proposal uses scripted owner text and real pi replies).

### 5.2 Labels for the four P-2 scorers

`expected` (conversation):

| Field | Type | Used by |
|---|---|---|
| `requirements` | list of `{id, text, any: [keywords], figures: [..], kind, said_in_turn, sinks}`; `kind` is `figure`, `constraint`, `fact`, `correction`, `tried`, `workflow`, `role`, `system`, `outcome`; `sinks` is a subset of `record`, `summary`, `solution` (where the requirement must survive; P-2 section 0, lines 22-26) | requirement preservation (record, summary, plan text) |
| `answered_facts` | list of `{slot, value_words, said_in_turn}`; `slot` is one the redundant-question scorer knows (count, money, tool, place, who, since, how_often) | redundant question |
| `legit_reasks` | list of `{slot, turn, reason}`; `reason` is `owner_corrected`, `owner_unsure`, `figure_ambiguous` | exempts a re-ask from repetition and redundancy |
| `must_not_repeat` | list of phrases or ideas pi must not say twice | repetition |
| `owner_words_for_creativity` | list of owner phrases | creativity (an idea that only restates these is capped at 0) |
| `pack_ideas_ref` | list of pack idea keys | creativity (an idea equal to a stored pack idea is capped) |
| `unclassified_ok` | boolean, default false | a question with no recognised slot is reported "unclassified", never "not redundant" |

Creativity itself is a grader judgement (0 to 2, never by the model that produced the reply). The case
carries no creativity expected value, because creativity is not a labelled fact; the human-labelled samples
live in a separate labelling file (P-2 design section on labelling), not in the case.

### 5.3 P-1 fields as expected values (shared by extraction, conversation and plan)

Names match the schema proposed in `pi-p1-schema-review.md`. All optional; a case lists only what the owner
actually said.

| Field | Shape | Legacy compatibility |
|---|---|---|
| `constraints` | list; each item is a **string** (legacy, as the 9 existing cases) or `{kind, text}` with `kind` in `budget`, `staff`, `deadline`, `cannot_change` | a scorer treats a string as kind-less; no existing case changes |
| `tried` | list of `{what, outcome}` | new |
| `cause` | `{text, status, evidence_words}`; `status` is `owner_said`, `pi_inferred` or `confirmed`; an unsupported cause may never be `confirmed` | new; `hypothesis_only` stays for causes the owner did not state |
| `expected_outcome` | string, at most 300 characters, in the owner's words | new |
| `workflows` | list of short strings, owner's words | new (per customer in P-1, per case here) |
| `roles` | list of **roles only**, never names (for example `cashier`, `supervisor`) | new |
| `systems` | list of tools or systems the owner named | new; `systems_mentioned` on a problem is the nearest existing field |

Where in a case: `expected.problems[i]` may carry per-problem `constraints`, `tried`, `cause` and
`expected_outcome`; the customer-level `workflows`, `roles` and `systems` sit directly in `expected`.

### 5.4 Worked example (synthetic)

```json
{
  "id": "conv_repeat_trap_en_01",
  "case_type": "conversation",
  "format_version": 2,
  "industry": "furniture_manufacturing_and_woodwork",
  "language": "en",
  "kind": "repeat_trap",
  "regression": false,
  "synthetic": true,
  "provenance": {"author": "lane E", "reviewer": null, "created": "2026-10-30", "origin": "hand_written"},
  "turns": [
    {"role": "owner", "text": "Custom orders ship late. We have 2 supervisors and about 300,000 rupees to spend."},
    {"role": "pi", "reply_source": "reference", "text": "Late custom orders with two supervisors is a hard spot. When does the first one usually slip?",
     "record_after": {"problems": [{"id": "p1", "constraints": [{"kind": "staff", "text": "2 supervisors"}, {"kind": "budget", "text": "about 300,000 rupees"}]}]}},
    {"role": "owner", "text": "Mostly in the sanding step."}
  ],
  "expected": {
    "requirements": [
      {"id": "r1", "kind": "constraint", "text": "2 supervisors", "any": ["supervisor"], "figures": ["2"], "said_in_turn": 0},
      {"id": "r2", "kind": "constraint", "text": "about 300,000 rupees", "figures": ["300,000"], "said_in_turn": 0}
    ],
    "answered_facts": [{"slot": "count", "value_words": ["2", "supervisors"], "said_in_turn": 0}],
    "legit_reasks": [],
    "must_not_repeat": ["how many supervisors"],
    "owner_words_for_creativity": ["ship late", "custom orders"]
  }
}
```

## 6. Plan cases (`case_type: "plan"`): P-3 and FT-A3

New `kind` values: `plan_from_brief` (P-3 plan completeness), `solution_relevance` (FT-A3: score candidate
ideas), `constraint_violation` (an idea that breaks a confirmed constraint must be rejected whatever its
score).

### 6.1 Inputs

`input`: either `messages` (owner messages, as in extraction) or `from_case` (the id of a conversation case
whose final expected record is the brief) plus an explicit `brief`: `{problems: [{id, title, figures,
constraints, tried, cause, expected_outcome}], workflows, roles, systems}` using the section 5.3 shapes.
Industry comes from the envelope; a plan case never invents an industry.

### 6.2 Expected plan (P-3)

`expected.plan`:

| Field | Type | Notes |
|---|---|---|
| `modules` | list of `{id, key, any: [keywords], covers: [problem ids]}`; `key` is the closed catalogue key of the module (`BoxDraft.components`, P-3 document element E1); `any` is used when a keyword check is wanted instead | exists today in the Solution Box and the older document |
| `needs` / `wont_do` | optional lists of short strings | exist today (`needs` is the nearest thing to a next action; `wont_do` lists problems not addressed; P-3 elements E2 and E8) |
| `steps` | optional list of `{id, any, module}` | **layer B only**: the stored plan has no steps today; this field is inert until the owner approves extending the plan format (P-3 question Q1) |
| `dependencies` | optional list of `{from, to}` | layer B only |
| `roles` | optional list of roles | layer B only |
| `next_action` | optional `{any: [keywords]}` | layer B only; wording must stay "would", never a promise |
| `constraints_honoured` | list of constraint ids from the brief | an idea or step that violates one is a hard failure, not an averaged score |
| `forbidden` | list of phrases or rule ids (price, date, "will", named product, build promise) | checked against the plan text |

No threshold appears in a case. Pass levels come from D5, after the owner approves them.

### 6.3 Candidate ideas for the relevance scorer (FT-A3)

`expected.candidates`: list of `{id, text, verdict, reason, problem}` with `verdict` in `relevant`,
`irrelevant`, `generic`, `violates_constraint`, `restates_owner`. `problem` is the problem id the idea should
link to (or null). The scripted relevance scorer reads only these labels, so its job is to reproduce them
deterministically; it is later checked against the `grader` agent and hand labels (the 85% proposal).

### 6.4 Worked example (synthetic)

```json
{
  "id": "plan_relevance_furn_en_01",
  "case_type": "plan",
  "format_version": 2,
  "industry": "furniture_manufacturing_and_woodwork",
  "language": "en",
  "kind": "solution_relevance",
  "regression": false,
  "synthetic": true,
  "provenance": {"author": "lane E", "reviewer": null, "created": "2026-10-30", "origin": "hand_written"},
  "input": {
    "brief": {
      "problems": [{"id": "p1", "title": "Custom orders ship late",
        "constraints": [{"kind": "staff", "text": "2 supervisors"}, {"kind": "cannot_change", "text": "cannot stop production for training"}]}],
      "roles": ["supervisor"], "systems": []
    }
  },
  "expected": {
    "candidates": [
      {"id": "c1", "text": "A shared weekly list of orders by step, checked by a supervisor each morning", "verdict": "relevant", "problem": "p1", "reason": "fits two supervisors, no training"},
      {"id": "c2", "text": "Send every supervisor to a two-week training course", "verdict": "violates_constraint", "problem": "p1", "reason": "cannot stop production for training"},
      {"id": "c3", "text": "Use better software", "verdict": "generic", "problem": null, "reason": "no link to the stated problem"}
    ]
  }
}
```

## 7. Scripted versus real-model runs

- A **case** contains no run mode. A **run record** carries: `mode` (`scripted` or `real_model`), `stage`
  (`scripted`, `stage1`, `stage2`, `stage3`), `model_id` (null when scripted), `date`, `cap_usd`, `calls`,
  `split_used`, `held_out_access` entry (section 10), and `format_version`.
- The report header prints the mode in words. A `scripted` report is headed "code-path check: tests the
  extraction path, the scorers and the replay code, not the model". It never uses the words "AI quality".
  Creativity, depth and any grader-judged field are `null` ("not scored") in a scripted report.
- Each case result row repeats `mode`, so a mixed table cannot hide which rows were real.
- `recorded.origin` is enumerated: `hand_written` (reference output written by hand, not model output),
  `real_model` (saved output of an approved run, kept outside the case file and outside git unless the owner
  says otherwise), `none`. The scripted replay reads only `hand_written`.

## 8. PII and sensitivity rules for cases

1. Synthetic text only: every new case has `synthetic: true` and the text is written for the evaluation.
2. No real phone number, email, ID or card number. The only allowed card-like value is a published
   payment-provider test number, and only in a safety case that names it.
3. No real person or customer name. Roles only (`cashier`, `supervisor`, `driver`). No real business name;
   the industry key is the only business identifier.
4. No text copied from a real WhatsApp chat or a real staff record, even with names removed.
5. A pattern scan (phone, email, card, ID shapes, plus the redaction patterns of `safety.py`) runs over every
   `text`, `messages`, `user_words` and `notes` field in the invariants test.
6. Held-out and Regression follow the same rules; a past failure becomes a Regression case only after its
   text is rewritten as synthetic text.

## 9. Validation rules and the invariants test list

All checks run in unit tests (no database, no model). Names are proposals for `test_pi_evalkit_formats.py`
(a unit file name that does not clash with an integration file).

1. Every case file is valid JSON and a list; `extraction.json` is byte-identical to the approved hash.
2. Ids are unique across `extraction.json`, `conversation.json` and `plan.json`; none was reused.
3. Every case has the envelope fields of section 3; `case_type` is one of three; `format_version` is 2 in
   new files and absent in `extraction.json`.
4. `split_of` still equals the hash rule, and no case stores `split`.
5. No message or turn text is shared between Held-out and Development or Regression (the existing rule,
   extended to turns and plan inputs).
6. Every `said_in_turn`, `turn` and `from_case` reference resolves.
7. Every `expected.requirements[].figures` and `any` keyword appears in the owner's turns (an expected value
   the owner never said is a fixture bug), except `hypothesis_only` items.
8. `cause.status == "confirmed"` appears only when the owner's turns state the cause.
9. `roles` hold no capitalised personal names (the role-name pattern of `safety.py`).
10. Every `candidates[].verdict` is in the allowed set; every `solution_relevance` case has at least one
    `relevant` and one non-relevant candidate (otherwise the scorer has no negative control).
11. Every new scorer has a negative control: a case built to fail it does fail it.
12. A group below `MIN_CASES` is reported "not yet measured" for every new case type and every new scorer.
13. PII scan (section 8) passes; `synthetic` is true.
14. `title`, where present, has at most 8 words.
15. Layer B plan fields (`steps`, `dependencies`, `roles`, `next_action`) are ignored by the scorer unless the
    plan format is approved; a test proves that, so inert fields cannot change a score.
16. The existing 132 cases score exactly as before (golden totals recorded from the current baseline).

## 10. Splits, sealing and Held-out access

- **Assignment:** unchanged. Regression by tag, otherwise the stable hash of `id` (25% Held-out). Choosing
  an id is therefore the only way to choose a split, so ids are assigned before a case is reviewed and are
  never renamed to move a case.
- **Why a hash is not a seal.** Because cases sit in the repository, a Held-out case is readable by anyone who
  tunes prompts. Today this is controlled by rule (never tune on Held-out) and by the access record. For the
  stage 3 Held-out conversations this is weak: see open question 2.
- **Access log:** an append-only file of `{who, why, when, run_id, split, case_ids_or_count}`, written by the
  runner for every run that reads Held-out, and by a reviewer for any manual read. Proposed location:
  `docs/pi-saas/pi-eval-heldout-access.jsonl` (new, append-only). Nothing stores such a log today;
  `held_out_access()` only builds the record.
- **One-time use:** a Held-out result used for a decision is recorded once; re-running Held-out after tuning
  needs the owner's approval and a log entry.
- **Regression:** every past failure, never removed, never tuned away; a case enters Regression by the tag.

## 11. Versioning and migration

- `format_version` is an integer per file. Extraction cases have none (they are version 1 by definition).
  This document is version 2 for conversation and plan files.
- A change that only adds optional fields keeps the version. A change that renames, removes or reinterprets
  a field makes a new version and a new file; old files are never edited in place.
- The loader dispatches on `case_type` and `format_version`, and refuses an unknown version.
- Legacy shapes stay readable forever (for example `constraints` as a list of strings).
- Migration of the 132 cases: none. They stay as they are.

## 12. Mapping to the tasks

| Task | Uses | Status |
|---|---|---|
| FT-A3 (30 scripted solution cases, relevance scorer) | `plan` cases, kind `solution_relevance` and `constraint_violation` | documented here; not built |
| P-2 scorers | `conversation` cases | documented; not built |
| P-3 plan completeness | `plan` cases, kind `plan_from_brief`; layer B fields inert until Q1 | documented; not built |
| B2a / P-1 | expected values of section 5.3 give B2a's acceptance something to measure | documented; B2a not started |
| P-5 stages 2 and 3 | run record of section 7; Stage 3 needs sealed Held-out conversations | proposals only |

## 13. Open questions for the owner

1. **Files:** keep one file per case type (as proposed), or a single `cases` folder with one file per
   language? One file per type keeps `extraction.json` untouched.
2. **Sealing Held-out conversations.** The repository cannot hide a Held-out case from the people who tune.
   Options: keep Held-out conversation cases outside git (a sealed file held by the owner, hash recorded in
   the repo), or accept the rule-only seal. Which?
3. **Who authors and reviews the cases** (the P-2 and P-3 documents also ask), and who reviews the expected
   module sets and care text for regulated trades.
4. **Access log location and who may write it.** In the repository, or outside it?
5. **Constraint shape:** accept `{kind, text}` objects beside the legacy strings, or require a migration of
   the 9 labelled constraint cases (which this document says not to do)?
6. **Layer B plan fields** stay inert until the plan format is extended (P-3 Q1). Confirm.
7. **Minimum case counts per case type, language and industry** are D5 items; nothing here sets them.
8. **Hindi** has 8 cases and no Held-out case; confirm it stays "not yet measured" until B4 and new cases.
9. **Real-model outputs:** keep saved model replies out of git (proposed) or inside a private folder?

## Appendix A. Decision status (APPROVED versus PROPOSED)

| Item | Status | Basis |
|---|---|---|
| Roadmap A to G is the master roadmap; this document adds no task and changes no priority | APPROVED | owner, 2026-10-30; roadmap plan section 8 header, `pi-fast-track-plan.md:158` on `pi/doc-fast-track` |
| P-1 to P-6 as additions, with the owner's conditions | APPROVED | roadmap plan section 8, lines 158-172 |
| FT-A3: scorer plus 30 scripted solution cases, owner of the files is lane E | APPROVED task; criteria unchanged | roadmap plan line 57 (D1 to D4 approved the Fast-Track; section 8 keeps it) |
| P-3: no verification thresholds before D5; P-2: 85% stays a proposal until the labelling method and labelled samples are reviewed | APPROVED conditions | owner's conditions on the Step 2 approval; roadmap plan lines 168-169 |
| The 132 existing cases and the existing evalkit invariants stay unchanged | APPROVED (existing behaviour and tests) | `splits.py:12-27`, `scorers.py:13`, `test_pi_evalkit_heldout.py:22-92`; roadmap plan line 107 |
| D5 thresholds, language scope, industry criteria | PENDING owner (not decided here) | roadmap plan line 123 |
| This case format itself (every field, kind, file name and rule in sections 2 to 11) | **PROPOSED** | needs owner review before lane E builds anything |
| New invariants 1, 4 to 16 of section 9 beyond the existing tests | **PROPOSED** | existing tests listed in Appendix B |
| Access-log file and sealing of Held-out conversations (section 10) | **PROPOSED**, open question 2 | nothing stores an access log today (`splits.py:25-27` only builds a record) |
| `mode` on the run and report (section 7) | **PROPOSED** | `report.py` has no mode today (`report.py:33-62`) |
| Reconciliation of field names with the P-2 and P-3 documents (Appendix C) | **PROPOSED** | the three documents currently differ |

## Appendix B. Source references (path:line) for every technical claim

All paths are on `origin/main` (cc462c5) under `apps/api/` unless stated. Counts were computed by reading
the case file with a short script on the worktree; they are not quoted from a document.

| Claim | Source |
|---|---|
| 132 cases; every case has `id, industry, language, kind, regression, messages, expected, recorded`; counts by language, kind; 28 multi-message cases | `app/modules/pi/evalkit/cases/extraction.json` (computed over the whole file) |
| Example of a list case and its `expected` and `recorded` shape | `extraction.json:3` (`acc_list_en`) |
| Example of a correction case, `corrections` shape | `extraction.json:141` (`acc_correction_en`) |
| Example of a constraints case, `constraints` as strings | `extraction.json:4366` (`furn_constraints_en`) |
| Regression cases | `extraction.json:1934` (`reg_audit5_four_lines`), `:3976` (`reg_six_problems`), `:4115` (`reg_correction_figure`) |
| No case stores its split; split by regression tag, else `sha256(id)[0] % 100 < 25` | `app/modules/pi/evalkit/splits.py:12` (`HELD_OUT_PERCENT = 25`), `:18-22` (`split_of`) |
| `held_out_access` only builds a record, nothing stores it | `splits.py:25-27` |
| Scripted replay runs recorded notes through the real extractor with no model call | `app/modules/pi/evalkit/replay.py:16-25` (`ScriptedManager`), `:39-57` (`replay`) |
| Replay builds history from `messages` as customer turns only, so it cannot carry pi turns | `replay.py:28-36` (`context_for`) |
| Replay copies `cause`, `cause_status`, `money_text`, `constraints` from the recorded note | `replay.py:13` (`EXTRA_FIELDS`), `:53-55` |
| Cases are loaded as a JSON list | `replay.py:60-63` |
| `MIN_CASES = 3`; a group below it is "not yet measured" | `scorers.py:13`, `:115-126` (`aggregate`), `report.py:25` |
| Figure and constraint matching rules | `scorers.py:37` (`figure_kept`), `:43` (`constraint_kept`), `:58` (`score_case`) |
| The report groups by split, language, case kind and industry | `report.py:33-62` |
| Existing invariants (unique ids; no shared message; complete cases; coverage; hash split; floors) | `tests/unit/test_pi_evalkit_heldout.py:22,26,31,38,48,55,62,67,76,86,92`; `tests/unit/test_pi_evalkit.py`, `test_pi_evalkit_constraints.py` |
| Extractor title rule (at most 8 words), the note cap | `app/modules/pi/problem_extract.py:34`, `:24` (`MAX_NOTES = 8`) |
| The extractor's `SimpleNote` has `money_text` but no `constraints` or `cause_status` field | `problem_extract.py:51-75` (`money_text` at `:69`) |
| Role-name patterns for the "roles, never names" check | `app/modules/pi/safety.py:819-833` (`ROLE_NAME`, `ROMAN_ROLE_NAME`, `DOCTOR_NAME`) |
| Roadmap rows used: FT-A1, FT-A2, FT-A3 (lane E), D5, merge check 8 | `docs/pi-saas/pi-fast-track-plan.md:55-57,123,107` on `pi/doc-fast-track` |
| Roadmap section 8: P-1 to P-6 rows and the conflicts list C1 to C10 | same file, `:158-196` |
| P-2 design: conversation case, record per pi turn, requirement sinks, answered, reask_ok | `docs/pi-saas/pi-p2-conversation-quality-scorers-design.md:9-31` on `pi/e-p2-scorer-design` |
| P-2 labelling method and the 85% proposal | same file, `:244-294` (section 7) |
| P-3 plan elements E1 to E10 and where they live; layers A and B; the question list for D5 | `docs/pi-saas/pi-p3-plan-completeness-design.md:12-61,172-198` on `pi/e-p3-plan-design` |
| P-1 field set (constraints, tried, cause, expected_outcome; workflows, roles, systems) | `docs/pi-saas/pi-p1-schema-review.md:34-86` on `pi/u-p1-schema-review` |

## Appendix C. Review against the roadmap and P-1 to P-6: unresolved conflicts and assumptions

Nothing in this document changes an existing acceptance criterion. The checks below are findings, not
changes.

### Conflicts (to be decided by the owner or lane E; none is resolved here)

| # | Conflict | Detail | Proposed resolution |
|---|---|---|---|
| CF1 | Field names differ between this document and the P-2 document | P-2 proposes `turns`, `record_at` (a map from pi-turn index to records), `answered` (`{slot, by_turn}`), `reask_ok` (list of turn indexes) and `requirements[].sinks`, `origin` (`pi-p2...design.md:15-28`). This document uses `record_after` per turn, `answered_facts`, `legit_reasks`, `requirements[].kind` plus `sinks`. | pick one set before lane E builds anything; this document adds `sinks` and the `fact` kind to match P-2, and leaves the rest as a PROPOSED rename list for the owner |
| CF2 | Plan module naming differs from the P-3 document | P-3 reads `BoxDraft.components` by closed catalogue `key` (`pi-p3...design.md:12-61`); this document now carries `key` and `needs` / `wont_do`, but P-3's own example keys are placeholders until real cases exist | keep `key`; P-3 must replace its placeholder keys with real catalogue keys when cases are written |
| CF3 | FT-A3's acceptance is "at least 85% agreement on 20 hand-labelled samples" (roadmap line 57); the P-2 proposal says 20 is too few and proposes a pilot of 20 then 60 | not decided here; FT-A3's wording stays as approved | owner decides in the P-2 method review; this document does not set a sample size |
| CF4 | Both P-2 and P-3 and this document introduce new case files while the roadmap lists only FT-A3 "new cases" (roadmap line 57) | P-2 and P-3 map to FT-A4 and FT-A5 in roadmap section 8 (lines 168-169), so the task ids exist, but no file ownership is stated for `conversation.json` and `plan.json` | the roadmap's lane E ownership (`evalkit/**`, `cases/*.json`, line 37) covers both files; confirm |
| CF5 | Held-out cannot be hidden in the repository | `split_of` is a hash of the id (`splits.py:18-22`), so a tuner can read every Held-out case in git; roadmap check 8 (line 107) assumes the split holds | open question 2: seal Held-out conversation cases outside git, or accept a rule-only seal |
| CF6 | Layer B plan fields collide with today's plan rules (no date, price, promise or "will") | `pi-p3...design.md:58-61` | the fields stay inert until P-3 question Q1 is approved (invariant 15) |
| CF7 | `constraints` has two shapes (legacy strings, new `{kind, text}`) | existing 9 cases use strings (`extraction.json:4366`) and `scorers.constraint_kept` takes a string (`scorers.py:43`) | the scorer adapts to read `text` from an object; no existing case changes; owner to confirm (open question 5) |
| CF8 | P-1 is still a proposal, so the field names in section 5.3 may change | D2 amendment is for owner review (`pi-p1-schema-review.md`, section 2.1) | section 5.3 is explicitly tied to the P-1 names; a P-1 decision changes it |

### Assumptions (stated, not verified)

1. A run's `mode` field and the report header (section 7) do not exist in `report.py` yet; adding them is
   lane E code work after approval, not part of this document.
2. **Scripted constraint scores read hand-written notes, not extractor output.** `replay.py:13,53-55` copies
   `constraints` and `cause_status` from the recorded note, but `SimpleNote` has no such fields
   (`problem_extract.py:51-75`). So today's constraint results test the scorer, not the extractor; B2a is
   what gives the extractor those fields. The shared format keeps that honest through `recorded.origin`.
3. The replay path (`replay.py:28-36`) has no place for pi turns, so conversation and plan cases need a new
   context builder; that is new code, not yet written.
4. The hash split gives roughly 25% Held-out only for large sets; small new files (for example 30 plan
   cases) can land with a different share. The format does not force a share; it states the rule.
5. The golden totals of invariant 16 are those of the current baseline report (`docs/pi-saas/pi-eval-baseline.md`
   on `origin/main`); I did not recompute them for this document.
6. The split counts (132 cases: Development 69, Held-out 60, Regression 3) were recomputed from the case file
   with the `splits.py:18-22` hash rule; 9 cases carry `expected.constraints`. They match the roadmap.
7. Examples in sections 5.4 and 6.4 are hand-written illustrations; their catalogue keys, categories and
   figures are placeholders and are not cases.

## Appendix D. Decisions recorded on 2026-10-30 (owner)

These three decisions resolve CF1, CF4 and CF5 for FT-A3. Everything else in this document stays PROPOSED.

| Item | Decision | Status |
|---|---|---|
| CF1 field names | The shared case-format vocabulary is used everywhere: `record_after`, `answered_facts`, `legit_reasks`, plus `sinks` and the `fact` kind. The P-2 design is corrected to match (branch `pi/e-p2-scorer-design`). | APPROVED |
| CF4 file ownership | Lane E owns `cases/conversation.json`, `cases/plan.json` and the evalkit case files. `cases/extraction.json` stays byte-identical. | APPROVED |
| CF5 sealing | For FT-A3 the seal is a rule only: the stable hash split of the case id, and a logged access for every Held-out read (append-only access log, no real-model access). Stage 3 Held-out conversation text must stay outside Git and needs a separate owner decision. | APPROVED for FT-A3; Stage 3 pending |
