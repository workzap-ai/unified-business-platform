# pi: the complete architecture and vision

Written 2026-10-27 after a week of building, from the code as it is today (origin/main `5b34ea8`),
the production data read-only, the 60-scenario real-model evaluation and the live chats. Where this
document says "built" it was seen working; "partial" and "missing" are stated plainly.

## 0. Ek safha mein (Roman Urdu)

pi ko Workzap ka **independent sochne wala advisor** hona hai: kisi bhi industry ka, kisi bhi masle
par, owner ke apne lafzon se masla samjhe, wajah dhoondhe, aur jab owner maange to sahi, aaj ke
zamane ke mutabiq, owner ke bataye hue par mabni idea de. PDFs aur 211 industries ke packs
**reference** hain (misal, level, lafz), pi ki hadd nahi. **Rules qanoon hain**: AI hone ka batana,
aik sawal aakhir mein, koi price ya document pehle nahi, koi payment chat mein nahi, koi medical, legal,
tax salah nahi. Qanoon prompt mein nahi, code mein lagta hai (linter, state guards, decision gates).

Teen cheezein har chat mein chalti hain: **Problem Map** (pi ne kya samjha, owner ne kya mana),
**Expert Advisor** (wajah ka sawal, grounded ideas), aur **Box** (poore set ka aik offer, baad mein
staff ka review). Neeche in ka naqsha, data, rules, dashboards, kharch aur parakh ka tareeqa hai.

## 1. Principles (never negotiated)

1. **Independent mind, reference knowledge.** The model reasons about the owner's own words. Packs,
   the Industry Solutions addendum, sector briefings and learned lessons are *examples and
   guard-rails*, never a list pi is limited to. An industry that is in none of them works the same way
   (verified: 12 industries outside the 211 each gave two grounded ideas).
2. **Rules are law, enforced in code.** Learned or retrieved content is data placed below the rules
   and can never override them (CLAUDE.md, Constitution layer L0).
3. **Grounded.** An idea assumes only what the owner said they have or do. No invented channel,
   asset, record, tool, staff role.
4. **Honest.** What and why, never how-to steps, never a promised result, never a price or payment
   term, never professional advice (medical, veterinary, legal, tax, financial).
5. **Never a dead end.** Failures degrade: a model failure ends in a lenient reply or a plain line,
   never silence; a handoff only when the owner asks for a person.
6. **Measured.** Every behaviour claim is backed by a replay, a grader score or a production query.

## 2. Layers

```
L0  Constitution        non-negotiables, reply linter (constitution.py), state guards (flow.py),
                        decision gates (decisions.py, box.py), safety pre-gates (safety*.py)
L1  Voice               language lock, one question last, British English, roles not names
L2  Conversation engine state machine (S0..S13, S_LISTEN_THINK, S_MAP_SHARE, S_BOX_OFFER ...),
                        problem noting, dials and moves (thinking, behind a flag)
L3  Expert advisor      diagnose -> propose -> judge -> vet (expert_advisor.py)
L4  Knowledge           model reasoning + sector briefings (packs/currency, 16 clusters)
                        + packs/industry (211) and packs/solutions (211) as EXAMPLES
                        + learned lessons and gold ideas (opt-in, frozen unless learning is on)
L5  Surfaces            WhatsApp, client dashboard (apps/pi /customer), staff console, documents
L6  Operations          providers and failover, cost and latency, drift check, evaluation harness
```

Priority when layers disagree: L0 over L1 over L2 over L3 over L4. The prompt is a request; the code
is the enforcement.

## 3. One message, end to end

1. **Inbound** (WhatsApp provider event -> `process_pi_event`). Batching of rapid messages, rate
   limits, loop guards, quiet hours.
2. **Pre-model gates** (`safety.py`, `safety_guard.py`): emergency, personal data redaction, advice
   requests (medical/legal/tax), boundaries, enquiries. These answer with fixed, translated lines.
3. **Handoff decision** (`runtime._keyword_handoff`, `needs_person`): a person takes over only when the
   owner asks for one (whole-word keyword *and* a request in the message). A business problem that
   happens to contain "banda" or "phone karta hai" is not a handoff (fixed 2026-10-27).
4. **Context** (`prepare_context`): history, noted problems, brief, dials, industry, language,
   the cached diagnosis, move history, sector briefing.
5. **Model turn** (structured JSON `ServiceTurn`): reply, problem operations, mood, language, and with
   thinking on a `move_plan`. Claude 5 is called at `effort: medium` so thinking cannot use the whole
   token budget and cut the JSON (the cause of the Dalal&Co outage). If every provider fails on invalid
   output, one more call with a reply-only schema runs before any tech-down notice.
6. **Guards after the model** (code): idea guard and filter G1-G8, one-question and voice rules,
   language check, offer gates. A violating reply is rewritten once; a still-bad reply is replaced by
   a safe fallback.
7. **Ideas when asked** (see section 5) and the whole-set offer line.
8. **Persist**: messages, problem records and revisions, brief, move log, hypotheses, audit stamp.
9. **After the reply**: diagnosis refresh (cached), map version if the map changed, follow-up
   scheduling.

## 4. The Problem Map (design and how pi checks it)

**What it is.** The owner's problems as nodes, typed links between them, grouped by root, versioned.
It is the shared picture: pi's understanding, the owner's confirmation, and the staff briefing.

**Data** (migrations 0033..0049): `pi_problems` (title, category, sub-type, goal verb,
`raised_voluntarily`, depth fields, status open/confirmed/in_box/parked/resolved/stale, tags such as
`rank:N`), `pi_problem_links` (type: causes, blocks, worsens, competes, same_root, symptom_of;
`evidence`: owner_said | pi_inferred | confirmed), `pi_problem_groups`, `pi_problem_revisions`,
`pi_map_versions` (json, image hash, shared_at, drawn positions).

**How a node is created and checked.**
1. Created only from the owner's words (`problem_ops`: create/update/merge/link/withdraw), with a title
   in their words, redacted of card/ID/phone/email, roles never names.
2. Sub-type and goal verb are set from what they want ("clear stock" vs "know my stock" sort
   differently: spec 7.2).
3. A link is **pi_inferred** (drawn dashed) until the owner confirms; **owner_said** when they said it;
   only the owner moves anything to **confirmed**. pi never confirms for them.
4. A node untouched for 90 days shows "pichli baar ka" until reconfirmed.
5. Duplicates of the same symptom merge; a different thing going wrong is a new node.

**How pi checks itself.** Every number on a map picture must appear in the owner's messages
(`map_render.numbers_supported`); unsupported numbers are dropped. The map the owner sees is built from
the same rows pi reasons from, so there is no second copy to drift.

**Surfaces.**
- WhatsApp: picture (en, roman_ur, ur, ar, fa, fr, es; Hindi falls back to English text until a
  Devanagari font is bundled) with one question and confirm / wrong / missing buttons; shared on the
  first map, when it changes, at the offer, on return; max one share per cadence rule.
- Client dashboard: Map tab, version timeline, resolve / park / reopen / rename / rank, "still true".
- Staff: the map is the briefing when a person takes over (staff view: **missing**, see section 9).

**Flags.** `response_rules.brain.map_share` (default off). Per workspace.

## 5. The Expert Advisor (how pi gives solutions)

Trigger: the owner asks for a fix ("solution do", "kuch karo", "ap kya kr skty hain", typos
included) while the flow allows it. Behind `response_rules.brain.solution_source = "expert"`.

```
owner words + noted problems + industry (maybe unknown) + country + sector briefing + never_say
   -> DIAGNOSE+PROPOSE (one Claude call, senior-operator persona, dated, English)
        problem in their words; up to 3 causes with evidence ONLY from their words;
        the one missing fact + the question for it; 5 candidate ideas with assumed resources
   -> JUDGE (fast model): scores fits / correct / current / grounded / specific / safe
   -> VET each chosen idea in code: check_idea, never_say, G1-G8, pricing and payment terms,
        outcome wording, one sentence, no digits or time, no tool words
   -> up to 2 ideas (2 per problem, up to 8 per business); if none survive: one question only
   -> translated into the owner's language; the app adds the whole-set offer line
```

Rules the engine enforces beyond the generic guards: no channel or asset the owner did not name
(G2 asset groups: video, social page, ads, online listing/search); no start-doing of what they already
do; no price, rate, discount or payment-term advice; no promised outcome; staff roles and records are
asked, not assumed.

**Diagnosis-driven questions.** The cached diagnosis supplies `suggested_next_question` so the next
question is about *why* the main problem happens, never an adjacent process (R-ASK-08). No "Noted /
Note kar liya" opener and no "the team will see this" (R-ECHO-05, R-DISC-05).

**Measured** (60 scenarios, 59 industries, real Claude Sonnet 5.5, independent grader with
`scripts/pi_eval_rubric.md`): old single-call generator 32/60 pass with 25 "no idea"; expert 91.7%
pass with no hard fail and 0 "no idea"; 12 industries outside the 211: 12/12 with two ideas.
Weak spots the grader named: first idea often a generic "ask customers why"; Industry correctness
and Currency are the lowest criteria; no referral to a vet, pharmacist or regulator in urgent cases.

## 6. Knowledge architecture (independent, with references)

| Source | Role | Can it limit pi? |
|---|---|---|
| Model reasoning (Claude) | the author of diagnosis and ideas | no |
| Sector briefings (`packs/currency`, 16 clusters, as of 2026-10) | what is current, what is outdated, local context, what not to assume | no, they inform |
| Industry packs and solution packs (211) | examples of level, wording, never-say lists, build phrases for the offer | no, examples only |
| Gold ideas (56, 28 trades) | examples of the right level | no |
| Learned lessons, idea scores | opt-in, frozen by default, reviewed weekly | no, and never above rules |
| Rules | constitution, linter, gates | yes, by design |

Unknown industry: the persona is given the owner's trade in their words; no pack lookup is required.
Industry detection still feeds sector notes and never-say lists when it succeeds.

**Gap to close:** the sector briefings are model-written and marked "needs human review"; a monthly
refresh job with a reviewer is not built.

## 7. Rules and where they are enforced

| Rule | Enforced in |
|---|---|
| First message says pi is an AI | constitution R-DISC-01, `with_disclosure` |
| One question, last sentence | R-VOICE, `repair`, rewrite |
| No product, document, quote, price while listening | R-SELL-01 (NO_OFFER states incl. S_RETURN, S_MAP_SHARE), decision gates |
| Offer once, for the whole set, only under R1-R3 or B1-B7 | `box.can_offer` (flag `box_offer`; with it off the whole-set offer follows the accepted summary) |
| No payment, card, OTP, password in chat | safety pre-gates, R-PAY |
| No medical, legal, tax, financial advice; emergencies stop the flow | safety.py, check_idea review |
| Roles not names; redact card, ID, phone, email | problems.redact, think_plan redaction, safety.redact_pii |
| Ideas: grounded, one sentence, no how-to, no promise | solution_rules.check_idea, idea_filter G1-G8, expert vetting |
| Handoff only when the owner asks | runtime._keyword_handoff, needs_person |
| Language lock | reply_language, language.py notices (en, roman_ur, ur, ar, hi, fa, fr, es) |

## 8. Solution delivery

ideas (free, 2 per problem) -> whole-set offer (R1-R3 or B1-B7) -> explicit yes gate -> Solution Box
(states collecting, ready, offered, drafting, in_review, sent, accepted, declined, changes_asked,
revised) -> a Workzap reviewer approves every document and quote (pi never prices) -> staff-confirmed
payment. B3/B4/B5/B7 signals are set from map confirm, ranking, voluntary problems and the dials.

**Pending owner decisions:** who reviews and prices the box and the service level (spec decision 9).

## 9. Dashboards

**Client (apps/pi, /customer).** Built: sign-in (WhatsApp code + Face ID/fingerprint, no
number-as-password), conversations, documents, requests, meetings, files, Map tab with timeline and
edit, Solution Box status, PWA. Partial: plain-language "what pi understood, what happens next" card,
translations of every label, mobile 375 px audit. Missing: nothing the spec forbids is added.

**Staff (Workzap).** Built: conversations, requests desk, health/self-test, drift key.
Missing (planned, not started): the review view with map, dials, the cached diagnosis, why the last
handoff happened and the cap usage; box review queue with offer-log rules; intent labels and live
alerts of spec 10.7.

## 10. Data and the SQL that runs against production

- Migrations are numbered by hand and applied by the owner by pasting `alembic upgrade A:B --sql`
  into Neon: now at `0049_pi_move_log`. Tables since 0047: `pi_map_versions`, `pi_solution_boxes`,
  `pi_offer_log`, `pi_move_log`, `pi_hypotheses`.
- Settings are merged with `jsonb ||` and never overwritten: `docs/pi-saas/enable-expert-workzap.sql`,
  `enable-map-thinking-workzap.sql`. Each has an undo.
- **Per-number reset** (`workzap-delete-one-number-*.sql`) must delete the five tables above before
  `pi_messages`: they point at messages, conversations and customers with RESTRICT (fixed 2026-10-27).
  Any new table with such a key must be added to every reset script in the same change.
- Production is only ever read by Claude Code (`SET default_transaction_read_only = on`).

## 11. Providers, cost and latency

- Order today: Anthropic primary (Claude Sonnet 5.5, effort medium), Gemini and Groq fallbacks.
  Gemini is on a free tier (rate limits; Google may use free-tier data): move to paid billing.
  Groq answers `invalid_request` to the full schema: not a useful fallback.
- A pi turn sends about 47,000 input tokens (spec text, rules, packs). That is the main cost and a
  latency floor. **Planned:** prompt budget (send only the sections for the state), prompt caching,
  a smaller model for the guards.
- Expert adds one diagnosis call per problem (cached) and, on a request for a fix, a judge call
  (median 6.5 s end to end). `expert_judge: false` skips the judge.
- Circuit breakers disable a provider after repeated failures; `AI_FAILOVER_ALL_CONFIGURED` is on.

## 12. Evaluation and operations

- `scripts/pi_expert_eval.py` + `pi_eval_scenarios.json` (60) + `pi_eval_rubric.md`: read-only,
  production keys loaded in memory, results graded by the `grader` agent, never by the same call.
- Local full-chat replay with the real model on a disposable database (scratch tests
  `test_zz_real_*`, never committed).
- Daily drift check (`drift_check`, off by default): 211 packs stored, retrieval probes, banned words.
- **Acceptance bar before turning a flag on for a workspace:** a graded run at 90% with no hard fail
  and no safety-scenario fail; then 5-10 real chats read by the owner; then watch `ai_usage_events`
  (purposes `pi_service`, `pi_expert_diag`, `pi_expert_judge`) and the handoff table for a day.

## 13. Status

| Area | State |
|---|---|
| Part A audit fixes, Part 14 removals | built, live |
| Dials, moves, hypotheses, plan schema (`thinking`) | built; **not proven with a real model**; off by default |
| Problem Map, portal, WhatsApp share, buttons, 8 languages | built (Hindi picture, Pashto and Sindhi wording partial) |
| Solution Box guards and signals (`box_offer`) | built; off by default |
| Expert advisor | built, live for Workzap, graded 91.7% |
| Sector briefings | built, need human review |
| Handoff keyword fix, voice rules, "kuch karo" ask | built, live |
| Diagnosis steering every question | partial (cached; turn 3 can still drift) |
| Idea cap per business across conversations | missing (per conversation today) |
| Hypothesis confirm/ignore from the owner's reply | missing |
| Staff review view, box queue, live alerts | missing |
| Prompt size reduction | missing |
| Real-chat acceptance for `thinking`, `map_share`, `box_offer` | not done |

## 14. Order of work (when building resumes)

1. **Acceptance of what is live:** the owner runs 10 real chats across industries; each weak reply
   becomes a scenario in the harness (the loop that found the keyword, effort and voice bugs).
2. **Question quality:** diagnosis steers every question; per-business cap; hypothesis updates.
3. **Staff review view** (the map and the dials are the handover briefing) and the box queue.
4. **Prompt budget** to cut cost and latency before more features are added.
5. **Languages:** Hindi font, Pashto and Sindhi wording, native-speaker review.
6. **Then, one at a time with real-chat acceptance:** `thinking`, `map_share`, `box_offer`.
7. **Knowledge upkeep:** monthly sector-briefing review, gold-idea review, drift check on.

## 15. Decisions that are the owner's

- Who reviews and prices the Solution Box, and how fast (spec decision 9).
- Move to paid Gemini billing and keep Anthropic primary (cost vs. rate limits and data use).
- Whether free ideas stay short (what and why) with the detail in the paid document: the current
  value-line design.
- Whether pi may name a concrete next step for "tracking" style requests (a location or visit
  system) before the offer, or only in the document.
