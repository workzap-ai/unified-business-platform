# pi problem-solving trace: one business problem, first message to final solution (PS-0)

Read-only inspection of `origin/main` c73cf4f (worktree `ps0`, 2026-10-31). Paths are under
`apps/api/app/modules/pi/`; `sc` = `service_conversation.py`. Line numbers were read in this tree.
"Code" means a function that decides or refuses; "prompt" means the model is asked and nothing checks.
Not verified: anything not listed with a line; runtime behaviour with a real model (nothing here ran a model).

## 1. Stages

| Stage | What happens (evidence) | Code-enforced | Prompt-only |
|---|---|---|---|
| Understand | The reply model may emit problem ops; if it wrote none, a second short model call fills the gap: `sc:6001-6012` -> `problem_extract.extract` (`problem_extract.py:113`), gated by `wants_extraction` (`:85-111`: brain mode, listening states, at least MIN_WORDS). Ops saved by `note_problems` (`sc:3535-3628`, called `sc:6494`) -> `ProblemBook.apply_ops` (`problems.py`). State moves by `flow.after_turn` (`flow.py:326-347`), applied in `advance_flow` (`sc:3630`). | Caps (`MAX_NOTES`), known-title filter (`problem_extract.py:149-155`), redaction, state legality (`flow.py` TRANSITIONS), one-question and last-sentence linter | Which question to ask next; what counts as a problem; the extractor's field list (`sc:944` area) |
| Diagnose | `brain_expert_diagnosis` (`sc:3006`) works out likely causes and one missing fact for the main problem, caches them on `conversation.service_brief` (not on the problem row). Pipeline `expert_advisor._pipeline` (`expert_advisor.py:657`), `vet` (`:468`). | `question_ok` form check (`:432`: one sentence, one `?`, no solution word, no 3-digit number); `same_question` repeat check (`:915`); a cause pi guessed cannot be stored as `confirmed` without owner words (`problems.py:552-564`, `problem_fields.merge_cause`) | The causes themselves and which fact is "most uncertain" (model + judge model, `expert_advisor.py:613`) |
| Solve (ideas) | Asked for a fix, pi gives free ideas: `brain_expert_ideas` (`sc:2762`), `brain_free_ideas` (`sc:2855`), pack ideas (`solution_ideas.py:339 choose`). | Cap 2 per message, 2 per problem, 8 before offer, about 25 words (`value_line.py:11-17`); idea filter G1-G8 `idea_filter.failures` (`idea_filter.py:316`: goal conflict `:163`, invented context `:217`, wrong subtype `:230`, cause misfit `:249`, repeats `:261`, off the map `:272`); `brain_no_repeat` (`sc:2504`); `brain_no_ideas`, `brain_howto` (`sc:3107`, `:3155`) | Whether an idea is useful for this owner (the filter checks form and a few mismatches, not fit to constraints or things already tried) |
| Recommend (offer) | Offer is made once for the whole set by `brain_offer` (`sc:3280`) when `box_offer_allowed` (`sc:3252`) -> `box.can_offer` (`box.py:43-83`: R1-R3, else B1-B7 plus main cause known, not just corrected, not in a hurry). `main_cause_known` is `box_signals.py:100-118`. | Entire offer gate; the model never writes the offer | Wording of the free ideas before the offer |
| Blueprint | `brain_docs.draft_offer` (`brain_docs.py:601`) builds a Solution Box draft (catalogue keys, 2 ideas per problem, `check_box_draft` `:418`) and a quote skeleton. Problem facts sent to the model: ref, title, category, subtype, their words, where, impact types, owner cause (`brain_docs.py:626-639`, `:657-660`); `box_doc.problem_view` (`box_doc.py:40-64`) adds how often, since, money, rank. | Closed catalogue, `MONEY_IN_TEXT` (`brain_docs.py:60`), no price or promise (`check_content` `:286`), refs must name a known problem | Section prose |
| Approval | Yes gate `decisions.decide` (`decisions.py:459`); "ok/hmm/maybe" is not yes. Reviewer approval `brain_docs.approve` (`brain_docs.py:992`) refused while `blockers` (`:924`) is non-empty (total, currency, valid-until, bank account, included and not-included lists). | Yes gate, reviewer gate, expiry (`decisions.py:754`), no payment in chat | none found |
| Execute / verify | Payment confirmed by staff, then `brain_payments.py:148` moves to S12_KICKOFF; kickoff call moves to S13_IN_BUILD (`brain_followups.py:481`); follow-ups in `brain_followups.py`, `followup_policy.py:134`. | State legality, staff-confirmed payment | Everything after S13: no step list, no success criterion, no check that the stated outcome happened (`pi-controlled-execution-design.md` is a design; not built) |

## 2. Stored facts: where written, where consumed

| Fact | Written | Consumed |
|---|---|---|
| `since` | `problems.py:632`, `:724` from `note.since_text` (extractor has `since_text`, `problem_extract.py:67`) | Missing-list for asking (`problems.py:1025-1028`); `box_doc.py:54`; `brain_docs.py:448-449`; `map_builder.py:93` |
| `impact` (types, money, time, people) | `problems.py:636`, `:726-736`; extractor `money_text`, `impact_types` | `problems.py:476` (severity); `brain_docs.py:638`; `box_doc.py:55-56`; missing-list `:1022-1024` |
| `cause` column (`status`, text, evidence) | `problems.py:532-545` via `requirement_values` (`:505`) only when the note carries `cause_text`; `person_believes_cause` is a separate older field (`problems.py:543-545`, `:650`, `:748`) | Only `person_believes_cause` is read: `problems.py:1049` -> `idea_filter.context_from` cause (`idea_filter.py:339-395`), `box_signals.py:100-118`, `brain_docs.py:660`. The `cause` JSON column: written but never consumed |
| `constraints`, `tried`, `expected_outcome` columns | `problems.py:516-549` only when the note has budget/staff/deadline/cannot_change/tried/outcome | Never consumed (no read outside `problems.py` and the new blueprint branch). Not in any model payload, filter, offer gate or document |
| Writer reachability | `SimpleNote` has none of these fields (`problem_extract.py:51-68`), so the extractor cannot write them. The reply model's `ProblemNote` has them (`problems.py:100-118`) but no prompt line asks for them (`sc` mentions budget only as "never push", `sc:693`) | `note_problems` calls `apply_ops` without `owner_text` (`sc:3548-3558`), but `requirement_values` needs it (`problems.py:538`), so `owner_said` is unreachable (board line 82 agrees) |

## 3. Top 8 places pi acts like a generic chatbot

Hot files (board lines 26-30): `service_conversation.py`, `problems.py`, `decisions.py`, `brain_docs.py`,
`box_doc.py`, `idea_filter.py`, `expert_advisor.py`, `flow.py`, `runtime.py`, `part19.py`: owned by FT-02
(`pi/s-ft02-eighth-draft`) until merged; wiring waits for it, one agent at a time. Not hot: `problem_extract.py`,
`problem_fields.py`, `box.py`, evalkit (lane E).

1. **The extractor cannot capture constraints, things tried, a stated cause or the wanted outcome.**
   Evidence `problem_extract.py:51-68`. Owner says "only 2 staff, tried a register, cannot stop work" and nothing
   is stored. Smallest fix: add `budget, staff, deadline, cannot_change, tried, cause_text, cause_said, cause_words,
   expected_outcome` to `SimpleNote` and map them in `to_note`. File not hot (B2b); owner: B2b lane, merge after FT-02
   because the call site is hot.
2. **Owner message is not passed when saving, so a cause the owner stated is never `owner_said`.**
   Evidence `sc:3548-3558` vs `problems.py:538`. Fix: pass `owner_text=message.body` to `apply_ops`. Hot: FT-02.
3. **Ideas ignore stored limits and past attempts.** `idea_filter.context_from` (`:339`) reads subtype, goal verb and
   cause only; no constraint or tried list reaches `failures` (`:316`). A "hire two people" idea passes for an owner who
   said they cannot hire. Fix: L2-4 (`pi-execution-board.md:66`): feed constraints and tried into `IdeaContext`, reject
   on conflict. Hot: FT-02 (`idea_filter.py`).
4. **Documents are written without the owner's limits or wanted outcome.** Payload `brain_docs.py:626-639` and
   `box_doc.py:40-64` omit constraints, tried, expected_outcome. Fix: add them to both and to `check_box_draft`
   (L2-wire, board line 67). Hot: FT-02 (`brain_docs.py`, `box_doc.py`).
5. **Diagnosis is a cache on the chat, not part of the problem.** Causes and the open question live in
   `service_brief` (`sc:3006` docstring) while the problem row stores only the owner's belief; "cause known" for the
   offer is true as soon as any cause text exists (`box_signals.py:100-118`) with no check of status or evidence.
   Fix: store diagnosis hypotheses with status `pi_inferred` on the `cause` column and have `main_cause_known` read the
   status. Hot: FT-02 (`sc`, `problems.py`); `box_signals.py` is named under GAP-1/2 in board line 69.
6. **Corrections work only for digits.** `figure_fix_for` (`sc:3513-3534`) returns nothing unless the message has
   digits, so "dus nahi, sau" or Urdu/Arabic number words do not fix a figure (board GAP-1). Fix: number-word table in
   `figure_correction` (not verified whether that module is hot) plus the existing call. Wiring hot: FT-02.
7. **What to ask next is chosen by the model; code only checks the form.** The missing list
   (`problems.py:1015-1030`) holds where, how_often, impact, since; it has no constraints, tried or outcome, so nothing
   makes pi ask "what have you tried?" or "what result do you want?", and `question_ok` (`expert_advisor.py:432`) does
   not check a question against known facts (only against earlier questions, `:915`). Fix: extend the missing list and
   reject a question whose slot is already stored. Hot: FT-02.
8. **The plan has no steps, dependencies or success criteria, and nothing checks the result.** Box content is
   catalogue keys and two ideas per problem (`brain_docs.py:418-436`); after S13 only follow-ups run
   (`brain_followups.py:481`). `blueprint_models.py` and `blueprint_rules.py` exist only on `pi/l2-options-record`
   (lane l23, not on main, not wired). Fix: after FT-02, wire the typed options record into document drafting
   (L2-wire) and add success criteria to the quote content; execution check waits for the Q-8 design. Hot: FT-02;
   new blueprint modules owned by `pi/l2-options-record`.

## 4. Limits of this trace

- No model was run; "prompt-only" is read from code and prompt text, not observed.
- `sc` is 7768 lines; stages were traced through the functions above, not every guard in it.
- `runtime.py` and `part19.py` were not traced line by line (not verified).
