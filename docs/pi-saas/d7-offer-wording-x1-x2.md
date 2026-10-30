# D7: offer wording and placement (X1) and never-offer conditions (X2): comparison for review

**Status: PROPOSAL, nothing changed, nothing decided.** Written 2026-10-30 from `origin/main` `cc462c5`.
"X1" and "X2" are the first two of the seven code-versus-spec contradictions in the platform-spec audit
(X1: offer wording and placement; X2: never-offer conditions, R3 and "no other problems" never set). They are
not the X1-X5 edge-case rule ids in `rule_index.json` (those are emergencies).

## 1. What the specs say

| source | rule |
|---|---|
| platform spec (first edition) §3.8 ROFFER02 | one message, one question: "Would you like a solution document and a quote for these? You can say no." optional line: "The document sets out what Workzap would build, in plain words. The quote says what it would cost and how long. It's an offer, not a charge." |
| same, ROFFER03/04 | nothing prepared without an explicit yes; "ok", "hmm", "maybe" are not yes; if unclear ask once "Shall I go ahead and ask Workzap to prepare them?"; with 2+ groups ask "Should it cover all of these, or only some?" |
| v1.5 Book 5 §5.4 and §10.9 (pp. 171-172, 189) | **the offer is one Solution Box for the whole set**; offered only under R1 (owner asks for document, quote, price), R2 (yes), R3 (who, how long, can Workzap), or B1-B7; never when the cause of the main problem is unknown, the map was not seen, the owner is upset or just corrected pi, a decline is recent. Wording rotates, e.g. "Ab tak aap ne chaar masle bataye ... In sab ko ek Solution Box mein, aap ki tarteeb se, likh dein, aur Workzap ki taraf se ek quote ban jaye? Abhi nahi chahiye to bhi theek hai." |
| v1.5 Part 18.3 (p. 218) | canOffer is a hard block at send time; "these" must point to the map or the box, never to free ideas; never in the same turn as the first map; **"You can say no" is removed**; falling trust blocks for 8 messages. The Part 14 removal table lists "You can say no" attached to an offer. |

Part 18.3 and Book 5 supersede the first edition's ROFFER02 sentence "You can say no".

## 2. What the code does today (verified in the worktree, `cc462c5`)

Three offer texts exist, chosen by the per-workspace flag `response_rules.brain.box_offer` (exactly `true`,
brain mode only; `box.py:85-90`):

| path | box_offer off (default) | box_offer on |
|---|---|---|
| owner accepts the summary (`decisions.py:~545-565`) | `decisions.TEXT["offer"]`, "Would you like a solution document and a quote for these? The document sets out ... It's an offer, not a charge." Allowed **only** when the owner asked for the document or quote in that message (R1); otherwise `R1-blocked` and no offer | `solution_ask.box_offer_line` (Solution Box wording), only if `box.can_offer` allows (R1-R3 or B1-B7) |
| after free ideas, how-to, R3 (`service_conversation.py:3280-3310`) | `solution_ask.OFFER_AFTER`, "Shall I get one solution document and a quote made for all of these together?" via `fixed_lines`, R1 only | Solution Box wording, gated by `can_offer` |

Box wording (`solution_ask.py:438-441`), English, when the chat has fewer than 3 noted problems (variant "C"):
"It's fine if you don't want this yet, and new problems can keep joining the same box. Shall I write all of
this into one Solution Box and have Workzap prepare a quote?" Variants "A" (3+ problems: "So far you've told me
about {n} problems ...") and "B" (map reviewed: "The map looks quite complete now. Shall I start writing it up,
or is there anything else to look at alongside it?") rotate by message id. The question is kept as the last
sentence (CLAUDE.md: one question per message), so the soft decline comes before it, which differs from the
spec's example order. Roman Urdu has A, B, C; Urdu, Arabic, French, Persian, Spanish have C only, marked for
native review. Buttons (`decisions.OFFER_BUTTONS`): "Yes, please / No thanks / Not now" (and Roman Urdu, Arabic).

## 3. The open decision, side by side

| | X1-a: Solution Box wording when `box_offer` is on, legacy line otherwise (**current code**) | X1-b: Solution Box wording everywhere | X1-c: legacy document-and-quote line only |
|---|---|---|---|
| spec fit | Book 5 and 18.3 where on; first-edition wording where off | Book 5, 18.3 | first edition ROFFER02 minus "You can say no"; contradicts Book 5 "the offer is the Solution Box" |
| "You can say no" | absent in both | absent | absent (already removed) |
| gating | box on: R1-R3/B1-B7; off: R1 only | R1-R3/B1-B7 for all workspaces; needs the readiness data (map reviewed, ranking) to exist everywhere, and the map flow is not live for every workspace | R1 only |
| owner experience | workspaces differ | one behaviour, but offers may rarely appear where B3/B4 are never set | most offers wait for the owner to ask |
| risk | two texts to keep in step | box_offer has no real-chat acceptance yet (`pi-architecture-vision.md` line 248) | against the spec |
| code change | none | remove the flag default or turn it on by default | remove Box wording |

## 4. The two failing integration tests (both fail on plain `cc462c5`; I ran them on the disposable database)

1. `tests/integration/test_pi_brain_decisions.py::test_the_summary_then_the_fixed_offer_with_buttons` (line 65).
   The fixture `to_the_offer` monkeypatches `box.box_offer_enabled` to `True` and `box.can_offer` to allow
   (lines ~21-23), so the box is on, and the code correctly returns the Solution Box line (variant C for two
   problems). The test still asserts the legacy `decisions.text("offer", "en")` and `OFFER_BUTTONS`. Observed:
   expected "Would you like a solution document ...", got "It's fine if you don't want this yet ...". This is
   a **stale test against X1-a**, not a code fault, under X1-a. It is referenced by
   `test_pi_part10_coverage.py:27` and `rule_index.json`.
2. `tests/integration/test_pi_brain_problems.py::test_merge_split_link_withdraw_and_rename_a_group` (line 194).
   It fails at line 255, `[link] = (await business_db.scalars(select(PiProblemLink))).all()`: zero problem
   links exist. **This is not an offer-wording failure.** Cause not diagnosed here; needs an owner.

## 5. X2: never-offer conditions

The audit said R3 and "no other problems" were never set. In current code `box.offer_facts` reads
`no_other_problems` (`box.py:212-213`, `box_signals.says_no_others`), `just_corrected` and `main_cause_known`
(`box.py:214-215`) and `service_conversation.py:3297` accepts R3 via `box_signals.asks_who_or_how_long`.
That suggests X2 is largely addressed in code; I have **not** re-verified it in a live chat or listed a test per
condition. Proposed: a table test per "never offer if ..." condition and per R1-R3 and B1-B7 (some exist in
`tests/unit`; coverage not audited here).

## 6. Tests that change, per option

- X1-a: update test 1 to assert `solution_ask.box_offer_line(...)` and the box-on buttons; add a box-off test
  asserting the legacy line and `R1-blocked` without a request. No production code change.
- X1-b: many tests that rely on the legacy offer change (not counted), plus a default-flag change.
- X1-c: remove the Box offer tests and the flag.

## 7. Recommendation (mine, marked as such)

X1-a: keep the code, and fix the stale test. It follows Book 5 where the flag is on and leaves other
workspaces unchanged. Whether `box_offer` should be on by default for Workzap is a separate decision that
needs the real-chat acceptance the plan lists as not done. Test 2 should be handed to its owner.

## 8. Decisions needed

1. X1-a, b or c.
2. Whether `box_offer` becomes the default, and for which workspace first.
3. Who owns `test_merge_split_link_withdraw_and_rename_a_group`.
4. Review of the five single-variant translations (Urdu, Arabic, French, Persian, Spanish) by native speakers.

## 9. Limitations

Spec quotes are from text extracted from the PDFs; page numbers refer to the v1.5 PDF footers. I did not run
a live chat. The first-edition section number is the one printed in the text.
