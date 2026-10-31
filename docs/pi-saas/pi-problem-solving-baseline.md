# pi problem-solving: scripted baseline (PS-0)

Pinned to `origin/main` **c73cf4f** (worktree `ps0`, branch `pi/ps0-baseline`, 2026-10-31). Numbers only: no
acceptance wording, no percentage target. Nothing here is a measure of the model.

## 1. Protocol (written before the numbers)

**Minimum for a measured cell** (set in code before this report was produced: `ps_scorers.MIN_CASES = 3`,
the existing evalkit constant, and `ps_scorers.MIN_ITEMS = 10`): a cell is printed as a percentage only when
it has at least **3 cases that contribute items** and at least **10 scored items** (the denominator). Below
either, the cell prints `not yet measured (num/den, N cases)`. Every cell shows its `num/den`.

**Cases.** `cases/problem_solving.json`: 60 conversation cases (`case_type` conversation, `format_version` 2,
`kind` problem_solving), 15 scenarios x 4 languages (en, roman_ur, ur, ar). 15 industries: property
management and rentals (rental management), e-commerce and D2C, sports clubs and turf rentals (bookings),
wedding planners (wedding management), banquet halls, salons, clinics (reception), auto workshops (repair),
poultry farms, private schools, restaurants, trucking, gyms, pharmacies, dropshipping. Each case has four owner
turns: T0 incomplete first message with one wrong figure, T1 a connected second problem + a hard limit + a thing
tried + the owner's own cause, T2 the corrected figure ("not 10, it was 100", "10 nahi 100", Urdu, Arabic) and a
request for a fix, T3 a rejection of pi's idea and a changed requirement. Each case also holds three
reference pi replies, reference extractor notes per turn, labelled candidate ideas, the allowed question slot per
pi turn, and a reference blueprint (steps, dependencies, resources, success criteria). All text is synthetic and
was drafted by agents; **no human has reviewed it** (`provenance.reviewer` is null).

**Splits.** Not stored in a case. `splits.split_of`: `regression` true gives Regression, else
`sha256(id)[0] % 100 < 25` gives Held-out, else Development. The case-id to split table is section 6. The 60 new
cases have no Regression case (none is a past failure); the Regression row below uses the 3 existing extraction
cases tagged `regression`. **Held-out is sealed**: the report skips it (`ps_report.score_all`), `replay_case`
refuses it without an `access_log.Pass`, a unit test proves both, and no Held-out case was replayed, scored or
used to choose a cue, threshold or wording. Authors of the case text did not compute splits.

**What is scripted and what is the live code.** Run per owner turn, no model call: the live gate
`problem_extract.wants_extraction`; the live `problem_extract.extract` (caps, per-note checks, known-title filter)
fed by the case's hand-written reference notes through the existing `ScriptedManager`; the live
`figure_correction.numeric_correction`; the live `problem_fields.merge_cause`; the live `idea_filter.failures`
with `context_from` the noted problems; `language.detect_language`; `expert_advisor.question_ok` and
`same_question`; the Solution Box schema `brain_docs.BoxDraft`. Scripted (not model output): the extractor's
notes, pi's three replies per case, the labelled candidate ideas, the blueprint. Not run: the reply model, the
flow state machine, the database, the idea engines, document drafting.

**Two record sets.** `live` = what the current extractor shape (`SimpleNote`, `problem_extract.py:51-68`) can
carry: it has no field for constraints, things tried, a cause or an expected outcome, so the real path drops them
(metrics without a suffix). `_reference` = the same notes with those fields added back; it checks the scorers
and shows what the notes hold (reference notes exist for owner turns 0 and 1 only, so limits said in turn 3 are
not in them); it is not a ceiling for the model.

**Metrics** (all as `num/den`): problem recall and precision; figure fidelity; correction detected (the live
finder) and applied; stated facts, constraints and things tried kept in the saved records; owner-said cause
captured; unsupported cause confirmed; a guessed cause stays a hypothesis (`merge_cause`, with and without a
wrong "owner said" flag); relevance scorer agreement with the labels, false relevant, limit-violating ideas the
scorer missed; limit-violating ideas rejected by the live idea filter (any rule, and by a rule other than G8);
relevant ideas kept by the live filter; language of pi's reference replies; repeated question; unclassified
question; one-question form; blueprint elements present, dependencies valid, tied to owner words, steps breaking
a stated limit, price or promise in the blueprint.

**Known limits of the numbers.** Question, language and blueprint metrics score hand-written reference text, so
they check the scorers and the case design, not pi. The repeated-question scorer uses a small fixed cue list per
slot (en, roman_ur, ur, ar); the cues were adjusted on Development cases after a first run showed which
questions it could not classify; unclassified questions are counted separately and never as "fine". The
relevance scorer agreed 55% with an independent grader on the borderline set (see `relevance.py`). The live
idea filter is given only the noted problems and the owner's words (no pack entries, industries or map nodes
the live path may add). Correction application is simulated by `figure_correction.replace_figure` over the
record's text fields; where the live path applies it was not traced into the run.
