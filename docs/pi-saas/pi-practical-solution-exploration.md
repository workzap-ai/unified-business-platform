# Practical digital solution exploration

The November 2026 upgrade allows a customer to explore a digital workflow before
authorising a solution document, quote or implementation. This deliberately supersedes
the earlier manual-ideas-only/how-to restrictions for an explicit solution request.
The existing discovery, document, payment, safety and account-manager flows remain.

## Confirmed failure paths

- `decisions.cost_asked` treated an expense/data-entry description as a pricing request.
- Current listening/map/box states were absent from `solution_ask.ASKABLE`.
- Manual idea selection and `brain_option_voice` could replace a solution explanation
  with a summary, generic scope/count question or document offer.
- The normal word cap truncated a practical workflow during constitution repair.
- Self-review's proposal fallback was the exact repeated "only a suggestion" message.
  Repeat filtering could also restore the original when no new text remained.
- Listening's answered-question check included preceding declarative sentences, so
  restating known records in a workflow could be mistaken for asking about them again.

## Implementation

`practical_solution.py` recognises workflow and implementation requests using the
existing solution intent recognition and multilingual semantic fallback. It selects
an exploration mode inside the existing structured reply pipeline. It is not a new
agent, product catalogue or set of industry-specific answers.

The reply receives the latest customer turn, scoped problem records and relationships
(including their status/evidence), existing requirements, history and approved knowledge.
Its prompt asks the model to reason from those facts to a suitable digital workflow,
explain relevant daily roles and information movement, respect corrections and constraints,
and ask at most one unanswered workflow question. Unknown sizing does not force discovery
to restart. Initial data entry and ongoing entry are distinguished; team responsibility,
imports, prices and compliance are never invented.

Legacy summary/idea/option renderers cannot overwrite an exploration reply. The mode has
a 240-word ceiling and retains shared safety, honesty, privacy and language validation.
Self-review gets one contextual repair attempt rather than immediately substituting a
fixed disclaimer. A still-invalid or repeated exploration response is rejected through
the existing rejection path, not sent as a successful solution.

`conversation_stage` and `solution_question_pending` persist continuation in the existing
brief. Commercial state and map confirmation are retained. Explanation always clears
action, quote approval, meeting and consent changes. No schema migration is needed.
"Kuch reh gaya" asks for missing information rather than forcing a summary or offer.
Explicit manual-only requests retain the legacy idea path.

## Verification and limits

`test_pi_practical_workflow.py` has 52 deterministic tests using the real composition
and guard pipeline with scripted model responses, including the furniture repeat,
pharmacy expenses/data entry, travel, unfamiliar robot repair, Arabic composition,
five-language semantic routing, current states, safety and non-authorisation.
These verify routing and preservation, not real-model reasoning quality. Live WhatsApp
replay and real-model multilingual acceptance remain necessary after deployment.

The final targeted regression run selected 46 PI unit-test files covering solution,
expert, constitution, pricing, language, review and discovery behaviour: **3,600 passed**
in 41.60 seconds, with four existing asyncio-mark warnings in `test_pi_expert_merge.py`.
Unit tests used explicit localhost test database variables and no live database/model.

Changed Python files pass Ruff formatting and lint. Full application mypy reports the
same nine errors on this branch and untouched main `eb0896c4`: `safety_scope.py`,
`problems.py`, `resolution_flow.py`, and two existing assignments in
`service_conversation.py`. Full backend formatting also reports the same 19 untouched
files on both checkouts, using the locked Ruff 0.16.8 and mypy 1.20.2 versions.
Those unrelated baseline issues are not changed by this patch.
