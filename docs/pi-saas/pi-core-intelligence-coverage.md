# Core product intelligence (Section 9, A to H) and the three success levels, mapped to the roadmap

Status: PROPOSAL for owner review, 2026-10-30. Roadmap A to G, the Fast-Track plan and P-1 to P-6 stay
the master; nothing here changes approved scope. Gaps are listed as proposed additions (Q-n) that need
the owner's yes. Status words: planned, implemented (merged to `origin/main`), scripted-tested,
real-model-verified. **Nothing below is real-model-verified.** `origin/main` is `cc462c5`; FT-02 (Part 19) is
not merged.

## The three success levels

| Level | Meaning | Roadmap that serves it | State |
|---|---|---|---|
| 1 Understand the business | complete problem, requirements, constraints | B6 (S1 to S5 implemented), B2a/B2b, S6, FT-REQ, P-1, P-4; labels in FT-A1/A2 | partly implemented; B2a blocked behind FT-02 |
| 2 Design the right solution | root cause, creative solution, architecture, plan | FT-C1, FT-ART2, FT-C4, P-2, P-3 | designed on paper; relevance and creativity not built |
| 3 Deliver verified outcomes | execute approved actions, verify results, report progress | P-6 (claims and outcome check, design only), erase/RLS work | **execution and progress tracking are not in the roadmap** (gap Q-8) |

## Section 9 mapped item by item

| Item | Covered by | Status | Gap |
|---|---|---|---|
| A. complete context, workflows, stakeholders, resources, systems, challenges | B2a, P-1 (workflows, roles, systems, expected outcome), FT-REQ sheet, S6 | planned | none new |
| A. every requirement, constraint, decision, attempt, outcome | B2a (constraints, tried), P-1, P-4 | planned (P-4 is an audit and a design) | none new |
| A. distinguish confirmed facts, assumptions, unknowns, recommendations | cause has `pi_inferred / owner_said / confirmed` (P-1) | planned, **for cause only** | **Q-1** a status on every fact, not only the cause |
| A. never invent facts; ask only essential questions; never re-ask | non-negotiables, B6 S4/S5 (implemented, `fact_ask` opt-in off by default), FT-REQ asks only the top missing item | implemented (partly) / planned | "essential" is not defined; **Q-2** rank missing items by how much they change the solution |
| B. symptoms versus causes; operational, financial, technical, human factors; dependencies, risks, consequences | expert advisor diagnosis (merged), B2a cause fields, FT-A2 cause-evidence scorer | partly implemented | no check that a diagnosis names factors, risks and consequences; **Q-3** root-cause quality criteria and labelled causes |
| B. evidence for each diagnosis; label hypotheses | `cause.evidence` and status (P-1), FT-A2 unsupported-cause scorer | planned | none new |
| C. design around the business; multiple options compared; recommend the strongest with reasons | FT-C1 relevance, FT-ART2, P-3 layer B | planned | **Q-4** an options comparison (benefit, cost, limits, risk) in the plan format; today ideas are 2 plus 2 per problem, with no comparison |
| C. missing capabilities the owner has not considered; avoid needless complexity | P-2 creativity rubric (design), FT-C1 "no idea is valid" | planned | none new |
| D. industry workflows, entities, terminology, rules; no cross-industry assumption | C2 (implemented), G9 and G11 (implemented), FT-C3 (tests merged), FT-C6, packs for 211 industries, P-3 | partly implemented | **0 industries verified**; the nine business types you list (booking, rental, e-commerce, SaaS, wedding and banquet, healthcare, education, logistics, agriculture) need a check against the 211 packs and a case set; D5 sets the criteria |
| E. modules, roles, workflows | P-3 layer A and B, Solution Box | partly implemented (modules, phases); steps, roles specified only | none new |
| E. database entities and relationships; APIs and integrations; automation and notifications; dashboards and reporting; security, privacy, audit; implementation phases; cost, dependencies, risks; success criteria | P-3 covers modules, steps, dependencies, roles, next action only | **not covered** | **Q-5** a blueprint schema with these sections, owned by lane S, built on the P-3 question Q1 |
| F. preserve requirements and corrections | S4, B2a, P-1 | implemented (closed facts) / planned | none new |
| F. track decisions and declined suggestions | P-4 audit and retention review; option A or C proposed | audit documented only; nothing built | owner decisions Q1 to Q4 of the P-4 review |
| F. unresolved questions and next steps | `open_items.py` exists; no roadmap task | implemented in part | **Q-6** confirm what exists, and test it for cross-chat carry |
| F. detect contradictions and ask | corrections handled (B6, "10 nahi, 100"); no explicit contradiction check | partly | **Q-7** a contradiction check between a new statement and the stored record |
| G. self-check before presenting: every requirement covered, workflows, constraints, dependencies, realism, evidence, measurable outcome | offline scorers (P-2 requirement preservation, P-3 completeness, FT-C1); P-6 claim gate; reviewer approves every solution document | scorers and gate designed; **no runtime checklist before a solution is presented** | **Q-9** a runtime pre-presentation self-check, reported to the reviewer |
| G. never describe an action as done unless executed and verified | P-6 design, non-negotiables | design only | depends on FT-02, P-4 decisions |
| H. realistic complex scenarios, independent reviewers; measure completeness, accuracy, relevance, creativity, actionability, consistency, repetition, safety, user satisfaction | P-2, P-3, P-5 (Stage 1 approved, Stages 2 and 3 proposed), the labelling method | proposals only | **Q-10** actionability and user-satisfaction measures are not defined; **Q-11** an end-to-end scenario demonstration suite for the nine business types, run on a real model with independent reviewers |
| H. real-model evaluation required | P-5 | nothing run; no key | owner decisions on model, caps and approval |

## Proposed additions (none approved, none started)

- **Q-1** a state (stated, assumed, unknown, recommended) on every stored fact, extending the P-1 cause status; belongs in the P-1 schema review before migration 0053 is written.
- **Q-2** rank missing information by its effect on the solution, so pi asks only what changes the answer (extends FT-REQ).
- **Q-3** root-cause quality criteria and labelled causes (extends FT-A2 and the P-2 labelling).
- **Q-4** options comparison in the plan format.
- **Q-5** blueprint schema (data entities, APIs and integrations, automation, dashboards, security and audit trail, phases, cost, dependencies, risks, success criteria).
- **Q-6** verify `open_items.py` for unresolved questions and next steps across chats.
- **Q-7** contradiction detection against the stored record.
- **Q-8** Level 3: executing approved actions and reporting progress; needs the owner to say which actions, how they are authorised and what counts as verified evidence.
- **Q-9** a runtime pre-presentation self-check.
- **Q-10** actionability and user-satisfaction measures.
- **Q-11** an end-to-end business-scenario demonstration suite on a real model with independent reviewers.

## Conflicts with approved rules (to resolve before any build)

1. **Blueprint "cost" versus "pi never prices a quote".** Blueprint cost has to come from a reviewer or staff, not from pi (CLAUDE.md non-negotiables).
2. **Blueprint phases and steps versus the rules against dates, promises and "will".** Wording stays conditional ("would"); a reviewer approves every solution document.
3. **"Multiple approaches compared internally" versus the existing 2 plus 2 ideas cap per problem (platform spec Book 5).** The comparison would sit in the solution document, after the offer and the owner's yes, not in free ideas.
4. **Q-8 execution versus "no payment in chat", "payment received only after staff confirm" and tenant and approval gates.**
5. **Section 9 H "real-model evaluation required" versus the approved scope:** only Stage 1 (extractor, Development, 30 calls, USD 0.50) is approved; nothing has been run.
6. **Q-1 and Q-5 enlarge the P-1 schema:** the schema must be reviewed once, before 0053, not after.

## What stays unchanged

FT-02 remains the critical path (the sixth fix commit is awaited). B2a does not start before it is integrated.
No migration, model call, spending, push or merge is implied by this document.
