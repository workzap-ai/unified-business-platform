# P-2: conversation-quality scorers, design and human-labelling method

> **Field names (CF1, approved by the owner on 2026-10-30):** this design now uses the shared case-format vocabulary `record_after`, `answered_facts`, `legit_reasks`, `sinks` and the `fact` kind from `pi-eval-case-format-v1.md`. Earlier drafts called them `record_at`, `answered` and `reask_ok`.

Status: DESIGN ONLY, 2026-10-30. No code, no case file, no model call, no spending. Written for the owner
(review) and for lane E (who would build it after approval). The 85% agreement threshold is a
**PROPOSAL** until the owner has reviewed the labelling method (section 7) and the labelled samples.
Roadmap link: P-2 in `pi-fast-track-plan.md` section 8; depends on FT-A2 (constraint scorer, merged) and
FT-A3 (relevance scorer, planned).

## 0. What exists and what this adds

`evalkit/scorers.py` scores **one extraction**: a case has `messages` (owner text) and `expected`
(problems, figures, constraints, corrections, `hypothesis_only`); `replay.py` turns recorded notes into
records; `score_case` returns recall, precision, figure and constraint fidelity and unsupported causes.
It never sees pi's replies, so it cannot measure repeated questions, redundant questions, or whether a
requirement survives into the summary or the solution. The four scorers below need a **conversation case**:
owner turns and pi turns in order, plus the record as it stood at each pi turn.

Reuse (read, do not copy): `slots.same_question` (exact spelling match, 60% content-word overlap,
cross-language topic words; `MIN_WORDS = 3`), `slots.words`, `reply_gates._questions`,
`reply_gates.known_in_record` (since and how often against the record's `missing` list),
`scorers._stems`, `figure_kept`, `constraint_kept`, `record_text`, `splits` (stable hash split).

**Proposed conversation case** (a new file, for example `evalkit/cases/conversation.json`, not created
here). Same id, industry, language, kind and split rules as extraction cases, plus:

```
turns: [{"role": "owner", "text": "..."}, {"role": "pi", "text": "..."}, ...]
record_after: {"<pi turn index>": [ {title, user_words, summary, money_text, cause, cause_status,
                                   constraints, missing:[since, how_often, ...]} ]}   # what pi had saved
expected: {
  "requirements": [{"id","text","kind": "figure|constraint|fact|correction","sinks": ["record","summary","solution"]}],
  "answered_facts": [{"slot": "since|how_often|count|money|tool|place|who", "by_turn": 2}],   # facts the owner gave
  "legit_reasks": [pi turn indexes where asking again is legitimate]                          # e.g. owner said "?"
}
origin: "reference transcript written by hand, not model output"   # same honesty label as today
```

A real-model run (P-5, separate approval) fills `turns[pi]` and `record_after` from the live path and keeps the
same `expected`; the scorers do not change.

## 1. What a scripted result may and may not claim

- A scripted run proves the **scorer** separates a good transcript from a bad one (negative controls) and
  that the code around the model keeps requirements. It says nothing about how a model behaves.
- Reports say "scripted" in the metric name. Never "AI quality", "creativity of pi", or "pi repeats X%"
  from scripted data. The word "measured" is reserved for a real-model run on labelled cases.
- A cell (language, industry or kind) with fewer than `MIN_CASES = 3` conversations is "not yet measured",
  as today. No threshold is applied before D5 is approved.
- Creativity has **no scripted score at all** (section 5): scripted data can only exercise its
  deterministic restatement flags.

## 2. Scorer 1: repetition

**Definition.** pi says the same thing again without being asked: the same question, the same idea, or the
same opening or closing line, across its own turns.

**Inputs.** pi turns only (plus `expected.legit_reasks`). No record needed.

**Algorithm (deterministic).**
1. Split each pi turn into questions (`reply_gates._questions`) and statements (sentences ending in `.`,
   `!`, `۔`).
2. Question repeat: for each question, compare with every earlier pi question using
   `slots.same_question`. A hit counts unless its turn is in `legit_reasks`.
3. Idea repeat: for statements of 4 or more content words, compare earlier pi statements by the same
   content-word Jaccard (`slots.words`), threshold `SAME = 0.6`. Greeting and disclosure lines are
   excluded (the first pi turn and any line containing "AI").
4. Boilerplate repeat: an identical normalised opening sentence (`slots._spelling`) in 2 or more pi turns.
5. Per conversation: `repeats = questions + ideas + boilerplate`; `repeat_rate = repeats / pi_turns`.
   Per group: total repeats over total pi turns, with n.

**Failure modes.** Paraphrase below 0.6 overlap is missed (under-count); a re-ask after the owner dodged
is a false positive unless labelled `legit_reasks`; very short questions are only caught by exact spelling
(`MIN_WORDS`); the cross-language rule needs 2 shared words, so a Roman Urdu question followed by the same
question in Urdu script is **not** matched (the loan-word rule cannot see script changes).

**Language.** en and roman_ur: full. ar and ur (script): the `words()` tokeniser handles non-Latin tokens
but has no stemmer, so inflected repeats are missed: report as "partial". hi (Devanagari): the word
pattern splits at vowel signs, so only exact-spelling repeats are reliable: "not yet measured" until a
tokeniser is chosen (an open point, not decided here).

**Negative controls.** (a) a transcript where pi asks "Which shop is it?" in turns 2 and 4 with no owner
answer between: must score 1 question repeat. (b) the same two questions but turn 4 is in `legit_reasks`: 0.
(c) two different questions: 0. (d) a transcript with no pi questions: `repeat_rate` 0, not "n/a pass".

**Worked example (en).**
```
owner: Our shop loses orders on WhatsApp, about 30 a week.
pi:    That sounds costly. How often does an order get missed?          <- turn 1
owner: Mostly evenings.
pi:    Thanks. How often do orders get missed?                          <- turn 3: same_question -> repeat
pi:    Mostly evenings is useful: one person cannot watch two phones.   <- statement, new
```
Expected: `questions=1, ideas=0, boilerplate=0, repeat_rate = 1/3` (three pi turns counted).

## 3. Scorer 2: redundant question

**Definition.** pi asks for a fact the owner already gave or the record already holds. Different from
repetition: the earlier ask may never have been made by pi.

**Inputs.** pi questions; owner turns before it; `record_after[turn]` (including each problem's `missing`
list); `expected.answered_facts` (the labelled facts and the turn that gave them).

**Algorithm.**
1. Classify each pi question into a slot with the existing patterns where they exist (`ASK_SINCE`,
   `ASK_OFTEN`) and new small pattern sets for count ("how many", "kitne"), money ("how much", "kitna"),
   tool ("which app or software"), place, and who. A question with no recognised slot is **not scored**
   (counted separately as `unclassified`, never as "not redundant").
2. The slot is filled when any of: (a) `known_in_record` says the record holds it (since, how often);
   (b) the matching figure or tool appears in `record_after` text (`record_text`, `money_text`); (c) the
   label `expected.answered_facts` names the slot with `by_turn` earlier than this question.
3. `redundant = filled slots asked / classified questions`.
4. A question that **names** the known value ("You said evenings; is that every day?") is a confirmation,
   not a redundant ask: detected when the question contains the stored figure or word.

**Failure modes.** Slot patterns are English and Roman Urdu: other languages give `unclassified`, so the
rate is **not comparable across languages** and must be reported with the unclassified count; (c) depends
on hand labels and so is only as good as the labels; a real model may ask a legitimate clarifying form of a
known slot ("since when exactly, the month?"): rule 4 and a human check on a sample guard against that.

**Negative controls.** (a) owner says "this started in March" in turn 1; pi asks "Since when has this
been happening?" in turn 3: flagged. (b) same, but pi asks "You said March; has it got worse?": not
flagged (names the value, and "worse" is not the slot). (c) a question about a slot the owner never
mentioned: not flagged. (d) a question with no slot: `unclassified`, not counted either way.

**Worked example (roman_ur).**
```
owner: Hamari dukaan mein roz 30 orders aate hain, staff sirf 2 hai.
pi:    Samajh gaya. Roz kitne orders aate hain?        <- slot count; answered turn 0 -> redundant
pi:    Aur ye masla kab se hai?                        <- slot since; not in the record -> fine
```
Expected: `classified=2, redundant=1`.

## 4. Scorer 3: requirement preservation

**Definition.** Each requirement the owner stated (figure, limit, fact, correction) is still present
where it matters: the saved record, the summary pi gave, and the solution text (ideas, Solution Box
document, quote draft). It extends `figure_kept`, `constraint_kept` and the correction check from one sink
(the record) to three.

**Inputs.** `expected.requirements` with `sinks`; record text; the summary pi turn; the solution text (the
pi turn or document that carries the ideas).

**Algorithm.** For each requirement and each listed sink: kept = `figure_kept` (figure), `constraint_kept`
(constraint, fact), or for a correction: the right value present and the wrong value absent in that sink
(the same rule as `score_case`). Output per sink: `kept / total`, and the list of lost requirements with
the sink that lost them. The headline number is the **weakest sink**, never the average, so a good record
cannot hide a solution that forgot the budget.

**Hard rule.** A solution that **violates** a confirmed constraint (for example proposes hiring 5 people
when the owner said "only 2 supervisors, cannot hire") is a constraint violation, reported separately and
not averaged away (roadmap rule); detection is a labelled `violated_by` phrase list per requirement in the
case, because a code check cannot judge feasibility.

**Failure modes.** `_stems` keeps 5 letters and has no morphology: an Urdu or Arabic inflection can look
lost (false loss). The Devanagari rule in `constraint_kept` falls back to "must appear as written", so a
paraphrase in Hindi is also "lost". A solution that restates a figure in a different unit ("2 lakh" for
"200,000") is lost: add the labelled `alt` spellings per requirement. The solution sink needs the
document text; where pi sends only a link, the sink is "not available", never "kept".

**Negative controls.** Drop "10 crore" from the summary: that sink fails and the weakest-sink score falls.
Replace "10 nahi, 100" with the old value in the solution: the correction fails. Add a violating idea:
the violation list is non-empty. A solution that contains every figure but also the wrong one fails the
correction check.

**Worked example (en).** Requirements: "budget is 50,000 rupees" (figure, all sinks), "cannot stop
production" (constraint, solution), correction "30 not 20 orders" (record, summary, solution). Record keeps
all three; summary keeps budget and 30; solution mentions 30 and "50,000" but proposes "shut the line for a
week to retrain": `record 3/3, summary 2/3 (constraint not required there: 2/2), solution 2/3,
violation: 1`. Headline = solution 2/3; violation listed.

## 5. Scorer 4: creativity

**Definition.** Among ideas that are **relevant and feasible**, how far they go beyond restating the owner
or handing over the standard checklist for the trade. Creativity never compensates for irrelevance or a
violated constraint: such an idea is not scored (it is a relevance or constraint failure).

**Two layers.**

*Layer A, deterministic restatement flags (scriptable).* Compute for each idea (a) `copy_ratio`: share of
its content words that appear in the owner's own messages, and (b) `pack_ratio`: best content-word overlap
with any stored pack idea of the same industry. Flag `restates_owner` when `copy_ratio >= 0.8`, and
`standard_checklist` when `pack_ratio >= 0.8`. A flagged idea is capped at 0 whatever the grader says (the
grader cannot raise it). These thresholds are starting proposals, to be calibrated on labelled samples,
not on Held-out.

*Layer B, grader judgement (needs a model; not scripted).* Run by the `grader` agent or an equivalent
reviewer model on the transcript, never by the model that wrote the reply (independence rule below).

**Rubric, scale 0 to 2, anchors:**
- **0** restates the owner's words, or is a generic checklist any business would receive ("use social
  media", "hire more staff"), or is flagged by Layer A.
- **1** relevant and specific to this trade and these facts, but conventional: what an experienced
  practitioner would list first.
- **2** relevant, specific, **and** a non-obvious angle the owner did not state and the standard list does
  not contain, and it fits the stated budget, staff and deadline. One concrete next action is named.

Score each idea, then the conversation score is the **mean over ideas that passed relevance and
constraints**, with `n_ideas` reported; a conversation whose ideas all failed those gates has no creativity
score ("not scored"), not 0.

**Prompt contract (exact).** System: "You grade ideas a business assistant gave to a business owner. You
did not write them. Judge only what is written. Do not reward length or enthusiasm." User payload
(JSON): `industry`; `owner_messages` (redacted, as stored); `record` (problems, figures, constraints);
`ideas` (list of `{id, text}`); `pack_ideas` (the stored standard ideas for the industry, titles only).
Required output (JSON only): `{"ideas": [{"id", "relevant": bool, "fits_constraints": bool, "score":
0|1|2, "evidence": "<quote of at most 15 words from the idea>", "why": "<at most 30 words>"}]}`.
Rules in the prompt: a `score` is allowed only when `relevant` and `fits_constraints` are true; if the
judge cannot decide it says `"score": null`. Temperature 0. Each conversation is judged twice with idea
order shuffled; a difference of 1 or more on any idea sends that conversation to a human.

**Independence rule.** The judge is never the model, family or prompt that produced the reply under test
(the live `pi_brain` model is an OpenAI model; the judge must differ and the pairing is recorded in the
report). The judge never sees `expected` or the label sheet. A judge's score is never used for learning
reward until the 85% agreement test (section 7) passes and the owner approves (D-series gate).

**Failure modes.** Judge bias towards longer, fancier text; agreement drift between judge versions
(record the judge model id and prompt hash with every score); non-English ideas judged less reliably
(report per language, not pooled); `pack_ideas` titles are English, so `pack_ratio` is weak outside
English and Roman Urdu: say so in the report; "non-obvious" is partly cultural: Pakistan-market ideas need
labellers who know the market.

**Negative controls (Layer A, scriptable).** An idea copied from the owner's message: flagged, 0. An idea
copied verbatim from the pack: flagged, 0. An idea with no overlap: not flagged (and Layer B decides). A
**scripted** transcript with a hand-written "creative" idea gets **no** creativity score: the report prints
"creativity: needs grader and human calibration" for scripted runs.

**Worked example (en, bakery).** Owner: "We lose cake orders on WhatsApp; two staff; no budget for
software." Ideas: (1) "Reply to WhatsApp orders faster" (copy_ratio high: 0). (2) "Keep a paper order
sheet taped by the oven with a tick for each stage" (relevant, fits, conventional: 1). (3) "Print a QR on
every box that opens a pre-filled WhatsApp message with the cake size and date fields, so orders arrive
complete; costs one print run" (relevant, no software, non-obvious, one action: 2). Mean 1.0 over three
scored ideas. If (3) had said "buy an order-management app" it would fail `fits_constraints` and drop out.

## 6. Scripted tests that lane E would write (when approved)

1. Each scorer: the controls above as tests, each seen failing first.
2. A mutation test per scorer: take a good transcript, apply one mutation (insert a repeat, remove a
   figure), assert the score moves in the right direction.
3. Language smoke tests: one case each in en, roman_ur, ur, ar, hi that states which cells are partial or
   "not yet measured" (the scorer returns `measured: False` rather than 0).
4. The report prints counts with every rate and refuses a rate for a cell below `MIN_CASES`.
5. No existing score changes: the 132 extraction cases score byte-identically.

## 7. Human-labelling method for the 85% agreement threshold (PROPOSAL)

**What is compared.** For creativity, the grader's 0, 1, 2 score per idea against the human consensus
score. The same procedure is proposed for the three deterministic scorers as a sanity check, but only
creativity needs the 85% gate (the others are code and are checked by controls). Primary statistic:
**exact agreement** on the 3-point scale; secondary: agreement within one point, and **weighted Cohen's
kappa** (linear weights) to correct for chance. Both are reported; the 85% proposal applies to exact
agreement on the **relevant and constraint-passing** ideas.

**Sample size, with the reason.** The brief says at least 20. Twenty is too few to prove 85%: with 20 of 20
agreeing, the 95% Wilson lower bound is only about 84%; with 17 of 20 (85%) the interval is about 64% to
95%. With **60 ideas**, 54 of 60 (90%) gives about 80% to 95%, and 60 of 60 gives a lower bound of about
94%. **Proposal: 60 ideas** (from about 30 conversations, 2 ideas each), with a **first-pass pilot of
20** to debug the sheet and the rubric before the full 60. The owner may choose a different size; the
trade-off is stated, not hidden. State the interval with every agreement figure.

**Balance.** At least 10 ideas per language for en, roman_ur, ur, ar, hi (50), plus 10 spread over the
industries with the most conversations. At least 5 distinct industries; no industry more than 8 ideas;
about one third of ideas deliberately weak (restating, generic) so all three scores are used. A language
with fewer than 10 labelled ideas is reported "not yet measured", never "passing". Samples are drawn from
**Development** conversations only; Held-out is untouched.

**Who labels (owner decides).** Proposal: two independent human labellers, at least one native or
fluent in the language and one who knows the Pakistan small-business market; neither wrote the case nor
sees the judge's score. The owner (or a person the owner names) adjudicates disagreements. If humans are
not available for ur, ar or hi, those languages stay "not yet measured": an AI-only label is not human
truth.

**Procedure.** (1) Labellers get the rubric (section 5) and 6 shared practice ideas, then label
independently on the sheet. (2) Compute labeller-to-labeller agreement first; if it is itself below 80%,
the rubric is the problem and is revised before anything is said about the judge. (3) Disagreements are
adjudicated into one **consensus label**; the sheet keeps all three. (4) The judge scores the same ideas
blind. (5) Agreement of judge with consensus is computed overall and per language.

**Label sheet (one row per idea).** `case_id`, `language`, `industry`, `idea_id`, `idea_text`,
`relevant` (y/n), `fits_constraints` (y/n/unclear), `score_a` (0-2), `score_b` (0-2), `note_a`, `note_b`,
`consensus` (0-2 or `not_scored`), `adjudicator`, `judge_score`, `judge_model_id`, `judge_prompt_hash`.
Stored as a CSV or JSON file in the docs folder; no real customer text (cases are written text).

**Computation.** `exact = matches / n`; `within_one = |diff| <= 1 / n`; weighted kappa from the 3x3 table;
95% Wilson interval for `exact`. Reported per language and overall, with n.

**If agreement is below 85%.** The judge is **not** used for any decision, dashboard or reward. In order:
(a) check labeller agreement; (b) read the disagreements and tighten the anchors or the prompt, never the
threshold; (c) re-run on a **fresh** sample of the same size (the first sample is now used up for tuning);
(d) try a different judge model, recorded; (e) if it still fails, creativity stays a human-only review and
the roadmap says so. The threshold itself changes only by the owner, and the change is logged.

**Status of the 85%.** Proposal, not an approved gate. It becomes a gate only after the owner reviews this
method and the labelled sample.

## 8. Dependencies, open decisions and limits

**Dependencies.** FT-A2 (merged: constraint scorer), FT-A3 (relevance scorer, which also needs its own 85%
check against hand labels), D5 (thresholds and per-cell minimums, still pending), the conversation case
format (this document proposes it; lane E builds it only after approval), a named pair of human labellers.
P-5 (real-model stages) is needed before any of these can speak about a model.

**Decisions for the owner.** (1) Approve the conversation case format. (2) Choose the sample size (60 with
a pilot of 20 proposed). (3) Name the labellers and the adjudicator. (4) Confirm that the 85% applies to
exact agreement on the 3-point scale (a stricter reading than "within one point"). (5) Approve a judge
model other than the producer's, with its price, before any judge run (no spending is authorised now).
(6) Hindi tokenisation approach for repetition and preservation. (7) Whether wants and "tried" items count
as requirements in `expected.requirements` once P-1 fixes the schema.

**Limits of this document.** It is a design: nothing here was run. The worked examples are written by
hand to show the arithmetic, not taken from a model. Thresholds `0.8`, `SAME = 0.6` and the sample sizes
are proposals to be calibrated on Development and then confirmed once. The intervals are normal
Wilson-interval arithmetic computed by hand for the figures quoted. The deterministic scorers read
patterns the code already has; their language coverage (en and roman_ur strong, ur and ar partial, hi weak)
is read from the code, not measured.
