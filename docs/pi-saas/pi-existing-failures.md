# pi: failures that exist on origin/main (0643c2f1), traced 2026-10-31

Run on the disposable database (127.0.0.1:55432/owner_industry_test) from the worktree
`.cache/lanes/stale` (branch `pi/fix-stale-tests`). Production code was not changed. Test-only
fixes are in the same branch; this page lists what is left and why.

## Production bugs (not fixed here)

Two integration tests in `test_pi_open_items_and_map_chat.py` are marked `xfail(strict=True)` with a
pointer to this page. When the fix lands the strict marker turns the test red until the marker is
removed, so nobody forgets it.

### 1. `map_edit.STRONG_LINK` holds backspace characters, so "this connection is wrong" does nothing

- Test: `tests/integration/test_pi_open_items_and_map_chat.py::test_a_wrong_link_is_removed_and_pi_asks_the_real_connection`
  (assertion at the old line 215: `assert 'suggested' == 'rejected'`).
- File: `apps/api/app/modules/pi/map_edit.py:64`. Introduced in `c41ab202`.
- Root cause: the pattern was written through a Git Bash heredoc, which rewrote `\b` into the
  control character 0x08 (the trap CLAUDE.md warns about). The line reads
  `r"<BS>(?:jor+|jarr|jarh|taalluq|taaluq|rishta|arrow|connection)<BS>|جوڑ|الرابط|الربط"`.
  `STRONG_LINK.search("this connection is wrong")` is False (debug run). `_unlink` therefore returns
  `Edit("unlink", "nothing")` when the message names no problem ("nothing drawn, or a web link"), the
  link stays `suggested`, and the model's own reply goes out. Verified: with the message
  `wants()` == "unlink", two confirmed problems and one drawn link, `_unlink` still returned nothing.
  Every owner who says "this connection is wrong" without naming P1/P2 is affected, in English and
  Roman Urdu ("ye jorr galat hai"). Only the Arabic alternatives work.
- Smallest fix: replace the two 0x08 bytes in that line with `\b`. Risk: none.
- Same defect, found on the way (`grep -P "\x08"` over `app` and `tests`):
  - `apps/api/app/modules/pi/idea_filter.py:197-198` and `:202` (three `re.compile` patterns:
    `\b(?:search...|google)\b` and `\b(?:search|online|google|listing|...)\b` read as `<BS>...<BS>`;
    introduced in `57f52dff`). The words only match next to a backspace, so these idea-filter
    patterns never match. Fix: same replacement. Check the unit tests around them afterwards, a
    pattern that starts matching can change a verdict.
  - `apps/api/tests/unit/test_pi_blueprint_adversarial.py:230`:
    `rf"\b{word}\b"` has the same corruption, so `assert not re.search(...)` is always true. Not a
    production bug, but that assertion proves nothing today.
  - Suggested guard: a unit test that fails when any `.py` file under `app` or `tests` contains
    0x08.

### 2. The map edit "which problem do you mean, for example P2?" is rejected by the no-price guard

- Test: `test_pi_open_items_and_map_chat.py::test_when_it_cannot_tell_which_problem_pi_asks_one_question`
  (old line 270: `reply.count("?") == 1` but the reply was `Thanks, I've got that.`).
- Files: `apps/api/app/modules/pi/map_edit.py` (`LINES["which_problem"]`, `LINES["which_link"]`, the
  examples "P2" and "P1 and P2"), `apps/api/app/modules/pi/service_conversation.py:1394`
  `validate_service_reply`, `apps/api/app/modules/pi/runtime.py:1711` and `:1815-1831`.
- Root cause: `note_problems` replaces `turn.reply` with the map-edit line after the reply was
  checked, and that line is not added to `context["fixed_lines"]` (the list `allowed_text` trusts).
  At step 8 of `runtime.process_pi_event` `validate_service_reply(reply, ..., mode="quote")` refuses
  any digit when the price mode is `quote`, `ask_team` or `hidden` (default for a service tenant:
  `price_policy.price_mode`). The "2" in "P2" trips it (checked directly:
  `validate_service_reply("... for example P2?", 4000, "quote", [])` raises `SERVICE_PRICE_BLOCKED`,
  mode `exact` passes). The draft counts as rejected, `ask_team` raises a staff request
  ("A generated reply failed validation ... (reply_rejected)") and the owner gets the canned
  `BRAIN_ACK_NOTICES` "Thanks, I've got that." with no question: a dead end, and a pointless team
  ticket. Agent run `error_code` = `SERVICE_PRICE_BLOCKED`.
  Applies to "which link" and "which problem" in every language.
- Smallest fix: in `note_problems`, when `map_edit.apply` returned an edit whose `line` is in the
  reply, append that line to `context["fixed_lines"]` (like the other fixed lines at
  `service_conversation.py:3466`), or change the examples to words ("for example the first one").
  Risk: low; the first keeps the "P2" the owner can type back.
- After fixes 1 and 2, remove both `xfail` marks and rerun the file; the first test's later steps
  (reasons count, second "wrong link" falls to the model) have not been exercised on fixed code.

## Environmental (not a code or test bug)

### 3. The nine integration-workflow and integrations-API tests

- Tests: `test_integration_workflows.py` (3 `routes_to_provider_once`, 4 `timeout_retries...`) and
  `test_integrations_api.py::test_outbox_delivery_signing_retry_dead_letter_and_manual_retry`,
  `::test_private_redirect_target_is_never_followed`.
- Not Redis: the fixture (`test_integrations_api.env`) uses an in-process `CaptureQueue` and the
  comment says "No Redis locally". Redis is not listening here and the tests still pass below.
- Cause: the disposable database holds 865 old `pending` rows in `outbox_events`, left by earlier
  runs (other tenants, other days). `outbox.dispatch_pending` (`app/integrations/outbox.py:110`)
  takes the oldest `outbox_batch_size` (default 100) pending events across ALL tenants, so the
  event the test just created is never reached, no operation or delivery row appears
  (`assert 0 == 1`, `IndexError`, `delivery is None`). Debug run: 865 events, the test's two
  `customer.created` events last, workflow `enabled_at` correct, status `pending`.
- How to run them: `OUTBOX_BATCH_SIZE=1000` (the setting's maximum, `app/core/config.py:168`) in the
  environment: both files, 39 passed. Better: a fresh `owner_industry_test` database, or
  `UPDATE outbox_events SET status='dispatched' WHERE status='pending'` on the disposable database
  only (not done here, other lanes share it). A test-isolation fix (mark the polluting rows, or give
  the fixture its own batch size) belongs to whoever owns the integrations tests.

## Fixed as stale tests (for the record)

| Test | Why it was stale |
|---|---|
| `test_pi_brain_problems::test_merge_split_link_withdraw_and_rename_a_group` | link floor 60 to 75 in `c41ab202`; the op carried the 0.6 default |
| `test_pi_brain_decisions::test_the_summary_then_the_fixed_offer_with_buttons`, `test_pi_simulate_kiryana`, `test_pi_map_chat_triggers::..._offers_question_stays_last`, `test_pi_solution_ask_flow` (2) | the box-on offer is `solution_ask.box_offer_line`, the tests pinned the legacy text; now one helper `tests/integration/offer_expect.py` |
| `test_pi_simulate_kiryana` | ordered replies by `created_at` (transaction start, not an order); now `pi.reply_to(mid)`; no longer writes into another session's scratchpad |
| `test_pi_solution_gaps_db::test_g5_promotion...` | unordered `.first()` could pick a `testing` arm; now `status == "active"` and `order_by(arm_key)` |
| `test_pi_open_items_and_map_chat` (the first, "named first on return") | split the reply on "Which", which the next-question logic no longer writes; now checks the quoted words and one question last |
| `test_pi_pipeline_gap_flows` (2) | the file imported `roomy_limits` but not the autouse `the_offer_is_open` fixture, so after `c41ab202` (legacy offer only on R1) the journey never reached S6 |
| `test_pi_rare_handoff::test_a_sticker_is_skipped_quietly` | spec 6.10: a sticker alone is resolved by `message_signals` before any conversation exists |
| `test_pi_spec_in_prompt` | R-SELL-01 is superseded (`28dc4fb5`); the handbook carries R-SELL-03 |
