# P-6 design: evidence-backed claims and outcome verification

Status: DESIGN PROPOSAL for owner review, 2026-10-30, written against `origin/main` cc462c5 plus read-only
`git show` of `pi/s-ft02` (read at commit a4fd6dc; owner-os-61 may still add a third commit, so every
`pi/s-ft02` reference below is to a4fd6dc) and of `pi/doc-fast-track` (the approved plan). **Documented
only.** Nothing is implemented, tested or run; no code, migration, table, model call or spend. Task id P-6
(FT-X1 in the fast-track plan). Nothing here changes approved scope or approved acceptance criteria.

Conventions: every item carries a status, **APPROVED** (the owner approved it; source named) or
**PROPOSED** (this document's suggestion, needs the owner's yes). Exact references are `path:line` on
`origin/main` cc462c5 unless marked `[a4fd6dc]` (read with `git show pi/s-ft02:path`, never from its
worktree). Paths are under `apps/api/app/modules/` and `apps/api/tests/`. "Not verified" marks a statement I
did not confirm in code; section 14 lists them all.

Rule to implement: **pi never states that an action was done, sent, booked, approved, paid, delivered,
noted or prepared unless a verifiable record shows it, and never says an outcome was achieved unless
someone with authority or the customer confirmed it.** A promise about the future ("I will note", "the team
reviews first") is allowed only in the form the non-negotiables already allow; this design does not widen it.

## 1. What exists today (so nothing is built twice)

| Existing control | Where | What it covers | Limit |
|---|---|---|---|
| `R-PAY-05` payment received only after staff confirm | `pi/constitution.py:1841` (check), `:1598-1599` (`_claims_payment`), `:148-162` (`PAYMENT_RECEIVED`), `pi/constitution_langs.py:180`; context flag `payment_confirmed` | one claim type, hard violation, several languages | the only claim with an evidence flag |
| `R-HONEST-01/02` invented timelines, clients, statistics, "no amount before an approved quote" | `pi/constitution.py:1432-1456`, `:2050` | made-up facts and prices | not about actions |
| `R-PROM-01` guarantees and promised results | `pi/constitution.py:1876` | outcome promises | not "it is done" claims |
| `R-DISC-06` "the team will see this chat" | `pi/constitution.py:2153` (`TEAM_WILL_SEE` defined `:1133-1138`) | one false claim about visibility, in expert mode only (`:2152`) | single pattern |
| `FINAL_CHECKS` (R-PAY-02, R-PAY-03, R-DISC-03, R-BRAND-01) | `pi/constitution.py:2341`; used in the last-pass lint at `pi/service_conversation.py:6389` (`constitution.lint(turn.reply, context)` filtered to `FINAL_CHECKS`) | rules re-run on the final text after late appends; the lint receives the turn context, so a rule may read evidence flags | no claim rule among them |
| fixed application lines with truthful text | `pi/decisions.py:229-239` (`preparing`), `:240-244` (`declined`), `pi_saas/deals.py:186-195` (`delivered`, `ORDER_UPDATES`), `pi/brain_payments.py:122-131` | text written by code at the moment the event happens | true only if sent at that moment; the model can repeat it later |
| append-only evidence records | `pi/box_models.py:102-106` (`pi_box_transitions`), `pi/brain_docs_models.py:77-78` (`approved_by`, `approved_at`) and `:113` (`confirmed_by`), `pi_saas/deal_models.py` (`pi_documents` response fields, per P-4), `pi/problem_models.py:111-127` (`pi_problem_revisions`) | see section 2 and the P-4 audit | decline and quote-declined leave no durable row (P-4 audit finding 3) |
| decision request raised in a savepoint that can fail silently | `pi/service_conversation.py:3475-3499` (`raise_decision_request`: `begin_nested`, `except DBAPIError: logger.warning("pi_decision_request_skipped")`) | the request that backs the `preparing` line | **the line can be sent although no request row exists**; this is a concrete C2 failure case |

Gap this design closes: only the payment claim is checked against evidence. Every other "done" sentence
(including model-written ones and the fixed ones when repeated) is unchecked.

## 2. Claim taxonomy: claim, required evidence, where to check

Evidence is read at context time by one read-only function (section 3), never written by this feature.

| # | Claim type (examples, en) | Required evidence | Table or log to check | If no evidence |
|---|---|---|---|---|
| C1 | **Noted / saved** ("I've noted that", "saved", "I've added it to your list") | a problem, fact or want stored this turn or earlier | `pi_problems` + `pi_problem_revisions`, `pi_memories`, brief `wants` (Part 19) | say what was heard, not that it was stored |
| C2 | **Asked staff / request raised** ("I've asked Workzap to prepare your document", the `preparing` line) | a raised request row for this customer | `pi_saas/requests.py` `raise_request` (called from `pi/service_conversation.py:3475`; the table was not read here, see section 14), `pi_box_transitions` (`pi/box_models.py:106`) | "I can ask Workzap to prepare it" (offer form, no past tense) |
| C3 | **Document prepared / sent** ("your document is ready", "I've sent the quote") | a `pi_brain_documents` row with `status=sent` and `sent_at`, or a sent `pi_documents` row | `pi_brain_documents.status/sent_at`, `pi_documents.sent_at` | "the team is still preparing it" only if C2 evidence exists, else the offer form |
| C4 | **Approved** ("the team approved it", "approved by Workzap") | `approved_by` and `approved_at` set | `pi_brain_documents.approved_by/approved_at`; customer approval: box `sent -> accepted` in `pi_box_transitions` and the brief `approval` (this conversation only) | "waiting for the team to review it" (only if C2/C3 evidence exists) |
| C5 | **Payment received / confirmed** | `confirmed_by` set | `pi_brain_payments.confirmed_by/confirmed_at` (today: context flag `payment_confirmed`) | existing R-PAY-05 behaviour |
| C6 | **Booked / meeting set** ("I've booked Tuesday 4pm") | a booking or calendar row for this customer at that time | booking tables and meeting link records (not read here: owner of the `pi_saas` meetings desk to confirm) | "I can book it if you confirm the time" |
| C7 | **Work started / shipped / delivered** | order status `processing`, `shipped` or `delivered`; deal journey flags | `Order.status`, `deals.ORDER_UPDATES`, `deal_routes.journey` (`order.status in {...}`) | do not say it; say what is recorded (e.g. paid, not started) |
| C8 | **Team has seen / will follow up by a time** ("the team will contact you today") | an open staff request or a scheduled follow-up row | staff request rows, `brain_followups` schedule | no time promise (also `R-HONEST-01`) |
| C9 | **Changed / corrected** ("I've updated your number to X") | a new revision row with the new value, or the memory row archived and replaced | `pi_problem_revisions.diff`, `pi_memories` (old row `archived`) | read the value back as "you said X" |
| C10 | **Deleted / erased** ("your data is deleted") | the erase ran: an erase audit record | `brain_erase.erase_customer` result, audit log (inferred) | never claim erasure without the record; documents and payments are kept by design (R1 to R6 open) |
| C11 | **Outcome achieved** ("it worked", "your orders are no longer lost", "problem solved") | customer or staff confirmation of the outcome (section 5), not delivery alone | feedback saved by `pi/service_conversation.py:7558-7600` (`save_feedback`: a note on the lead via `note_lead`, a `customer_activities` row via `log_activity`, and `brief["feedback"]`); `pi_problems.status = "resolved"` (`pi/taxonomy.py:93`) set only through a revision | say what was delivered; ask how it went |
| C12 | **Kept / remembered** ("everything you told me is kept here", the `declined` line) | the data exists and no erase has run | the customer's `pi_problems`/`pi_memories` rows present | drop the claim if the rows are gone |

Not a claim (allowed without evidence): a question; an offer ("I can ask Workzap to prepare it"); a
statement of what the owner said ("you said 5 lakh"); a future step phrased as intended action that the
non-negotiables already allow ("I will note these for the document that the team reviews", the FT-02
covers line) provided the **same turn** also creates the record it names, or the line is changed to the
offer form. Section 6 settles that boundary.

## 3. Where the gate sits and how it works

**One evidence read, one final-text check.**

1. `claim_evidence(session, conversation)`: a read-only function in the style of `brain_docs.open_quote`
   (called at `pi/service_conversation.py:1585`). It is the same read-only function as P-4 option A
   (`pi-decision-records-audit.md` section 4 on `pi/s-s7a-audit`), so P-4 and P-6 must share one function,
   not build two. It returns a small dict of booleans and ids only: `noted`,
   `request_raised`, `document_sent`, `approved`, `payment_confirmed`, `booked`, `order_state`,
   `feedback_saved`, `erased`. Tenant and environment come from the conversation row (`WorkspaceRow`
   scope); nothing is stored, so there is no new table, erase gap or retention question.
2. The result is placed in the turn context next to `payment_confirmed` (which it generalises).
3. **The gate is a last-pass check on the final assembled reply**, after every late append, in the same place
   and for the same reason as `constitution.final_one_question` `[a4fd6dc]` (`pi/constitution.py:2344`,
   called at `pi/service_conversation.py:6542`): the first validation (`validate_service_reply` at
   `service_conversation.py:6380` on main; the break check at `[a4fd6dc]` `:6333`) runs before fixed lines,
   offers, notices and disclosures are added. The claim rule (`R-CLAIM-01`, PROPOSED name) would be added to `FINAL_CHECKS`
   (`constitution.py:2341`). `FINAL_CHECKS` is a set of rule ids applied to the result of
   `constitution.lint(turn.reply, context)` (`service_conversation.py:6389` on main, `[a4fd6dc]` `:6458`),
   and `lint` receives the turn context, so a rule can read the evidence dict; `payment_confirmed`
   (`constitution.py:1841`) already works that way.
4. Detection: for each sentence of the final text, a per-language claim detector returns zero or more
   claim types (C1 to C12). A claim without its evidence is a violation; the sentence is rewritten
   (section 4), never dropped silently and never replaced by an invented sentence.

**Claim detector by language** (patterns, not a model, so it is deterministic and testable):

| Language | Source of patterns | Strength | Main false-negative risk | Main false-positive risk |
|---|---|---|---|---|
| en | past tense or perfect of a done verb with first-person or passive object ("I've sent", "is ready", "has been approved") | strong | idiom ("all set", "you're good to go"), implied claims ("here is your quote" with no attachment) | an owner-quoted sentence ("you said it was delivered") and conditional ("once it is approved") |
| roman_ur | `kar diya`, `bhej diya`, `ho gaya`, `tayyar hai`, `mehfooz hai`, `kar liya` | medium | spelling variants, mixed English | `kar diya` used about the owner's actions |
| ur (script) | the same verbs in script | partial: no entries in the fixed lines today (FT-02 audit R7) | stemming, `۔` sentence split | as above |
| ar | perfect verb forms (`تم إرسال`, `طلبت`, `أرسلت`) | partial | dialect | past tense about the owner |
| hi (Devanagari) | `कर दिया`, `भेज दिया`, `हो गया` | weak (no existing bank) | most forms | as above |

Limits stated plainly: a regex detector will miss novel phrasings (false negatives) and will sometimes flag
the owner's own words (false positives). So: (a) the gate runs on **pi's** sentences only and skips text
inside quotation marks and sentences that start with "you said"; (b) a rewrite is conservative (section 4);
(c) "not covered for this language" is reported by the evaluation, never "passing", for ur, ar and hi until
labelled cases exist (same rule as P-2 and P-3).

## 4. Fail-safe behaviour: soften to what is true, never invent

For a claim without evidence the gate does **one** of these, in this order:

1. **Offer form** (the claim becomes a possibility): "I've asked Workzap to prepare it" becomes "I can ask
   Workzap to prepare it." Uses fixed per-language templates keyed by claim type, so the rewrite is code,
   not model output.
2. **What is recorded** (state the true state): C7/C3: "your document is not sent yet; the team has your
   request" only when the request evidence (C2) exists; otherwise rule 1.
3. **Drop the sentence** only when it is a pure claim with no information (for example a lone "Done!"), and
   the reply still has its question.
4. **Regenerate once with the reason** (the existing "fail, regenerate, then fixed fallback + alert" path in
   the v1.5 rules) when the rewrite would leave the reply without content. A second failure uses a fixed
   safe line and raises the human alert already used for other gates.

The gate never adds a fact, a date, a name or a promise. It never touches the AI disclosure, the emergency
lines or the payment-refusal text (all statements by design). Order PROPOSED: the claim rewrite runs
**before** `final_one_question` `[a4fd6dc]` (`service_conversation.py:6542`), so the one-question rule
still sees the final text; both are last-pass checks and the exact order is fixed in the implementation
plan after FT-02 is integrated.

## 5. Outcome verification after delivery

"Delivered" is evidence of delivery, not of an outcome (C7 versus C11). PROPOSED sequence, reusing the
after-payment journey that already exists (`pi_saas/deals.py:186-195` `delivered` text and `ORDER_UPDATES`;
`pi_saas/deals.py:1343-1384` the work-moved note and the `awaiting_feedback` marker;
`pi_saas/deal_routes.py:147-170` the start/delivered route; `deal_routes.py:567-573` the journey flags;
`pi/service_conversation.py:7558-7600` `save_feedback`):

| Step | Evidence | Who confirms | Timing | Stored where (no new table) |
|---|---|---|---|---|
| 1 delivered | `Order.status = delivered`, set by staff through the journey route (`deal_routes.py:147-170`) | staff | when staff mark it | `Order.status` (exists) |
| 2 customer asked how it went | the `awaiting_feedback` marker (`deals.py:1384`) and the sent message | pi (system) | right after step 1 (exists today) | brief key `awaiting_feedback` (per conversation) |
| 3 customer answers | `save_feedback` writes a lead note (`note_lead`), a `customer_activities` row (`log_activity`) and `brief["feedback"]` (`service_conversation.py:7580-7599`) | the customer | any time; one reminder at an interval the owner sets | lead note, activity row, brief (exist) |
| 4 outcome verified | the step 3 words classified as a confirmed outcome (the extractor already returns `feedback_mood`, `service_conversation.py:7574`), or a staff confirmation, linked to the problem ids the document covered | customer or staff, **never pi alone** | after step 3 | PROPOSED: a `pi_problem_revisions` row with `reason="outcome_confirmed"` and the evidence message id in `diff`, then `pi_problems.status = "resolved"` (value exists, `pi/taxonomy.py:93`) only through that revision |
| 5 not confirmed | no answer, or "not fixed" | | after the reminder window | problem stays open; pi may ask what remains, never claims "solved" |

Rules (PROPOSED): pi may say "delivered" at step 1, "you told me it worked" at step 4, and nothing stronger.
"Verified" means a confirmation record exists; whether the outcome is also *correct* is the owner's business
judgement and is out of scope. A reversal (customer later says it broke) is a new revision, not an edit.

**Migration finding (verified):** `pi_problem_revisions.reason` is `String(24)` with no CHECK constraint on it
(`pi/problem_models.py:126`; the only CHECK on that table is on `by`, `:121`, values `pi`, `person`,
`staff`). So the new reason `outcome_confirmed` (17 characters) needs **no migration**, and `by` already has
the right values (`person` for the customer, `staff` for a staff confirmation). This removes the dependency
on migration 0053 that an earlier draft of this section assumed.

**Evidence consistency gap:** the step 3 words live in `customer_activities` and the lead note (both outside
erase today: G12, G14 in `pi-erase-gaps-g1-g14.md`) and in `brief["feedback"]` (erased with the
conversation). After an erase the verified-outcome claim (C11) must be re-derived only from rows that still
exist; the retention decision R1 to R6 decides which.

## 6. Part 19, `preparing` and covers lines, and the boundary of "promise" versus "claim"

| Line | Text (en) | Claim? | Evidence needed | Recommendation |
|---|---|---|---|---|
| `preparing` (`pi/decisions.py:229-239` on main) | "I've asked Workzap to prepare your solution document and quote. I'll send them here once they're ready." | C2 (past tense "asked") | request row exists | send the line only if `raise_decision_request` (`service_conversation.py:3475-3499`) actually created the row, since its failure is swallowed at `:3499`; otherwise the offer form. The FT-02 fix `[a4fd6dc]` adds that the team reviews first (`decisions.py:230-240` there); the claim part remains |
| covers lines `[a4fd6dc]` `pi/part19.py:241-264` (`COVERS_LINES`, `covers_lines`) | "I will note these for the document that the team reviews: {items}." | a promise, not a claim | none, but it must become true | keep as a promise only when the same turn writes the wants; the line does not say "noted" |
| `declined` (`pi/decisions.py:240-244`) | "Everything you've told me is kept here if you change your mind." | C12 | rows exist | allowed only until an erase; after an erase it is false (section 7) |
| "I've noted" model sentences | model-written | C1 | stored record | covered by the gate |
| playback `[a4fd6dc]` `pi/part19.py:324` (`replay`) | "Here is what I have noted..." | C1 | stored problems and wants | true by construction; keep |

Boundary proposed: **past tense or "is/has been" about an action needs a record; "I will / I can" about an
action needs none, provided the action is allowed and actually happens.** A "will" with no mechanism behind
it (no request, no follow-up row) is itself an unchecked claim; the detector flags "will" lines in C8 when
no scheduled follow-up or open request exists.

## 7. Erase, retention and tenant isolation

- The gate reads only; it stores nothing. No new table, column or migration: the one proposed write, a
  `pi_problem_revisions` row with `reason="outcome_confirmed"` (section 5), needs no schema change
  (`pi/problem_models.py:126`, `String(24)`, no CHECK on `reason`).
- Tenant and environment scoping comes from the conversation row; the evidence read joins only on the
  conversation's customer, using the same scoped repositories as `open_quote`. A two-tenant test with the same
  phone number in both workspaces is required (pattern of `test_pi_isolation_core.py`).
- After an erase the evidence for C1, C9, C12 is gone by design, so those claims must be false/softened after
  the erase; C3, C4, C5 evidence (documents and payments) stays under today's policy and the retention
  decisions R1 to R6 (`pi-erase-gaps-g1-g14.md`): if the owner decides documents are erased, C3/C4 claims
  about them must stop at the same time. The design follows whichever retention decision is taken.
- C10 (a claim that data was deleted) needs an erase record. `erase_customer` is at `pi/brain_erase.py:128`;
  a grep of that file for an audit call (`audit.record`, `from app.modules.audit`) found none, and the
  callers were not checked. Until an erase record is shown to exist, pi must never claim erasure in chat.

## 8. Tests (scripted proposals; nothing run) and real-model checks (proposals only)

**Scripted unit tests** (disposable DB not needed for the detector; needed for the evidence read):
1. Detector table test: for each claim type C1 to C12 and each language (en, roman_ur, ar; ur and hi marked
   "not covered" until patterns exist), 3 positive and 3 negative sentences, including owner-quoted text,
   questions, offers and conditionals.
2. Gate test on the FINAL assembled reply: a model reply claiming each action with no evidence is rewritten
   by the fixed template; the same reply with evidence is untouched; a lone claim is dropped; the reply keeps
   its one question and its AI disclosure.
3. Negative controls: a gate that does nothing must fail the suite (a reply with a false C5 passes through).
4. Evidence read (integration, disposable DB): each flag true only when its row exists; two-tenant
   isolation; after `erase_customer` the C1/C9/C12 flags are false and C3/C4/C5 follow the retention policy.
5. Interaction tests: payment-refusal and emergency lines are never removed; `final_one_question` still holds
   after the claim rewrite; fixed lines (`preparing`, `declined`, covers) pass when their evidence exists.
6. Outcome verification: delivered without feedback never produces "it worked"; feedback with a confirmed
   outcome writes exactly one revision row with the evidence message id; a later "it broke" reopens.

**Real-model checks (proposals; each needs its own approval, model verification, price and cap; none run):**
a Stage 3 style replay (see `pi-real-model-stage3-proposal.md` on `pi/e-p5-stage-proposals`) of short
conversations designed to tempt a false claim (customer asks "did you send it?", "is it approved?"), scored
by the `grader` agent and by the gate itself; count false claims per 100 replies, per language, with the gate
off and on. No threshold is set here (D5 pending).

## 9. Acceptance criteria (measurable, to be confirmed by the owner)

1. Every claim type C1 to C12 has a detector test per covered language and an evidence-read test.
2. With the gate on, a scripted reply claiming an action with no evidence never reaches the customer in any
   covered language (0 of the scripted cases), and a reply with evidence is unchanged.
3. The gate removes no AI disclosure, emergency, payment-refusal or safety sentence (tests).
4. Languages without patterns are reported "not covered", not "passing".
5. A real-model replay (when approved) reports false claims per 100 replies with the gate off and on.
6. No new table and no migration (the new revision `reason` value needs none, section 5).
7. Two-tenant test passes; after an erase, no claim relies on erased evidence.

These seven are PROPOSED additions. They do not replace the approved acceptance criteria of the plan row
(section 13).

## 10. Risks

- **False positives** rewriting a true sentence: mitigated by evidence checks first, owner-quote skip, and
  conservative templates; measured in the real-model check.
- **False negatives** on idioms and unsupported languages: stated, never hidden.
- **Hot file:** the gate sits at the end of `compose_service_turn` in `service_conversation.py` (about 7,800
  lines). Its hunk must be small (one call) and rebased on the FT-02 integration.
- **Evidence staleness:** a record can change between the read and the send; the read happens at the start of
  the final pass, and an old claim in earlier messages is not rewritten (only new sentences).
- **Fixed lines versus truth:** `preparing` and `declined` can become false after the fact; section 6.
- **B1 and B4 (capability map):** denied actions are not audited, and there is no refund or payment reversal,
  so C5 and C10 can be proved forward only; pi must not claim a reversal ("refunded") at all until a
  record type exists (add refund wording to the detector as an always-block claim).

## 11. Dependencies and open owner decisions

**Depends on:** FT-02 integrated (the final-text pass and Part 19 wording are in that lane; this design does
not touch it); the P-4 retention decisions R1 to R6; B1 (audit of denied actions) as a hardening, not a
blocker; D5 for any pass/fail threshold. It does **not** depend on migration 0053 (section 5).

**Owner decisions needed:**
1. Is the boundary in section 6 right: past tense needs a record, "I will / I can" does not?
2. May the gate rewrite a model sentence (templates) or should it only regenerate and fall back?
3. Who confirms an outcome (customer words, staff, both) and the reminder window after delivery?
4. May `pi_problems.status` become `resolved` (it exists, `pi/taxonomy.py:93`) through a confirmed outcome
   revision?
5. Should "refunded", "reversed" and "erased" claims be blocked outright until their record types exist?
6. Which hard-fail languages must be covered before release (en and roman_ur now; ur, ar, hi later)?

## 12. Limitations

- Design only; no code was read beyond the cited lines and no database was queried.
- Not read: the `pi_saas/requests.py` table behind `raise_request`, the booking and meeting tables,
  `brain_payments.py` in full, the callers of `erase_customer`, and `taxonomy.STATUSES` use sites. Each is
  listed in section 14.
- The per-language detector strength is judged from existing banks (`pi/constitution_langs.py`) and the FT-02
  audit, not measured.
- Status: documented; implemented no; scripted-tested no; real-model-verified no.

## 13. Conformance with the approved master roadmap (`pi/doc-fast-track:docs/pi-saas/pi-fast-track-plan.md`)

| Plan reference | What it says (plan line) | This design |
|---|---|---|
| Section 8 table, row P-6 (`pi-fast-track-plan.md`, the "P-6" row) | "FT-X1: evidence-backed claims: no done, sent, approved or booked unless a record shows it; outcome check after delivery"; lane S; depends on FT-02, capability-map B1, after-payment records; acceptance "the linter and a gate block a completion claim with no record; a test per claim type"; tests "final-text lint, two-tenant"; status planned | **APPROVED** acceptance and tests are kept verbatim as criteria 2 and 1 and tests 2 and 4 of this design. Criteria 3 to 7 and the evidence function are **PROPOSED** additions. |
| Section 1, lanes table (lane S "Owns" list: `system_ask.py`, `box*.py`, `solution_*.py`, `expert_advisor.py`, `idea_filter.py`, `brain_docs*.py`) | lane S does not own `constitution.py` or `service_conversation.py` | those are **hot files** (plan section 1: at most about 30 lines per hunk, rebase on the latest `origin/main`, the integrator resolves conflicts). PROPOSED: the detector and templates live in a **new module** (name PROPOSED `claims.py`, lane S) and the hot files get only a call and the `FINAL_CHECKS` entry. |
| Section 5, minimum checks 1 to 10 | unit suite, targeted integration, tests first, ruff/mypy, two-tenant, erase, rule-auditor and redaction-checker, scripted report, migration up/down, clean-worktree diff | all apply unchanged. Check 9 (migration) is not needed (section 5 finding). Check 6 (erase): no new stored data, so no erase change. |
| Section 3 critical path: FT-02 → B2a → ... | FT-02 first | P-6 implementation starts only after FT-02 is integrated. This document touches nothing in FT-02. |
| Section 6 decisions D1 to D4 approved; D5, D7, D8 pending; D6 Stage 1 only | | P-6 needs no D-decision to be documented; any threshold waits for D5; D7 (offer wording) changes the exact `preparing`/offer text the gate must accept (section 14). |
| Section 8, conflict 6 (P-6 evidence source: B1) | "P-6 can only prove what existing records show" | kept: section 10 states the same limit for C5 and C10. |
| P-4 audit finding 2 | the append-only `pi_box_transitions`, `pi_brain_documents`, `pi_brain_payments` are the natural evidence source for P-6 | used as the evidence source in section 2; one shared `claim_evidence` function with P-4 option A (section 3). |

## 14. Unresolved conflicts and assumptions

**Unresolved conflicts (each needs the owner or an integration decision):**
1. **Hot file and lane ownership.** The gate needs hunks in `pi/constitution.py` and
   `pi/service_conversation.py` (hot files) while the P-6 plan row is lane S. PROPOSED resolution: new module
   plus one-line hunks; the integrator rebases (plan section 1).
2. **FT-02 is still moving.** The final-text pass (`final_one_question`), the Part 19 lines and the
   `preparing` text changed in commits a4fd6dc and may change again in owner-os-61's third commit. Every
   `[a4fd6dc]` reference may shift; P-6 must be re-based on the integrated version.
3. **One evidence function for P-4 and P-6.** Two read-only evidence functions would duplicate each other;
   P-4 option A and P-6 `claim_evidence` should be one design, decided with the P-4 owner decisions.
4. **Retention (R1 to R6) decides which claims survive an erase.** Documents and payments are kept on erase
   today (`pi/brain_erase.py`, per the P-4 audit table row "Quote requested"), free-text feedback rows are
   not erased (G12, G14). Until R1 to R6 are decided, C3, C4, C5 and C11 cannot be specified exactly for
   the post-erase state.
5. **Swallowed request failure.** `pi/service_conversation.py:3499` logs and continues when the request
   cannot be written, while the `preparing` line is already chosen. Fixing that (send the line only on
   success) is a change inside the decision path, not only a gate; whether it is in P-6 scope or a separate
   fix is undecided.
6. **Erase claim (C10) has no proven record.** No audit call was found in `pi/brain_erase.py`; either P-6
   blocks C10 outright or an audit record is added, which is outside this design.
7. **Offer wording (D7).** If the owner changes the offer text, the "offer form" templates in section 4 and
   the fixed lines in section 6 must be reconciled with it.

**Assumptions (not verified in code):**
- A. The `pi_saas/requests.py` `raise_request` table is a durable row that can be queried per customer
  (`pi/service_conversation.py:3475-3499` only shows the call).
- B. A booking or meeting record exists per customer for claim C6 (meetings desk, not read).
- C. `deals.save_feedback`'s mood (`turn.feedback_mood`, `service_conversation.py:7574`) is reliable enough to
  classify an outcome; its accuracy was not measured.
- D. Sentence-level detection per language is feasible with patterns of the kind already in
  `pi/constitution_langs.py`; strength for ur, ar and hi is judged from the existing banks only.
- E. `taxonomy.STATUSES` value `resolved` (`pi/taxonomy.py:93`) is not already set by another path; its
  writers were not searched.
- F. The callers of `erase_customer` were not read, so an erase audit event may exist outside
  `pi/brain_erase.py`.

## 15. Decision register

| Item | Status |
|---|---|
| Requirement: pi never claims an action without a verifiable record; outcome verification after delivery (owner message approving P-6) | **APPROVED** |
| Plan row acceptance and tests for P-6 (section 13) | **APPROVED** (in the approved plan) |
| FT-02 first; no P-6 implementation before it is integrated; docs-only, no push, no merge | **APPROVED** |
| Claim taxonomy C1 to C12 and the evidence per claim (section 2) | PROPOSED |
| One read-only `claim_evidence` function shared with P-4 option A (section 3) | PROPOSED |
| Gate as last-pass `R-CLAIM-01` in `FINAL_CHECKS`, new module for detector and templates (sections 3, 13) | PROPOSED |
| Fail-safe order: offer form, what is recorded, drop, regenerate once (section 4) | PROPOSED |
| Outcome sequence and the `outcome_confirmed` revision with `resolved` status (section 5) | PROPOSED |
| Boundary "past tense needs a record; I will / I can does not" (section 6) | PROPOSED |
| Block `refunded`, `reversed`, `erased` claims outright until record types exist (section 11) | PROPOSED |
| Per-language coverage: en and roman_ur first, ur/ar/hi "not covered" until patterns and labels exist | PROPOSED |
| Acceptance criteria 3 to 7 (section 9) | PROPOSED |
