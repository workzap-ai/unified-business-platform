# pi-saas: problem-solving flow, open issues (pi/ps-flow)

Written on branch `pi/ps-flow` (single writer). Everything here is observed on the integrated tip, not
inferred. File:line refer to `apps/api/app/modules/pi/` at the commit that introduced this note.
Nothing below is fixed by weakening the L2-1 gate: unknown stays unknown and is never approved.

## Open L2-1 issues (owner of `pi/l2-hard-gate`)

### L2-1-a. "we cannot promise delivery days" is read as an avoid-topic limit on "delivery"

- Input limit: `we cannot promise delivery days`
- Input idea: `Message each buyer when the parcel leaves with the courier tracking line.`
- Observed: `violates`, rule `cannot_change`, evidence `('courier',)`, reason "the option involves
  delivery, which the owner said they cannot (we cannot promise delivery days)".
- Expected: not `violates` (the idea does not promise a delivery day). `ok`, or `unknown` at worst.
- Where: `constraint_check.py:1022-1024` (`lex.topic_limit` turns the limit into `_Lim("topic",
  verb="delivery")`, the verb "promise" is dropped) and `constraint_check.py:1179`
  (`_hits_in(... lex.topic_hits ...)` rejects any idea that mentions the topic).
- Effect: a relevant idea is removed from the owner's chat (2 of 82 relevant Development ideas).
- Test (xfail, exact input): `tests/unit/test_pi_flow_courier_regression.py::
  test_idea_that_only_mentions_the_courier_is_not_rejected_by_a_promise_limit`.

### L2-1-b. "Use a new courier." passes against "we cannot change courier"

- Input limit: `we cannot change courier because of the contract` (also plain `we cannot change courier`)
- Input idea: `Use a new courier.`
- Observed: `ok`, rule `cannot_change`, reason "1 stated limit(s) read and none broken".
- Expected: `violates` (it changes the courier). `Switch to a faster courier company for every order.`
  and `Change the courier.` are correctly `violates` after the small clause fix on this branch.
- Where: `constraint_check.py:1203` widens a CHANGE limit to the families RAISE, CUT and BUY only; the
  verb "use" belongs to none, so the family test at `constraint_check.py:1296` never fires.
- Test: add `Use a new courier.` to `tests/unit/test_pi_flow_courier_regression.py` when fixed.

### L2-1-c. Urdu and Arabic option verbs are not read

- Input limit: `لا نستطيع توظيف أحد` (we cannot hire anyone); idea `توظيف موظف جديد`.
- Observed: `unknown`, reason "the option is not in a script this check can read".
- Expected: `violates`.
- Where: `constraint_check.py:1117` (`_check_cannot` returns unknown when `not option.latin`).
- Effect on the flow (handled here, not by weakening the gate): an unknown idea is shown labelled "not
  yet checked", is ranked after any idea the gate cleared, is never read as clear, and the one
  question that would settle it is asked (PS-5). `pi/l2-hard-gate` is extending the reading to Urdu,
  Arabic and Hindi; merge it when it lands and re-run `test_pi_ps_flow_scenarios.py`.

### L2-1-d. Staff caps are documented as not enforced by the gate

- Module docstring of `constraint_check.py` ("Staff limits ... not enforced"); round 2 (04f8bf14)
  says staff limits are enforced. Verify through a journey before relying on it.

## Open items in this branch

- Spec text on bare agreement. `docs/pi-saas/spec-text/pi-platform-spec-1.txt:1323-1325` and
  `pi-platform-spec-v1.6-2026-10-30.txt:1832` (ROFFER03): "Ok", "hmm", "maybe", "let me think" are
  not yes; "yes/haan/ji/theek hai/okay go ahead/sure" is yes. The same files list "ok" in the
  multilingual yes classifier (`pi-platform-spec-1.txt:3017`, v1.6 `:3666`), which contradicts ROFFER03
  for "ok". `decisions.py:31-33` counts "theek hai" and its Urdu and Arabic equivalents as yes, which
  agrees with ROFFER03; nothing was changed. The owner decides whether "ok" stays out of `YES_WORDS`.
- Cause withdrawal ("I take that back") has no mechanism in `problem_fields.merge_cause`.
- A Roman Urdu failed-attempt outcome such as "mix ho gaye" is not read as a failure (Level 1 reader).
- `blueprint_text.money_in` flags the Urdu phrase "بغیر فیس والے" (without fee) as a price claim (L2-3).
- Arabic owner causes: `problem_fields.said_by_owner` matches whole words, so a word with an attached
  conjunction ("والمصففين" against "المصففين") keeps the cause `pi_inferred` (safe direction).
- The no-idea fallback line has no Urdu-script key in `language.BRAIN_ACK_NOTICES`.
- The PS-6 journey suite (`pi/ps6-scenario-suite` 9c3def8b) was merged and reverted on this branch: its
  tests call `option_wiring.gate_ideas` and `blueprint_doc`, both removed when PS-3 and PS-4 landed
  (one verdict path in `option_voice.voice`, one blueprint in `blueprint_wire.build`). It needs to be
  ported to those two entry points before it can run here.
