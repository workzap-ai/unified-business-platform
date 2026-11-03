# Q-3, Q-4, Q-5 design: the solution blueprint (root cause, options, feasibility, architecture)

Status: DESIGN DOCUMENT, 2026-10-31, branch `pi/q-blueprint-design`, base `origin/main` a7352e5. Docs only: no code, no
migration, no model call, no push. Nothing here is implemented. Status words as in the fast-track plan: planned,
implemented (merged), scripted-tested, real-model-verified. Nothing below is real-model-verified.

Labels used throughout: **EXISTING** (I read the code; cited `file:line` on a7352e5), **PROPOSED** (this design),
**UNKNOWN** (not read or not decidable from the repository). Spec citations are `spec-text/<file>` with PDF page
(`p`) and text line (`L`).

## 0. Scope and where it comes from

| Item | Plan text (`pi-fast-track-plan.md` section 9, lines 222-225) | This document |
|---|---|---|
| Q-3 | Root-cause quality criteria and labelled causes; "must improve solution quality, not add fields" | section 3 |
| Q-4 | Options comparison in the plan format; at least two real options with benefit, cost source, limit, risk; reviewer approves; "after the offer and the owner's yes; cost from staff, never priced by pi" | sections 3.5, 4 |
| Q-5 | Blueprint schema (entities, APIs, automation, dashboards, security, phases, risks, success criteria); "reconciled with P-1 and 0053 before implementation" | sections 5, 6 |

Level 2 text (as given in the task: "blueprint (modules, roles, permissions, APIs, entities, integrations, phases,
acceptance, rollback)", "cost always from staff, never priced by pi") is only partly in the repository:
`pi-core-intelligence-coverage.md:31` lists the Q-5 section names, and its "Conflicts" 1 to 6 (lines near the end) give the
price, wording and 2+2 conflicts that this design resolves. **UNKNOWN:** the term "OWNER APPROVAL hard gate" does not
occur in the repository (grep of docs and apps). Section 6.2 maps it to the three gates that do exist; the owner should
confirm that reading (decision D1).

Dependencies stated by the plan: FT-02 (Part 19), P-3 question Q1 (plan fields), P-1 reconciliation, B2a (on `origin/main`,
migration 0053). `part19.py` is **not** on `origin/main` (it is untracked in the shared tree); I did not read it, so every
statement about Part 19 behaviour below comes from spec v1.6 p223-225 only.

## 1. What exists today (read from code)

| # | Fact | Where |
|---|---|---|
| E1 | The document pipeline: owner yes recorded in `service_brief["offer"]` (`_prepare`), then `draft_offer` builds a solution document and a quote skeleton, both `status="in_review"`, `drafted_by="pi"`. Called from a staff route and from a job. | `decisions.py:731-751`; `brain_docs.py:601-774`; `brain_doc_routes.py:292-311`; `pi_saas/jobs.py:247` |
| E2 | The model writes only a `BoxDraft` (catalogue key, phase, problem refs; hypotheses, ideas, assumptions, wont_do, needs). Wording of each component comes from the approved catalogue in code. One retry with the issue list. | `brain_docs.py:108-122`, `:552`, `:661-673`; `solutions.py:26` (CATALOGUE), `:103` (`custom_build`), `:202` (fallback to `custom_build`) |
| E3 | Document rules in code: component maps to a problem (R-DOC-02), every problem addressed or in `wont_do` (R-DOC-03/04), no money (R-DOC-09, `MONEY_IN_TEXT`), no promise, no "will" (R-DOC-06), jargon, sentence length, reading grade 9 (R-DOC-05); box structure (value line, catalogue only, phases 1-4, clusters, order). | `brain_docs.py:60-67`, `:219-264`, `:286-328`; `box_doc.py:25`, `:286-317`; `box.py:148` |
| E4 | `blockers` is the approval gate: solution = `check_content` must be empty; quote = total, currency, valid-until, time estimate, included, not-included, bank account, phase prices. `approve` refuses while blockers exist, renders and stores the PDF, sets `approved_by/at`. Only approved versions can be sent. `edit` returns an approved document to review and clears approval. | `brain_docs.py:924-949`, `:992-1041`, `:1131-1145`, `:804-912` |
| E5 | The reviewer routes need `quotes.write` for edit, approve and revise (the same permission for all three). Each writes an audit event. | `brain_doc_routes.py:166-258` |
| E6 | The PDF prints only the content keys it reads (problems, clusters, links, ideas, phases, components, wont_do, order, needs, assumptions, naya). An extra content key is not printed. (From the `content.get` calls; I did not run it.) | `brain_pdf.py:172-261` |
| E7 | Documents and payments are **kept** when a customer is erased (they are counted as "kept"); problems, boxes and memories are deleted. | `brain_erase.py:520-545`, `:316-335`, `:361-412` |
| E8 | Owner approval of the quote is two-step (`approval_pending`, then a second yes), only for a contact who `can_approve`; expired quote escalates. | `decisions.py:763-826`; spec brain-v3 p29 R-DEC-01/02 (L3262-3270) |
| E9 | Flow: 28 `State` members (CLAUDE.md says 22; the enum has grown: `S_LISTEN_THINK`, `S_MAP_SHARE`, `S_BOX_OFFER`, `S_BOX_DRAFT`, `S_RETURN`, `S_HOLD` and others). `NO_OFFER` blocks documents in listening, hold, return, map share. `S_BOX_OFFER -> S_BOX_DRAFT -> S6_PREPARING -> S7_DELIVERED -> S8_REVIEW -> {S8b, S9, S9b}`; `S13_IN_BUILD` is terminal (no outgoing moves). `send` moves S6 or S8b to S7. | `flow.py:14-42`, `:50-54`, `:56-124`; `brain_docs.py:1221-1224` |
| E10 | Separate box lifecycle (collecting, ready, offered, drafting, in_review, sent, accepted, declined, changes_asked, revised); only staff move to `sent`; append-only `pi_box_transitions`. | `box.py:98-146`; `box_models.py:100-116`; `box_lifecycle.py:336-358` |
| E11 | Expert advisor: diagnose (up to 3 causes with `evidence_for` and `evidence_against`, one missing fact, one question, 5 candidate ideas), judge, deterministic vet. Returns `Advice(ideas, question, causes[names], problem)`. **Only cause names, the problem and the question are cached** (redacted) in `service_brief["expert_diag"]`; evidence is dropped. | `expert_advisor.py:1-23`, `:240-273`, `:304-315`, `:468-522`, `:657-734`, `:850-871` |
| E12 | One question rule for expert questions: one sentence, one question mark, no solution word, no digits of 3+, no personal-data ask. `same_as_any` stops a repeat; `need_fact_line` is the "one more fact" reply when no idea survives. | `expert_advisor.py:432-441`, `:924`; `idea_filter.py:398` |
| E13 | Idea filter G1-G12 is pure code; G10 `feasibility.check` rejects an idea the owner's stated size cannot carry (people, sites, hours), only when `IdeaContext.resources` is set. `IdeaContext` has `cause` (the owner's belief), no constraints. | `idea_filter.py:143-160`, `:316-336`; `feasibility.py:1-12` |
| E14 | B2a fields (merged, migration 0053, deferred columns): `constraints {budget,staff,deadline: {text,msg}, cannot_change: [{text,msg}]}`, `tried [{what,outcome,msg}]`, `cause {text,status,evidence{msgs,words}}` with status `pi_inferred / owner_said / confirmed`, `expected_outcome`. `owner_said` needs whole-word evidence in the owner's own message; every text goes through `redact_pii` and `third_party.protect`. There is **no assumed/confirmed status on a constraint**: an entry exists because the owner said it (`msg`). | `problem_fields.py:7-26`, `:36-60`, `:84-133`; `problems.py:36`; `migrations/versions/0053_pi_problem_requirements.py` |
| E15 | **The B2a fields are not read by anything that builds a document or an idea.** `noted_context` returns `cause: person_believes_cause`, not the new columns; `draft_offer` passes `cause = person_believes_cause`; `IdeaContext` has no constraint field. (grep of `constraints` in `brain_docs.py`, `box_doc.py`, `expert_advisor.py`, `idea_filter.py`, `solution_*.py`, `decisions.py`, `service_conversation.py` found no read.) | `problems.py:989-1060`; `brain_docs.py:658-660` |
| E16 | FT-A3 scripted relevance scorer is merged: verdicts `relevant, irrelevant, generic, violates_constraint, restates_owner`; a CONFIRMED limit breaks an idea whatever its link score; "no idea" is valid (`pick_ideas` never pads); `score_case` reports `hard_misses`. Limits in cases are `{kind, text, blocks[], status}`; `blocks` are fixture data. Matching is stem-based, no negation, no spelled-out numbers; it agreed 55% with an independent grader on the borderline set. | `evalkit/relevance.py:1-40`, `:43`, `:215-252`, `:297-311`, `:314-362`; `evalkit/relevance_match.py` header |
| E17 | FT-C1 (relevance in code in `idea_filter.py`/`expert_advisor.py`) is **planned, not built**; `evalkit` is lane E's. | plan line 78; the greps in E15 |
| E18 | P-3 design already defines Layer A (reads today's fields) and Layer B (steps, dependencies, roles, next action; B5 constraint hard failure). | `pi-p3-plan-completeness-design.md` sections 1-2 |
| E19 | Owner OS platform modules that exist as code: `customers, orders, inventory, finance, hr, sales, quotes, reports, integrations, workspace_agent, products, catalog, pi, pi_saas`. Permission keys seen: `quotes.write`, `sales.read`, `pi.read`, `pi.handoffs.manage`. **UNKNOWN:** the full permission list and what each module exposes; I did not read them. | `apps/api/app/modules/*`; `brain_doc_routes.py:162`, `:168`; `pi/service.py:59`, `:306` |

Spec anchors used (all v1.6 unless stated):

- Hypothesis ledger: p161 L7642-7653 (hypothesis, evidence for, evidence against, confidence, cheapest test, status open / confirmed by the owner / dropped; "never builds the Solution Box on an unconfirmed hypothesis without labelling it").
- Box: p171 L8003-8040 (eight sections; section 4 "from the approved catalogue only"), p172 5.3 lifecycle, p172-173 5.4 readiness and R1-R3, p173 5.5 (pi drafts sections 1 to 7, staff review, edit, price section 8, approve), p174 5.7 guards (canOffer, boxState, valueLine, catalogue, noMoney).
- Ideas cap: p201 L9472 (Book 5 decision 5: 2 per problem, up to 8 per business before the offer).
- Documents: brain-v3 p27 L3072-3147 (R-DOC-00 reviewer approval mandatory; R-DOC-01..09), p28 L3149-3248 (R-QUOTE-01 prices only from Workzap; solution families including `custom_build`, `integration`, `erp_nori_platform`, `workflow_automation`), p29 R-DEC; p419 L37402 ("keep the solution document proportionate (R-DOC-02)").
- Build wording: p129-130 L5957+ (RBUILD01 say what they would notice; do not use "dashboard, system, software, platform, ERP, module, automation, integration, CRM, portal, analytics, app" unless the owner did; RBUILD06 "would", never "will").
- Part 19: p223-225 L10434+ (buying signals R1/R3 start the quote; no price from pi; "aap ye sab kar denge" answered honestly).

## 2. The two outputs and the one rule that shapes both

The blueprint has two views of one record, because two rules collide.

- **Owner view.** Plain sentences, catalogue wording, "would", no price, no jargon (R-DOC-05/06/09, RBUILD01). It is the existing Solution Box. Section 4 may use only catalogue items (p171, p174). `custom_build` is in the catalogue (`solutions.py:103`), so a custom automation is described there "specifically, in the who gets what, when style".
- **Staff view (technical annex).** English, structured: modules, roles, permissions, entities, APIs, integrations, automations, phases, acceptance, rollback. It exists for the reviewer's judgement and for Level 3 task creation. It uses the words the owner view must not use, so it is **never rendered into the owner PDF and never quoted in chat** (E6 shows the PDF ignores unknown keys; S7 adds a test that a blueprint key is absent from the PDF text).

Nothing in the technical annex is a promise: it is "what staff would need to confirm", not a commitment.

## 3. Q-3: the root-cause record and the options record

### 3.1 What a Level 2 blueprint is, as a stored record

One record per customer offer (one per `offer_id`), versioned like the document. It has four parts. Parts A to C exist
for every blueprint; part D only when the options include a build or a custom automation.

- **A. Analysis, one entry per problem ref** (root cause, evidence and hypotheses kept apart).
- **B. Options, compared** across the offer's problems.
- **C. Recommendation** (smallest reliable option first), constraint results, what is left alone.
- **D. Architecture** (section 5).

### 3.2 Part A shape (PROPOSED)

```
analysis[problem_ref] = {
  "symptoms":   [{"text", "msg"}],                 # what the owner saw, in their words (redacted)
  "facts":      [{"text", "msg", "kind": "stated"}],   # numbers, tools, roles the owner said. Only "stated".
  "tried":      copy of problems.tried (B2a),  "constraints": copy of problems.constraints (B2a),
  "expected_outcome": copy of problems.expected_outcome (B2a, owner's words),
  "root_cause": {                                  # ONE field, status decides how it may be used
      "text", "status": "confirmed" | "owner_said" | "hypothesis" | "unknown",
      "evidence": {"msgs": [...], "words": [...]}  # same shape as problem.cause.evidence (E14)
  },
  "hypotheses": [{"id", "text", "for": [{"msg","words"}], "against": [{"msg","words"}],
                  "confidence": "low"|"medium"|"high", "cheapest_test": "<one question>",
                  "status": "open"|"confirmed"|"dropped"}],        # spec p161, same six fields
  "factors":   {"operational","financial","technical","human"}: optional short text each (coverage list, not a score),
  "conclusion": "confirmed" | "provisional" | "cannot_conclude_yet",
  "next_question": {"text", "would_change": "<option id or ranking>"} | null
}
```

Rules, all enforced in code (PROPOSED function `blueprint_rules.analysis_issues`):

1. **Evidence and hypothesis are separate fields.** A hypothesis never writes into `root_cause.evidence`. `root_cause.status` is copied from `problem.cause.status` (E14) when the owner said it; otherwise it is `hypothesis` or `unknown`. A model can never raise a status.
2. `confirmed` and `owner_said` need evidence by the existing B2a proof (whole words in the owner's own message). A hypothesis `for` entry needs the same: words must occur in an owner message. A hypothesis with an empty `for` list is stored as `status: open` with `confidence: low` and cannot be the basis of a recommendation.
3. **Conclusion function (pure):** `confirmed` if `root_cause.status` is owner-stated and no `against` unresolved; `provisional` if at least one hypothesis has `for` evidence and none is stronger against; else `cannot_conclude_yet`. A `provisional` conclusion is **printed labelled** in section 2 and section 7 of the box ("may", "could"; p161: never build on an unconfirmed hypothesis without labelling it). The existing `apply_box` hypotheses and `unconfirmed()` already carry such labelled lines (`brain_docs.py:404`; `box_doc.py:197`).
4. **Insufficient evidence means one targeted question or an honest "cannot conclude yet".** If `conclusion == cannot_conclude_yet`: before the offer, the existing expert question path supplies the one question (`question_ok`, `same_as_any`, `need_fact_line`: E12), as the last sentence. At document time (the owner already said yes) the blueprint must not invent a cause: the document says what is not yet known under "Assumptions and open questions" (box section 7) and the recommended option is limited to ones that work whatever the cause is (the expert prompt already has that rule: `expert_advisor.py:127-128`) or to "learn the cause first". If the question was already asked (same_as_any) or the cap is reached, the honest statement replaces the question. No cause is stated as fact.
5. **Not more fields for their own sake (plan acceptance).** The only new stored items versus E11 are `evidence_for/against` (already produced by the advisor and then discarded) and the `cheapest_test`. Everything else is copied from B2a.

### 3.3 Quality criteria for a root cause (Q-3 "criteria and labelled causes", lane E, PROPOSED)

A labelled case marks, for each problem: the allowed cause classes (a set, not one answer: "one right cause is not true for a business problem", P-3 design section 2), the facts that make each class supportable, and the correct conclusion state. Criteria, each checkable without a model:

| Criterion | Check |
|---|---|
| C-1 Supported | every cause with status above `hypothesis` has owner-message evidence (zero unsupported causes on every split; the same bar as the B2a row, plan line 74) |
| C-2 Separate | no hypothesis text appears as `root_cause` unless status allows it |
| C-3 Both sides | where the case lists a contradicting fact, it appears in `against` |
| C-4 Factors named | the case's required factors (financial, human, ...) are present, or marked "not known" |
| C-5 Right state | `conclusion` equals the label (confirmed, provisional, cannot conclude) |
| C-6 Question moves the answer | the `next_question` changes at least one option's status in the case (Q-2 link; not built here) |

Agreement with human labels follows the P-2 method (at least 20 samples, two reviewers, a third adjudicator, the 85% bar is the owner's decision; `evalkit/human_review.py` header). Scripted results are labelled "scripted", never "AI quality". The `grader` agent is a model and not independent human truth (plan conflict 7).

### 3.4 Part B: options, compared (PROPOSED shape)

```
options[] = {
  "id": "O1", "kind": "owner_action" | "process_change" | "workzap_build" | "custom_automation" | "learn_first",
  "what": "<one plain sentence, what the owner would notice>",   # catalogue wording for builds (RBUILD01)
  "catalogue_key": "stock_alerts" | ... | null,                    # required for workzap_build, custom_build for custom
  "addresses": ["P1","P3"], "works_on": ["h1"],                    # problems; hypothesis ids it relies on
  "benefit": "<what the owner would see or know; no figure, no promised result>",
  "fit": {"problem_link": [...refs], "facts_reused": [msg ids], "generic": false},     # filled by code (FT-C1)
  "limits": ["<what it does not change>"],                         # becomes wont_do / not_included lines
  "trade_offs": ["..."],
  "dependencies": [{"kind": "owner_input|access|data|person|other_option", "text", "blocking": bool}],
  "risks": [{"text", "level": "low|medium|high"}],
  "constraint_checks": [{"constraint": "budget|staff|deadline|cannot_change#2|tried#1", "result": "ok|violates|unknown", "why"}],
  "footprint": {"modules": n, "integrations": n, "roles": n, "automations": n},    # computed in code, not by the model
  "cost": {"source": "staff", "amount": null},                     # always null from pi
  "status": "recommended" | "alternative" | "rejected", "rejected_because": "..."
}
recommendation = {"option_id", "why": ["<reason citing a fact or constraint>"], "order": [...]}
```

Rules:

- **At least two options** are compared in every document where the conclusion is not `cannot_conclude_yet`; a `rejected` option with a reason counts as compared (plan Q-4 acceptance: "at least two real options with benefit, cost source, limit, risk"). `learn_first` and "do nothing yet" are valid options; "no option" is a valid result (FT-C1: never fill a quota).
- **Cost source is a field, the amount is never pi's.** `cost.amount` is null in every pi-written blueprint; `cost.source` is the string `staff`. The quote, priced by the reviewer per phase, is the only place with money (`edit` phases price: `brain_docs.py:863-872`; `blockers` quote checks `:929-948`). `MONEY_IN_TEXT` runs over every blueprint string (`brain_docs.py:60`).
- **Smallest reliable option first** (deterministic order, PROPOSED `rank_options`): drop `violates`; then prefer options with no blocking dependency, then lower `footprint` total, then higher FT-C1 link score; `unknown` constraint results rank after `ok` and are flagged for the reviewer. `reliable` is derived from code facts (conclusion not `cannot_conclude_yet`, no blocking dependency on an unconfirmed fact, catalogue key present), not from the model's confidence.
- **Constraint-aware** (budget, staff, deadline, cannot-change, tried): section 4.
- **Where it shows.** Not in free ideas (cap 2 per problem, 8 per business, p201; value line `box.py:148`). The comparison appears only in the solution document, after the offer and the owner's yes (S_BOX_DRAFT), for reviewer and owner (decision D3 on how much of the rejected set the owner sees).

## 4. Q-4: feasibility checks in code, and how FT-C1 and FT-A3 feed them

### 4.1 Order of checks (PROPOSED `option_gate.evaluate(option, record)`)

1. **Hard gate (reject, whatever the score).** A violated owner-stated constraint rejects the option: `cannot_change` text broken by the option, an attempt in `tried` that failed repeated as the option, a budget or deadline ceiling the option's own footprint plainly exceeds. Result `violates`; the option is stored `rejected` with the constraint named. No score can rescue it. This is the plan's FT-C1 rule ("a violated confirmed constraint rejects the idea whatever its score").
2. **Hard gate: stated size** (G10): the existing `feasibility.check(text, resources)` (people, sites, hours; `idea_filter.py:325`; E13), now also run on builds that need a named person, an on-call role or a site per branch.
3. **Dependency gate:** a `blocking` dependency on something the record shows is absent (an account, data, a person) marks the option `not_ready`: it stays visible as an alternative with the dependency named and cannot be `recommended`.
4. **Rule gate:** the existing document rules on the option text (E3): money, promise, "will", jargon, third-party names, credentials.
5. **Score (ranking only):** FT-C1 relevance (problem link, fact reuse, minus generic) orders what survived.

`unknown` is a real answer: the matcher cannot parse a constraint text (E16 limits). An `unknown` never rejects and never silently passes: it is listed to the reviewer as "could not check: <constraint>".

### 4.2 Feeding from FT-C1 and FT-A3

- **FT-A3 is the specification and the test of the scorer** (E16): same verdicts, same hard-miss rule. Its fixture limits carry `blocks` and `status`; production constraints do not (E14: `{text, msg}`, no status, no `blocks`). So the production gate cannot read `blocks`; it must derive rules from the text with the same pure helpers (`relevance_match.parse_rules`, `rule_hit`, `ceilings_of`, `over_ceiling`) and treat every B2a constraint as confirmed (the owner said it). **Gap, PROPOSED fix:** move these helpers into a production module (`constraint_check.py`) that `evalkit/relevance.py` imports back, so production does not import eval code and lane E keeps its tests; or import read-only from evalkit and accept the layering. Decision D4.
- **FT-C1 is the producer** of `problem_link` and `fact_reuse` for ideas; Q-4 reuses the same function for options so one definition of "relevant" exists. FT-C1 is not built (E17), so Q-4 S4 waits for it, or ships the hard gate alone first (section 11).
- **Honest limit of the scorer.** The matcher agreed 55% with an independent grader on the borderline set (E16). A hard reject on that basis is acceptable only because a false reject costs a visible alternative (the reviewer sees it with its reason), while a false accept is caught by the reviewer's gate and by `unknown` flags. Hence: the gate may reject, but the reviewer can restore a rejected option with a recorded reason (PROPOSED, decision D5); pi never does.

### 4.3 Wiring B2a (the missing read, E15)

Today nothing reads constraints. PROPOSED: a loader in the blueprint module reads the four deferred columns for the offer's problems with the existing `REQUIREMENT_COLUMNS` pattern (`problems.py:36`, `:500`), so `noted_context` and `IdeaContext` are not widened (hot file avoidance). `IdeaContext` gets a constraint field only in a later, separate step if the owner wants the same gate on free ideas (decision D6).

## 5. Q-5: the software and automation blueprint (part D)

Used for two products, one schema: **Owner OS platform product** (configure or extend existing modules, E19) and **custom automation** (`custom_build`, `workflow_automation`, `integration`; brain-v3 p28 families). `architecture.scope` is `owner_os_platform | custom_automation | mixed`. Proportionate by rule: modules and phases are capped (box caps 8 components, 4 phases: `brain_docs.py:113`, `box_doc.py:25`) and an `oversize` check compares footprint with the owner's stated size (brain-v3 p419 L37402: do not propose systems sized for a much bigger company).

```
architecture = {
  "scope": "...",
  "modules":   [{"id","name","purpose" (plain), "catalogue_key", "owner_os_module": "inventory"|"orders"|...|null,
                 "build": "configure"|"extend"|"new", "problems": [...], "phase": 1-4}],
  "roles":     [{"id","role" (role name only, never a person), "does",
                 "permissions": ["<existing permission key>" | {"new": "<proposed key>"}]}],
  "entities":  [{"id","name","fields":[{"name","type","pii": bool}],"relations":[...],
                 "owner_os_table": "<existing>"|null, "retention_note"}],
  "apis":      [{"id","direction":"inbound|outbound|internal","purpose","owner_os_route": "<existing prefix>"|null,
                 "auth": "<scheme, never a secret>","entities":[...],"idempotent": bool}],
  "integrations":[{"id","system": "<category or owner-named>","mode":"read|write|sync",
                 "existing_connector": "<name from CONNECTORS.md>"|null,"owner_provides":[...],"failure_mode"}],
  "automations":[{"id","trigger","condition","action","actor_role","notify_roles":[...],
                 "human_in_loop": bool,"external_effect": bool}],
  "dashboards":[{"id","audience_role","answers":"<question it answers>","entities":[...]}],
  "security":  {"pii_entities":[...],"access_rules":[...],"audit_events":[...]},
  "phases":    [{"n","name","modules":[...],"depends_on":[...],"entry":"...","exit":"..."}],
  "acceptance":[{"id","about":"<module|automation id>","given","when","then","verified_by":"staff|owner|test","problem":"P1"}],
  "rollback":  [{"for":"<phase|module id>","how","data_impact","decided_by_role"}],
  "dependencies":[...], "risks":[...], "open_questions":[...]
}
```

Rules (code, PROPOSED `architecture_issues`):

- Every module has at least one problem ref and a catalogue key (R-DOC-02; `box_doc.structure_issues` already enforces catalogue keys at `:286-317`). A module with `build: new` and no `owner_os_module` requires `catalogue_key = custom_build`.
- Every entity, API, integration, automation and dashboard names the module it serves; none is orphaned. Every `external_effect: true` automation has `human_in_loop: true` (no autonomous external action; Q-8 boundary, plan line 228).
- Every phase has an entry and an exit; every acceptance item names a problem and a verifier; **every module and phase has a rollback item** (Level 3 needs it: "every action has an approval and a rollback", plan line 228).
- `permissions` use existing keys; a `{"new": ...}` key is flagged for staff, never silently created. Roles are role names (E14 redaction; `third_party.protect`).
- `owner_provides` and `auth` never hold a password, OTP, card or secret; the existing needs rule says access is "arranged at kickoff" (brain-v3 p27, section 5 of the document). A credential word in any field fails the check.
- Blueprint phases are the box phases (`MAX_PHASE = 4`), so the quote's phases (`box_doc.quote_phases`, `:239`) are priced one per phase by the reviewer.
- Integrations name an existing connector where one exists (`docs/pi-saas/CONNECTORS.md`); a missing connector is an open question, not an invention. **UNKNOWN:** which connectors and Owner OS routes cover each module; S6 includes a read-only capability read before any `owner_os_module` mapping ships.
- Dashboards: RBUILD02 (actions before views); a dashboard module needs a problem about not seeing (`solutions.VIEW_BUILDS`, `solutions.py` near the catalogue).

### 5.1 Owner view derived from the architecture

Each module renders as one catalogue sentence (`catalogue_text`, `box_doc.py:62`), one build per sentence, never a feature list (RBUILD05). The owner never sees API, entity, integration or module words unless they used them first. Phase names stay plain ("Get the numbers you need each morning").

### 5.2 Overlap with FT-ART2

FT-ART2 (plan line 79) makes a system request with several modules one Solution Box with a section per module, and adds budget-ready and cannot-change lines. That is the owner view; Q-5 is the staff annex behind it. They share `box_doc.py` and `brain_docs.py`; S6 must land after FT-ART2 or be coordinated with its lane. **UNKNOWN:** `system_ask.py` named in the plan does not exist on `origin/main`.

## 6. From blueprint to the approved document; the gates; Level 3

### 6.1 Flow of the record

1. Listening (`S_LISTEN_THINK` and earlier): Part A is computed in memory or stored internally; only one targeted question or the existing free ideas (cap 2, filter G1-G12) may reach the owner. No option, module, document or price (`NO_OFFER`, `flow.py:54`; `can_offer`, `box.py:43`).
2. Offer and yes (R1-R3 or B1-B7, spec p172-173): `_prepare` records the yes (`decisions.py:731`). Only now may the blueprint be written.
3. Drafting (`S_BOX_DRAFT`): `draft_offer` gains one structured call that proposes options and the architecture, after code has built Part A. Code validates (sections 3-5), one retry with the issue list (the existing attempt pattern, `brain_docs.py:661-673`).
4. The snapshot is stored in the solution document content (`content["blueprint"]` for the reviewer-visible record; owner text in the existing keys). `review_notes` carries every `unknown`, `not_ready`, rejected option and `provisional` conclusion (the field already carries issues: `brain_docs.py:746`).
5. Review (`S6_PREPARING`): the reviewer edits (`edit`), prices the quote per phase, approves (E4, E5). Editing clears approval (`:909-911`), so the approved snapshot is exactly what is sent; S5 adds a snapshot hash to detect a blueprint edited outside the document.
6. Send, owner reads (`S7`, `S8`); changes requested go to `S8b` and a revision, which creates a new document version and a new blueprint version (`revise`, `:1044`).

### 6.2 The approval gates (reading of "OWNER APPROVAL hard gate", decision D1)

| Gate | Who | Where enforced today | What Q-3/4/5 adds |
|---|---|---|---|
| G-A Owner says yes to the offer | owner | `decisions.py:731-751`, `box.can_offer` (`box.py:43`) | blueprint not written before it |
| G-B Reviewer approves document and quote | Workzap reviewer, `quotes.write` | `blockers`/`approve` (`brain_docs.py:924-1041`); R-DOC-00 (brain-v3 p27 L3098) | blueprint rules join `check_content`; an unresolved `unknown` must be acknowledged by the reviewer before approve (PROPOSED field `reviewer_ack`) |
| G-C Owner approves the quote, two confirmations, `can_approve` | owner contact | `decisions.py:763-826`; R-DEC-01/02 (brain-v3 p29) | none; a build or task never starts on G-B alone |

Risk, from code: edit, approve and revise share `quotes.write` (E5) and the capability backlog flags that one user can approve their own quote (BL-08, SUSPECTED, not verified by me). For a technical blueprint a second sign-off is attractive (decision D2). pi can never move any of these states: only staff move a box to `sent` (`box.py:127-142`).

### 6.3 Level 3 hand-off (Q-8) and P-6

Boundary from the plan (line 228): no autonomous external actions, payments, bookings, messages, production changes or irreversible actions; every action has an approval and a rollback; an action record exists before any "done" claim.

- **Tasks are generated from the approved blueprint, not by pi.** PROPOSED: each `phase`/`module`/`automation` of the approved snapshot becomes one staff task record: `{blueprint_id, version, item_id, approved_by, approved_at, rollback_ref, acceptance_ref, evidence_ref}`. Tasks exist only after G-C and staff-confirmed payment (`S11`), and the flow already has a place: `S12_KICKOFF -> S13_IN_BUILD` (`flow.py:115-117`). `S13` is terminal, so progress reporting cannot be a new flow move; it is records plus P-6.
- **P-6 evidence.** A claim such as "started", "done", "delivered" needs a record (P-6 design, claim table C7, C11). Blueprint `acceptance` items are the checkable definition of "done"; a task is complete only when its acceptance evidence row exists. The P-6 design says P-4 and P-6 must share one read-only `claim_evidence` function (`pi-p6-evidence-claims-design.md` section 3, decision list item 3); the blueprint adds no second evidence function.
- Out of scope here: the task table, the executor and the reporting UI (Q-8 is its own design).

## 7. Data model proposal

Principle: additive only, nothing old rewritten, tenant and environment scoped through `WorkspaceRow` and `scoped_fk` like every neighbour (`brain_docs_models.py:39-60`).

### 7.1 Option A (recommended): snapshot in the document, working record in a new table

**Table `pi_blueprints`** (PROPOSED; migration number assigned at S2 after `alembic heads`; 0054 is reserved to lane U for a possible P-4 ledger, plan line 153 of the P-1 review).

| Column | Type | Note |
|---|---|---|
| tenant_id, environment_id, id, created_at, updated_at | from `WorkspaceRow` | scope; every query filters both (`mine(...)` pattern in `brain_erase.py`) |
| customer_id | uuid, scoped FK to `customers` | erase key |
| offer_id | uuid | joins to `pi_brain_documents.offer_id` |
| conversation_id | uuid null | |
| version | int, default 1 | unique with (tenant, environment, offer_id) |
| status | `draft` / `in_review` / `approved` / `sent` / `superseded` | mirrors `brain_docs_models.STATUSES` (`:31`) |
| analysis | JSONB | part A |
| options | JSONB | part B, C |
| architecture | JSONB null | part D |
| source_msgs | JSONB list | message ids the evidence points at (for erase and audit) |
| document_id | uuid null, scoped FK to `pi_brain_documents` | the solution version that carries the snapshot |
| snapshot_sha | text | hash of the snapshot at approval |
| issues | JSONB list | `unknown`, `not_ready`, `rejected` for the reviewer |
| redacted | bool | true after the redaction pass |

Checks: `status IN (...)`, `version >= 1`. One index on (tenant, environment, customer_id). **Why a table and not only document content:** the analysis is needed before any document exists (hypotheses survive turns and chats, `expert_diag` drops them: E11), and documents are **kept** on erase (E7), so a blueprint inside the document would keep the owner's words after an erase. The table is deleted with the customer; the document snapshot keeps only what the retention decision (R1-R6, `pi-decision-retention-review.md`) allows. **UNKNOWN:** whether a retained document may keep evidence quotes; decision D7.

### 7.2 Option B: no new table

Store everything in `content["blueprint"]` of the solution document, hypotheses in `service_brief`. No migration, nothing for lane U to collide with, but the analysis does not exist before the yes, evidence is lost across chats, and erase keeps owner words in documents. Acceptable only for a first scripted step (S1-S5 need no storage at all, section 11).

### 7.3 Erase, redaction, isolation (both options)

- **Redaction before storing:** every owner-derived string goes through `problem_fields.clean` (`redact_pii` then `third_party.protect`, then cut: `problem_fields.py:52-60`) and the model's restated text through the same redactor used by `expert_advisor.remember` (`:862-866`). Roles only, never a third-party name (non-negotiable; plan conflict 2 depends on the FT-02 role-conversion fix being merged first; **UNKNOWN** whether it is).
- **Erase:** add `pi_blueprints` rows to `brain_erase.erase_customer` (delete by `customer_id` inside the tenant and environment filter) and add a "kept" count for the document snapshot like `documents` and `payments` (`brain_erase.py:520-545`). The erase gap list (`pi-erase-gaps-g1-g14.md`) must not grow: S2's acceptance includes an erase test.
- **Isolation:** two-tenant tests as for 0053 (a blueprint of tenant A is invisible to tenant B and to another environment).
- **Order of deployment:** same rule as 0053: apply the migration before code that writes the table; the loader tolerates a missing table behind a setting (PROPOSED flag `response_rules.brain.blueprint`, default off, same style as `box_offer`, `box.py:85`).

## 8. State machine placement

PROPOSED: **no new `State` member and no new legal move.** The blueprint rides existing states.

| Step | State | Legal move used (existing) |
|---|---|---|
| Part A computed, one targeted question | `S_LISTEN_THINK` | self; `S_LISTEN_THINK -> S_BOX_OFFER` only through `can_offer` (`flow.py:79-90`) |
| Offer made and answered | `S_BOX_OFFER` | `-> S_BOX_DRAFT` on yes (`flow.py:96-98`) |
| Blueprint drafted, validated | `S_BOX_DRAFT` | `-> S6_PREPARING` (`flow.py:100`) |
| Reviewer edits, prices, approves | `S6_PREPARING` | `send` moves to `S7_DELIVERED` (`brain_docs.py:1221-1224`) |
| Owner reads, asks, changes | `S7`, `S8_REVIEW`, `S8b` | `S8b -> S7` after a revision (`flow.py:108-110`) |
| Owner approves quote, payment, kickoff | `S9`, `S10`, `S11`, `S12` | unchanged |
| Tasks (Level 3) | `S12 -> S13_IN_BUILD` | none added (`S13` terminal, `flow.py:117`) |

Box lifecycle (E10) aligns: `drafting` (blueprint written), `in_review`, `sent`, `revised` (blueprint version +1); `box_lifecycle.on_draft_ready` is already called at the end of `draft_offer` (`brain_docs.py:771-773`). Blueprint `status` follows the document's, never leads it. A returning owner (`S_RETURN`), `S_HOLD` and the exceptions keep `NO_OFFER`; nothing from the blueprint is said there.

## 9. Non-negotiables: where each is enforced, and what is added

| Rule (CLAUDE.md) | Enforced today (code) | Blueprint adds |
|---|---|---|
| First message says AI | `flow.OPENING` (`flow.py:197-203`) | none |
| One question, last sentence | expert `question_ok` (`expert_advisor.py:432`), reply linter (`constitution.py`, not re-read) | `next_question` must pass `question_ok`; at most one per message; never asked twice (`same_as_any`) |
| No product, document, quote or price while listening; "ok/hmm" is not yes; free ideas capped 2/problem, 8/business | `NO_OFFER` (`flow.py:54`), `can_offer` (`box.py:43`), `value_line` (`box.py:148`), idea filter (`idea_filter.py:316`) | options and architecture exist only after yes (G-A); comparison only in the document; no option text in chat before then. The 2+2 cap is untouched (core-intelligence conflict 3) |
| No payment in chat; bank only in approved PDF; "received" only after staff | `blockers` bank check (`brain_docs.py:942`), `PiBrainPayment` staff-only confirm (`brain_docs_models.py:93`) | credential/secret/bank words fail `architecture_issues`; blueprint never prints a bank detail |
| Reviewer approves every document; pi never prices | `approve` and `blockers` (`:924-1041`); R-QUOTE-01 | `cost.amount` null by validator; `MONEY_IN_TEXT` over every field; acceptance of the quote unchanged |
| No legal, medical, financial, tax advice; emergencies stop the flow | `safety.py`/`safety_guard.py` pre-model gates; expert persona rule (`expert_advisor.py:61-64`) | regulated-industry blueprints carry a `compliance_flag` for the reviewer and propose no advice; **UNKNOWN** exactly which `safety.py` function to reuse (S2 reads it) |
| Roles, never third-party names; redact before storing | `problem_fields.clean`, `third_party.protect` (`problem_fields.py:52-60`) | applied to every stored string; `roles[].role` and `entities` are role names; validator rejects a name pattern |
| Branding Workzap only; British spelling | R-DOC-08; style lints (**UNKNOWN**, `style.py` not read) | owner view uses catalogue wording only; S7 test checks British spelling on blueprint-derived text |
| Rules in code, learned content is data below the rules | linter, state guards, decision gates | the model proposes, `blueprint_rules` disposes; no blueprint field is learnable; learning stays frozen unless `learning_frozen` is exactly false (CLAUDE.md) |
| R-DOC-02..09 | `check_solution`, `check_content` | blueprint-derived owner text passes the same functions; the technical annex is checked by its own validator and is never printed (E6) |

## 10. Test plan

Unit (no database; new files, none sharing a name with an integration file):

- `analysis_issues`: unsupported cause, hypothesis promoted to `root_cause`, empty `for`, evidence not in owner message, conclusion function (every branch), status never raised.
- `option_gate`: violated `cannot_change`, repeated failed attempt (`tried`), budget ceiling, G10 size, `unknown` flagged not rejected, rejection independent of score (a perfectly relevant option that breaks a constraint is rejected), `rank_options` order (smallest reliable first), two-option minimum, `learn_first` valid.
- `architecture_issues`: orphan entity/API, module without problem, `external_effect` without human in the loop, missing rollback or acceptance, credential word, money in any field, new permission flagged, oversize.
- Redaction: card, ID, phone, e-mail, third-party name in every stored field.
- Negative controls copied from P-3 section 4 (empty plan, wrong industry, padded plan, constraint violator that scores well elsewhere), each in English and Roman Urdu at least.

Integration (disposable database only, `. ../../scripts/pi-test-env.sh`):

- two-tenant and two-environment isolation of `pi_blueprints`; erase deletes the rows and counts the kept snapshot; migration up and down, single head.
- `draft_offer` with the flag off produces today's document byte for byte (regression); with it on, snapshot present, owner PDF text contains no blueprint key words (module, API, entity, integration).
- `approve` refuses with an unacknowledged `unknown`; `edit` after approval clears approval and the snapshot hash changes.

Scripted scenario: one multi-module system request (the Artwing shape: eight modules, budget ready, one cannot-change line) through listening, offer, yes, draft: asserts no price in chat, one question maximum per message, options shown only after yes, every module in the document, rejected option has its reason, S6 hand-over text. Scripted, not a model measure.

Evalkit measures (lane E; all labelled "scripted"; thresholds are the owner's, none invented here, in the style of `pi-eval-thresholds-proposal.md`):

| Measure | Definition | Hard rule |
|---|---|---|
| M1 root-cause accuracy | state agreement with human label (confirmed / provisional / cannot conclude) and cause-class match | unsupported conclusions = 0 on every split; agreement bar per P-2 |
| M2 problem-linked relevance | FT-A3 verdict per option, grouped by language and industry | below-minimum cells reported "not yet measured" |
| M3 feasibility | `hard_misses` (expected `violates_constraint`, got other) | 0; false-reject rate reported |
| M4 constraint compliance | share of recommended options violating no stated constraint | 100% on cases; `unknown` counted separately |
| M5 architecture completeness | per element present/absent (modules, roles, permissions, entities, APIs, integrations, phases, acceptance, rollback), never one blended number | an industry is "verified" only with D5 minimum cases (P-3) |

Real-model runs need separate cost approval (plan P-5, Q-11); nothing here asks for one.

## 11. Staged delivery (small, independently mergeable; each default-off)

Hot files: `service_conversation.py` (7768 lines; expert hooks at `:1488`, `:1673`, `:2776-2830`), `problems.py`, `decisions.py`, `part19.py` (not on main). The plan keeps B2a/FT-REQ/P-6 behind FT-02 on those files. **No step below edits a hot file except S5 (`brain_docs.py` is not hot) and the optional S9.**

| Step | What | Files touched | Conflict risk with hot files | Acceptance | Rollback |
|---|---|---|---|---|---|
| S1 | Shapes and pure validators for parts A, B (`analysis_issues`, conclusion function, `rank_options`); fixtures only | new `blueprint_models.py` (pydantic), `blueprint_rules.py`, new unit tests | none (new files) | all unit tests of section 10 part A/B; ruff, mypy clean | delete the files |
| S2 | Table `pi_blueprints`, model, migration, erase hook | `blueprint_store.py`, migration (number after `alembic heads`), `brain_erase.py` (one hunk), tests | low: `brain_erase.py` only; migration number must not take 0054 | up/down, single head, two-tenant, erase test, old behaviour unchanged | `alembic downgrade`; table is additive and unread when the flag is off |
| S3 | Hard gate and option gate in code, reading B2a through the deferred-column loader; shared matcher module | `constraint_check.py`, `option_gate.py`, `evalkit/relevance*.py` (import-back, coordinate with lane E), tests | none in hot files (does not touch `problems.py` or `IdeaContext`) | M3 hard_misses 0, M4 on case set, FT-A3 tests unchanged | revert; matcher import-back reverted |
| S4 | FT-C1 relevance feed (after FT-C1 merges) | `option_gate.py` only | none | M2 not below FT-C1 baseline | revert |
| S5 | Document wiring behind `response_rules.brain.blueprint`: structured call, validation, snapshot in content, `review_notes`, `reviewer_ack`, snapshot hash | `brain_docs.py`, `brain_docs_models.py` only if a column is wanted (prefer content), `box_doc.py` (small) | `brain_docs.py` is touched by FT-ART2: coordinate order | flag off = today's output identical; flag on = section 10 integration tests | flag off; revert hunk |
| S6 | Architecture (part D): validator, capability read-only check, staff annex | `architecture_rules.py`, `blueprint_store.py`, tests | after FT-ART2 | M5 element presence on cases; owner PDF has no annex words | flag off |
| S7 | Staff review view: show annex, issues, rejected options, acknowledge | `brain_doc_routes.py` (response view `_view` only), web reviewer page | low; the web page file set is **UNKNOWN** (not read) | reviewer can see and acknowledge; approve blocked until ack | revert view fields |
| S8 | Evalkit cases and scorers for M1-M5 (labelled cases, the P-2 method) | `evalkit/**` (lane E) | none | negative controls fail, human-agreement step per P-2 | delete cases |
| S9 | Optional: constraint field in `IdeaContext` so free ideas use the same gate | `idea_filter.py`, `service_conversation.py` (small hunk) | **high** (hot file); only after FT-02 and B2a/FT-C1 integration | G1-G12 behaviour unchanged with the field empty | revert hunk |
| (Q-8, own design) | tasks from the approved snapshot; claims through P-6 | not in this document | | | |

Recommended order: S1, S3 (hard gate first, it delivers the safety value alone), S8, S2, S5, S4, S6, S7, S9. S1, S3 and S8 need no migration and no hot file.

## 12. Open owner decisions

| ID | Decision | Recommended |
|---|---|---|
| D1 | Confirm the "OWNER APPROVAL hard gate" means G-A, G-B, G-C of section 6.2 (the phrase is not in the repository) | yes; add nothing new |
| D2 | A second, technical sign-off for custom automation, or one reviewer for all? (`quotes.write` is one permission for edit, approve, revise) | second sign-off for `custom_automation` and `mixed` only |
| D3 | How much of the rejected and `unknown` set does the owner see in the document? | owner sees the recommended option and one alternative with limits; the reviewer sees everything |
| D4 | Shared matcher: move helpers to production with import-back, or import evalkit read-only | move with import-back; needs lane E agreement |
| D5 | May a reviewer restore an option the gate rejected, with a recorded reason? The scorer agreed only 55% on borderline cases | yes, recorded, reviewer only |
| D6 | Add constraints to `IdeaContext` (free ideas) or keep the gate at document time only | document time first; free ideas after FT-C1 |
| D7 | Retention: may a kept document snapshot hold evidence quotes after an erase? (R1-R6 are open) | no: the snapshot keeps owner view text only, evidence stays in the erasable table |
| D8 | New table (Option A) or content-only (Option B), and who owns the migration number given 0054 is reserved | Option A, number assigned at S2 |
| D9 | Constraint status: B2a has none (every entry is treated as confirmed). Add `assumed` later through P-1 reconciliation, or keep it out | keep out; an assumed limit is an open question, not a constraint |
| D10 | Is the technical annex ever shared with the owner (as a separate staff-approved file), or staff only forever | staff only |

## 13. Unknowns and risks

Unknown (not read, not claimed): `part19.py` behaviour; whether the FT-02 role-conversion and redaction fix is merged; `style.py` and the British-spelling check; the exact `safety.py` function for advice boundaries; the full permission-key list and what Owner OS modules and routes expose; the web reviewer page files; the retention decisions R1-R6; `system_ask.py`, which the plan names but is not on `origin/main`; `constitution.py` linter internals beyond `PROMISE`/`JARGON` names.

Risks:

1. **Scorer reliability.** The matcher agreed 55% with an independent grader on borderline cases (E16); a hard gate built on it can wrongly reject or wrongly pass. Mitigations: reject-only use, `unknown` flags, reviewer restore, M3 hard-miss 0 on cases, nothing claimed as real-model verified.
2. **Jargon collision.** The annex needs words that RBUILD01 and R-DOC-05 forbid in owner text; a leak into the PDF or chat would break a non-negotiable. Mitigation: annex never rendered, PDF-text test (S5/S6).
3. **Erase.** Documents are kept on erase (E7); a blueprint snapshot could retain owner words. Mitigation: D7, table deletion, erase test.
4. **Schema drift with P-1/0053.** `cause` holds one cause; hypotheses are new. Mitigation: a separate table, no change to 0053, reconciliation shown to the owner before S2 (plan: amendments are presented, never silent).
5. **Overlap with FT-ART2 and FT-C1** on `brain_docs.py`, `box_doc.py`, `idea_filter.py`; sequencing in section 11.
6. **Proportionality.** A technical blueprint tempts oversized systems (brain-v3 p419); caps and the `oversize` check, plus reviewer judgement.
7. **Single permission for edit, approve, revise** (E5; BL-08 suspected): approval of a technical annex by the same person who edited it.
8. **The 22-state claim in CLAUDE.md is stale** (28 members, E9); any test written from the "22" number would be wrong.
9. **Level 3 scope creep.** Q-8 is an owner-scope design; this document stops at the approved snapshot and the record fields tasks would need.
