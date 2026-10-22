# pi Brain: state machine plan

Source: `pi-brain-v3.pdf` Parts 3, 4, 5, 6 and 9. Written 2026-10-21 after reading Parts 1 to 6.
Scope: Workzap's own pi only, behind flags. Other workspaces keep today's behaviour.

## 1. What the spec asks for

**Conversation states (Part 3.2).** Every conversation has one state, enforced in code:

```
S0_NEW -> S1_LISTENING <-> S2_CLARIFYING -> S3_NOTED -> (loop) -> S4_SORTED_SUMMARY
S4 -> S5_READINESS -> S6_PREPARING -> S7_DELIVERED -> S8_REVIEW <-> S8b_CHANGES_REQUESTED
S5 -> S5b_DECLINED (dormant)      S8 -> S9_APPROVED -> S10_AWAITING_PAYMENT
S8 -> S9b_DECLINED_QUOTE          S10 -> S11_PAYMENT_CONFIRMED -> S12_KICKOFF -> S13_IN_BUILD
any -> X_EMERGENCY | X_HUMAN | X_PAUSED | X_OUT_OF_SCOPE | X_BLOCKED
```

Each state lists what pi may and must not do. Examples: no suggestion, offer or quote before
S5; no document without an explicit yes (`yes_message_id`, confidence >= 0.9); approval needs
two confirmations and `can_approve`; payment is confirmed only by staff.

**Problem model (Part 4).** A durable record per problem (title <= 8 words, `user_words`,
category/subtype from a fixed 19-category taxonomy, scope, frequency, since, impact, stated and
inferred severity, confidence, links, revisions). Split, merge, link and group rules; teams
(`can_approve`, shared workspace, duplicates across contacts).

**Document and quote (Part 5).** A solution document (drafted by pi from problem records) and
a quote (priced by Workzap), both approved by a human before sending (R-DOC-00). Decisions by
three buttons. Payment by bank transfer only. Kickoff after staff confirm payment.

## 2. What exists today

| Spec | Today | Gap |
|---|---|---|
| `conversations.state` | None. Progress lives in `service_brief` (projects: collecting, awaiting_confirmation, confirmed, with_team), `brief["proposal"]`, `awaiting_customer` | No single state, no transition guard |
| Problem records | `analyse()` in `pi_customer/service.py` rebuilds `customer_issues` per chat (cached JSON, departments); `service_brief.projects` is project-centred | No durable problem rows, revisions, links, taxonomy |
| Listening, no pitching | Prompt says "never pitch while they explain"; asks for name and business early; qualifies leads | Spec forbids the early profile questions and has no lead qualification |
| Offer, explicit yes | Brief is confirmed ("Shall I send this to the team?"), then an AI-written proposal is sent automatically (`auto_proposal`) | No offer step, no yes classifier, no choice of problems |
| Document + quote | One AI-written proposal (`PiDocument`, `deals.py`), prices from catalog variants. `execution_mode` ai_led/mixed/human_approved | Spec: two documents, human approval mandatory, quote never AI-priced |
| Decision | `proposal_answer` accepted/changes/declined with evidence; page and chat share `deals.answer`; buttons exist (`buttons.py`) | No double confirmation, no `can_approve` |
| Payment | Stripe, bank, wallets, cash, pay links (`request_payment` tool, `action="payment"`) | Spec: bank transfer only, nothing typed in chat, staff confirm |
| Kickoff | Meetings and bookings (`pi_saas/meetings.py`, `work.py`) | Reusable for kickoff slots |
| Emergency, PII, abuse | None as classifiers | Part 6 cases need pre-LLM checks |
| Follow-ups | `followups.py`, `deal_followups.py`, check-in ladder | Needs the 3.9.1 policy and quiet hours |
| Voice and identity rules | `constitution.py` linter (flag `response_rules.constitution`) | Needs state-aware R-SELL rules |

## 3. Design decisions

1. **Stored state, nullable.** Add `pi_conversations.flow_state` (string, null = legacy flow)
   and `flow_state_since`. Only conversations of a workspace in brain mode get a state. Existing
   artefacts (deals, documents, payments) stay the source of truth for S6 to S13; the state is
   advanced from them, never the other way round for money.
2. **Pure transition table in code** (`pi/flow.py`): `State` enum, `TRANSITIONS`, `allowed_tools(state)`,
   `advance(state, event) -> state | Rejected`. The model asks for a transition in its structured
   result; the code accepts or rejects it, as `proposal_answer` already works.
3. **Keep structured output, not function calling.** Today a turn is one `ServiceTurn` JSON.
   Extend it (`problems` operations, `requested_state`, `yes_message_id`) instead of rewriting to
   a tool loop. Guards run after the turn, like `confirmed_now` and `proposal_evidence`.
4. **Real tables for problems** (not JSON): `pi_problems`, `pi_problem_revisions`,
   `pi_problem_links`, `pi_problem_groups`. Needed for merge/split history, links across contacts
   and the solution document quoting `user_words`.
5. **Explicit yes is deterministic.** Button id first, then a multilingual phrase list
   (yes, haan, ji, theek hai, go ahead, thumbs up; not ok, hmm, maybe). No model in the gate.
6. **Brain mode switches off what conflicts:** `auto_proposal`, `request_payment`, early profile
   questions, lead qualification. It is one setting, `response_rules.pi_mode = "brain"`, which
   implies the constitution linter and industry packs; the three existing flags stay for partial use.

## 4. Phases

Each phase ships behind the flag, with unit tests and one integration test on a disposable DB.

**P1. State core** (small, unblocks the rest)
- Migration 0034: `flow_state`, `flow_state_since`.
- `pi/flow.py` with the full table from 3.2 and unit tests for every legal and illegal move.
- Derive the first state for an existing chat (no messages: S0; has projects: S3; proposal sent: S7...).
- Prompt gets `state`, allowed next states, state guidance; linter gains R-SELL-01/02
  (no solution, offer, product or quote language in S0 to S4).
- Opening message fixed to the canonical line (R-DISC-01).

**P2. Problems and taxonomy**
- Migration 0035: the four tables. `pi/taxonomy.py`: 19 categories, sub-types, labels (the packs
  already use these keys).
- `ServiceTurn.problems` operations: create, update, merge, split, link; title rules (<= 8 words,
  no names, no blame), confidence < 0.6 means confirm first, severity score (4.7).
- S3 noted line and S4 summary formats (grouped, counts, plain words), correction handling,
  pattern surfacing (3+ in a group).
- Replace "ask for name and business" with the shape-question rule: one question, after two
  problems, never in the opening.

**P3. Offer and decision gates (S5, S5b, S8, S9)**
- Yes classifier, fixed offer text, "all or some" question when 2+ groups, decline accepted
  without persuasion and no re-offer in the session.
- Teams: `can_approve` on the customer, the owner-must-approve reply, shared-workspace notice.
- Approval needs two confirmations; buttons Approve, Ask for changes, Say no.

**P4. Documents and quote (S6, S7, S8b)**
- Brain mode creates a draft solution document from problem records and a quote draft; both wait
  for a reviewer (`approved_by`) in the dashboard. No automatic send. R-DOC-01..09 checks
  (every component maps to a problem, "what it won't do" never empty, no price in the document).
- Quote prices only from the reviewer; revisions as new versions, old ones superseded.

**P5. Payment and kickoff (S10 to S13)**
- Bank transfer only in brain mode: details only on the approved quote PDF, never typed.
- Staff-only confirmation moves S10 to S11; pi then offers kickoff slots (reuse meetings).
- Screenshots: thank, never confirm. Detail-change and refund claims escalate.

**P6. X-states and safety classifiers (Part 6)**
- Pre-LLM: emergency (with country numbers), PII detect and redact (encrypted quarantine, 30-day
  TTL), abuse and spam, advice-limit triggers, stop/opt-out.
- Escalation reasons list (6.6), `X_HUMAN` hand-off and hand-back lines, honest SLA message.
- Follow-up policy 3.9.1 mapped onto the existing ladder (quiet hours, Jumu'ah, Ramadan).

**P7. Evals**
- Golden conversations G1 to G15 and the red-team cases as integration tests with a scripted
  model (the harness in `test_pi_reply_language.py` already does this). CI gate.

Learning loop (Part 8) comes after P7 and is out of scope here.

## 5. Decisions needed from Workzap (Appendix D)

1. Human SLA pi may state (default: none).
2. Approved company profile facts pi may state.
3. Bank details: where the quote PDF gets them, and who sets prices (price book).
4. Retention for messages and the PII quarantine (must match `workzap.ai/pi/privacy`).
5. Which regulated trades Workzap serves, and the polite decline for the rest.
6. Whether any document type may skip review (spec recommends none).
7. One umbrella `pi_mode` setting, or keep separate flags (recommended: umbrella).

## 6. Risks

- `service_conversation.py` is large and shared; every change must stay behind `pi_mode`.
- The brain flow conflicts with the shared prompt in places (early profile questions, payment
  action). Brain mode must replace those parts, not stack on them.
- Prod needs migrations 0033 (already on the real DB), 0034 and 0035 before the flag is turned on.
- Roman Urdu and Urdu phrase lists (yes, banned phrases, emergency words) are thin and need
  native-speaker review before launch (spec 2.5.1).

## 7. Status (2026-10-22)

| Phase | State | Commit | Notes |
|---|---|---|---|
| Industry packs | done | 493b5ea | flag `knowledge_config.industry_packs`, migration 0033 |
| Constitution linter | done | 623ec92 | flag `response_rules.constitution`; hardened by `test_pi_redteam.py` |
| P1 state core | done | a3cd10f | `pi_mode`, migration 0034 |
| P2 problems and taxonomy | done | 3234105 | migration 0035 |
| P3 offer and decision gates | done | d4432fb | migration 0036 (`can_approve`) |
| P4 documents and quote | done in code, review UI missing | 1de1b6c and later | migration 0037; reviewer API only (`/pi/brain-documents`), no screen yet; sending outside the 24-hour window needs a template (open) |
| Style profile and repair strategies (spec 8.4.1, 8.4.2) | done | | `style.py`, brain-mode context and a linter length rule |
| P5 payment and kickoff | done | | migration 0038; approval now ends in S10; claims; staff confirm API; S11 notice; kickoff booking moves to S12; no screen yet |
| P6 X-states and safety classifiers | done (uncommitted until review) | | migration 0039; emergency, PII redaction + quarantine, advice limits, identity answers; open: opt-out reuse of `note_opt_out`, R-PRIV-06 deletion, escalation reasons |
| P7 golden conversations G1 to G15 | partly | | G5, G10, G11, G13 covered; see `pi-rule-coverage.md` |
| Learning loop (Part 8), step A | done | | `learning.py` (reward, never-learn, risk, Thompson bandit, freeze, drift), `pi_experiences` (0040) scored by the sweep, text-free; open: example bank (needs embeddings and the redaction gate), question arms in prompts, lexicon, pack drafting, canary/rollback, settings tuning, Brain dashboard, staff teaching buttons, problem-board image |

Production still needs migrations 0034 to 0037 (the real database is at 0033) before `pi_mode` is
turned on anywhere.
