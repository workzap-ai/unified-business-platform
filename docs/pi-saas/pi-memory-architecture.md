# pi memory architecture: audit of what exists, target brain, current-to-target map (Stage 1, documentation only)

Status: PROPOSAL for owner review. No migration, no table, no production code, no model call exists for this document.
Written 2026-10-31 on branch `pi/stage1-architecture` (cut from origin/main `954441c4`).

## 0. Method and labels

- **FACT** = I read it in the named file or `git show` ref in this session. **INFERENCE** = my reasoning from facts; it can be wrong.
- Code truth sources read: origin/main `954441c4` (the worktree), `pi/ps-flow` (the branch moved during this session: `ad59e5bc`, then `a07fe1e0`, then `1653b510`; wiring statements below were re-checked at `1653b510`, memory-store statements were read at `a07fe1e0` and the later commits were not diffed for them), `pi/ps8-context-memory` `822ee103`, `pi/ps7-problem-graph` `d1a33810`, `pi/ps0-baseline` `b1ea97b6` (case counts only).
- I ran no test and no model call. No test is claimed to pass anywhere in this document. Where a test file name is given it is only to show a behaviour is claimed by that lane; I did not run it.
- Migrations live in `apps/api/migrations/versions/` (FACT: directory listing; last numbered file `0054_payment_idempotency.py`; three non-numbered files `0cb6ac1ccb54`, `3ad535597720`, `ea6781564d8a`).
- Plan file read in full for RE-PLAN v2 and ADDENDUM A: `C:/Users/USER/.claude/plans/cheerful-cooking-scone.md` (sections A1 to A7).

## 1. Audit: every place pi keeps something about an owner or a business (origin/main unless stated)

| # | Store | Table or file | Key columns (FACT) | Scope | Written by | Read by | Erase (`brain_erase.py`) |
|---|---|---|---|---|---|---|---|
| S1 | Messages | `pi_messages` (`models.py:240`) | `conversation_id, direction, sender_type, message_type, body, media(JSONB), provider_message_id, idempotency_key, status` | tenant, env, via conversation | inbound/outbound runtime | context assembly, export (limit 5000, `inbox_routes.py:550`) | rows kept, `body` replaced by `ERASED` text |
| S2 | Conversation | `pi_conversations` (`models.py:193`) | `customer_id, summary, summary_message_count, service_brief(JSONB), language, flow_state, flow_state_since, clarification_count` | tenant, env, customer | brain turn (`service_brief` keys: warmup, business_profile, asked_facts, pending_question, map_followups...) | every turn | `service_brief` set to `{"erased": True}` (`brain_erase.py:495` on ps-flow) |
| S3 | Durable facts (notes) | `pi_memories` (`models.py:444`) | `customer_id, kind(preference/requirement/context), content(<=500), content_hash, source_message_id, status(active/archived), embedding_model, last_used_at`; unique `(tenant,env,customer,content_hash)` | customer | `memory_block.refresh` (`key: value`, 10 keys `FACTS`) | `memory_block.load` (700-char block), export, correct route | deleted (all kinds) |
| S4 | Business profile | `pi_business_profiles` + `pi_profile_facts` (`business_profile_models.py:36,82`) | facts: `profile_id, key, value, source(owner/page/photo), confirmed, confirmed_at, evidence_snippet, source_url, fetched_at`; unique per `(profile_id,key)` | customer or business | warm-up, dashboard edit, page read | `business_profile_store.sync_context` (copies into `service_brief["business_profile"]` each turn, store wins) | `business_profiles` step |
| S5 | Customer row | `customers` (`customers/models.py:25`) | `name, company, industry_primary, industry_secondary, industry_confidence, business_id, business_role, can_approve` | tenant, env | CRM, pi | everywhere | contact record kept on purpose |
| S6 | Problems | `pi_problems` (`problem_models.py:55`) | text fields + `scope, frequency, since, impact (JSONB)`, `person_believes_cause`, `status`, `confidence`, `source_message_ids`, `revision`, `merged_into`, and B2a (migration 0053) `constraints, tried, cause, expected_outcome, goal_verb` | customer, conversation | `problems.py` ops (create/update/merge/split/link/withdraw) | prompt, documents, map, PS-8 | deleted with revisions, links, groups |
| S7 | Problem history | `pi_problem_revisions` | `problem_id, revision, diff, reason, by(pi/person/staff)` | via problem | `problems.py` | PS-8 corrections | deleted |
| S8 | Problem links | `pi_problem_links` (`problem_models.py:143`) | `from_id, to_id, type(9 values), confidence, created_by, status(suggested/confirmed/rejected), evidence(owner_said/pi_inferred/confirmed)`; unique `(tenant,env,from,to,type)` | via problem | `problems.py` link op (`:957` on main), `business.py:229` | `brain_docs.py:599`, `brain_learning_routes.py:665` | deleted |
| S9 | Solution boxes | `pi_solution_boxes`, `pi_offer_log`, `pi_box_transitions` (`box_models.py:61,89,106`) | box: `state(10 values), version, parent_box_id, reviewer, offered_at, owner_ranking`; offer log: `rule, allowed, blocked_reason`; transitions: `from_state, to_state, actor, actor_ref, reason` ("rows are only added, never changed", docstring) | customer, conversation | `box_lifecycle.py` | PS-8 decisions | all deleted |
| S10 | Documents (generated) | `pi_brain_documents` (`brain_docs_models.py:40`) | `kind(solution/quote), number, version, problem_ids, content, content_en, total, status(draft/in_review/approved/sent/superseded), drafted_by, approved_by, approved_at, file_id` | customer | `brain_docs.py` | PS-8, customer page | deleted (kept per `brain_erase` docstring: quotes, documents, payments are kept; see `kept_reasons`) |
| S11 | Solution reactions | `pi_solution_memory` (`solution_models.py:71`) | `customer_id, conversation_id, industry_key, problem_id (STRING), idea_arm_id, given_at, reaction(String 12), said_will_try, reported_result, builds_mentioned, offer_status, document_id` | customer | `solution_ideas.py:454` | PS-8 `_idea_memory` (reaction in rejected/tried) | deleted |
| S12 | Idea catalogue stats | `pi_idea_arms`, `pi_idea_feedback`, `pi_solution_versions`, `pi_build_fit` | industry-level statistics, not owner memory | industry | learning jobs | idea retrieval | feedback rows deleted, stats kept |
| S13 | Uploaded files | `customer_files` (`customers/models.py:139`) | `customer_id, conversation_id, message_id, source, name, mime, size, data(bytes), ref_type, ref_id` | customer | `runtime._keep_file` (`runtime.py:1051`) | CRM page | NOT erased (gap G13, awaiting retention decision) |
| S14 | Document reading | `documents.py` `read_document`/`document_text` | returns a one-off summary (<=4000 chars) and `document_text` text capped at `MAX_TEXT`; the summary goes into the message description, `doc_kind` into `message.media` (`runtime.py:1055-1068`) | none | n/a | prompt only | n/a |
| S15 | Knowledge | `knowledge_sources/documents/chunks` (`models.py:470-537`) | workspace-level; chunk `embedding_values ARRAY(Float)`, `embedding_model`, `content_tsv` | tenant, env (NO customer) | teach files, website crawl | `knowledge.py` tsvector + `semantic.py` | not customer data |
| S16 | Learning bank | `pi_learning_examples` (`learning_models.py:37`) | `embedding JSONB` plus text | workspace | nightly learning | `learning_bank.py` cosine | examples deleted |
| S17 | Open items / hypotheses / move log | `pi_open_items`, `pi_hypotheses`, `pi_move_log` | pending questions, model hypotheses | customer | brain turn | brain turn | deleted |
| S18 | Quarantine, audits | `pi_quarantine`, `pi_reply_audits` (`pack_versions`, `prompt_version`) | encrypted copies, per-reply stamps | workspace | safety, audit | staff | quarantine deleted |

FACT for the whole table: every `Workspace*` row carries `tenant_id` and `environment_id`; foreign keys are composite via `scoped_fk` (e.g. `pi_problem_links.from_id -> pi_problems`). PostgreSQL RLS is not enabled (`docs/pi-saas/d8-rls-security-assessment.md` section 1, ADR 0004).

### 1.1 The live readers on pi/ps-flow `a07fe1e0` (re-checked at `1653b510`: unchanged) (FACT: `git grep` and `service_conversation.py:1618-1665, 4335-4338`)

| Reader | Called | Reads | Output |
|---|---|---|---|
| `memory_block.load_safely` + `memory_block.build` | `service_conversation.py:4335, 4338` | `pi_memories` (kinds context/preference), profile merge | `what_i_know` block, capped 700 chars (`BLOCK_CHARS`), also used by `memory_reply` ("what do you remember") |
| `context_memory.build_context` | `service_conversation.py:1638`, brain mode only | messages (this and earlier chats), problems incl. B2a, solutions with exact state, files, tried, rejections, decisions (offer log, open items), profile facts, memories, revisions | `ContextBundle`; `known_records`, `what_is_already_known`, `implementation_summary` feed the one question, the "we already have" line and implementation wording |
| `business_profile_store.sync_context` | `service_conversation.py:1638-1641` area | `pi_profile_facts` | `service_brief["business_profile"]`, `profile_grounding` |
| `requirements_read.read_requirements` | `service_conversation.py:1620` | B2a columns | `context["requirements"]` |

INFERENCE: both assemblers run on one brain turn, so there are two sources of "what pi knows" that can disagree (the 700-char block and the bundle). I did not trace whether the model prompt gets both in full.

## 2. Target architecture: the permanent evidence-backed business brain

Principles (owner requirements, also ADDENDUM A): existing stores first; one canonical record per concern; one retrieval path; every fact keeps its source and its knowledge state; the owner can see, correct, export and delete; derived views never become authorities.

```
 owner message / file / voice / staff action
        |  tenant+env+customer resolved, language/script (PS-9), redaction (safety.redact)
        v
 EXTRACT (existing: problem_extract, problems ops, requirements B2a, business_profile)
        v
 CLASSIFY: correction / withdrawal / new / duplicate / conflict      (new, small, pure code)
        v
 WRITE through ONE contract (idempotent upsert, history row, knowledge state, source ids)
        v                          canonical records (section 3)
 REBUILD derived views: summary, what_i_know block, customers columns, brief["business_profile"]
        v
 READ: ONE retrieval path (section 4) -> ContextBundle -> prompt/gates; log items used per reply
```

## 3. Layer-by-layer: current, target, mapping

State words: **Exists** (used live), **Exists-unwired** (code merged elsewhere, not on a live path), **Partial**, **Missing**.

| Layer | Current components (evidence) | Target | Mapping decision (current to target) | State today |
|---|---|---|---|---|
| Identity / business | `pi_business_profiles`, `pi_profile_facts` (S4); `pi_memories` business keys (`memory_block.FACTS`: name, role, business_name, business_type, location, team_size, channels, current_tools, website, goal); `customers.industry_*`; `service_brief["business_profile"]` | one canonical fact store with validity and history | CANONICAL = `pi_profile_facts` (A3) plus `valid_from, valid_to, superseded_by, version` (additive). `pi_memories` and `brief["business_profile"]` become derived views through the contract; `customers` columns derived | Partial: four stores (gap analysis D1) |
| Conversation | `pi_messages` (S1) verbatim; `pi_conversations.summary` + `summary_message_count`; `service_brief` working state | messages authoritative; summaries regenerated from records with source ids | Keep. Add no table: store `source_message_ids` inside the summary regeneration (design in `pi-memory-entities-and-lifecycle.md` section 8) | Exists, summary has no source ids |
| Problem | `pi_problems` + revisions + groups (S6, S7); B2a columns; statuses `owner_said/confirmed/pi_inferred/withdrawn` for cause (`problem_fields`, FACT via PS-7 header) | same | Keep as canonical. `person_believes_cause` stays a derived field (read by `box_doc.py:57`, `brain_docs.py:659`) | Exists |
| Solution | `pi_solution_boxes` + `pi_box_transitions` + `pi_offer_log`; `pi_brain_documents` (versioned, `superseded`); `pi_solution_memory` (reaction, `reported_result`, `problem_id` string); `flow_state` S0..S13 | solution revision and outcome history linked to problems by id | `pi_solution_memory.problem_id` is a string (FACT `solution_models.py:71..`, `solution_ideas.py:286 problem_id=problem["id"]`), no FK: add nullable `problem_uuid` FK later; outcome ladder beyond `in_build` needs owner-approved states (gap analysis G6) | Partial |
| Decision | Derived: `pi_offer_log.allowed/blocked_reason`, `pi_box_transitions`, `pi_brain_documents.approved_by/at`, `pi_open_items` -> PS-8 `DecisionItem` (FACT `context_memory.py:746-800` on ps8) | versioned decisions with validity and supersession | Derive first (A3). A ledger only if gap G2 evidence says derivation cannot give validity/supersession; design in entities doc E2 | Partial (derived, read-only, no validity) |
| Constraint | B2a `pi_problems.constraints` JSONB (FACT `problem_models.py:112`), read by `requirements_read.parse_constraints`; L2-1 hard gate (branch `pi/l2-hard-gate` `b3f3944a`, not on main) | scope, source, status, expiry, withdrawal | Extend the JSON element shape before any table (A3); main has the column, the gate is only on ps-flow | Partial |
| Document | `customer_files.data` (bytes, no text); `read_document` returns a summary only (S13, S14); `knowledge_documents` is workspace-wide | extracted text with page/sheet/section refs, customer-scoped | NEW store needed (the only genuinely new table family besides decisions/rejections); reuse `documents.py` readers; never use `knowledge_documents` for customer files | Missing |
| Graph | `pi_problem_links` (S8) written by the model "link" op; PS-7 `problem_graph.py` is pure; on ps-flow `1653b510` only `graph_voice.py` imports it (owner-facing wording, via `service_conversation.py:2158`); nothing persists its edges (FACT `git grep`, no `PiProblemLink` in `graph_voice.py`) | persisted edges with basis, quote and status | Reuse `pi_problem_links`; add nullable `basis`, `evidence_text`, `source_message_id`, `valid_to` (entities doc E4). Correction to plan A3: the table already exists and is already written | Partial |
| Retrieval | `memory_block.load` (SQL), `context_memory.build_context` (SQL, many tables), `knowledge.py` tsvector, `semantic.py` pgvector cast, `learning_bank` cosine, `idea_retrieval.py` | one path | Section 4 | Partial, three or four paths |
| Learning | `learning*.py`, `experience_*.py`, `pi_learning_*`; freeze flag `response_rules.brain.learning_frozen`; knowledge learning (what is true about this business) is NOT separate from performance learning today (INFERENCE: no module with that split found) | knowledge learning separate from performance learning; verified outcomes only | Keep freeze/canary/rollback; add outcome-verified gate later (Stage 2) | Partial |
| Transparency | `memory_reply` (what do you remember, chat), `PATCH /memory/{id}` (`inbox_routes.py:517`), `GET /customers/{id}/export` (`:550`: customer, conversations, messages only in the part I read), `brain_erase_routes.py`, `erase_customer` | explain why remembered and from where, export everything, correct, withdraw, delete | Reuse all four; FACT (`inbox_routes.py:342-420, 550-585`): the export returns customer, conversations (summary, language, `service_brief["requirements"]`), up to 50 active `pi_memories` (needs `pi.memory.read`), consents, open handoffs/tickets, bookings, tasks and up to 5000 messages; it does NOT return `pi_problems`, revisions, links, solution boxes, brain documents, `pi_solution_memory`, profile facts or files (not seen in the code I read) | Partial |
| Security | tenant+env on every row, composite FKs, redaction before store, `brain_erase`, `pi.memory.read`, `pi.customers.export` permissions; no RLS | RLS decision, zero cross-tenant leakage tested | Owner decision D8; test evidence in gap analysis | Partial |

## 4. The canonical memory contract (ADDENDUM A3), verified against code

| A3 statement | Code truth (FACT) | Verdict |
|---|---|---|
| `pi_profile_facts` canonical, unique per key = overwritten today | unique `(profile_id,key)`; columns as S4 | Correct. No `valid_from/valid_to/superseded_by/version` exists |
| fold `pi_memories` and `service_brief["business_profile"]` into it | `brief["business_profile"]` is rewritten from `pi_profile_facts` on every turn by `sync_context` ("what is stored wins"), but warm-up also writes it first (`warmup.py:12`, `service_conversation.py:6028`) | Partly wrong: the brief key is already a mirror of the store, not a separate authority. The real duplicate is `pi_memories` vs `pi_profile_facts` |
| `PiProblem` + revisions canonical; cause statuses owner_said/confirmed/pi_inferred/withdrawn | statuses present in PS-7 and `problem_fields` naming; `pi_problems.status` has `withdrawn`, `parked` (`taxonomy.py:91`) | Correct |
| solutions: boxes + transitions append-only, documents versioned, offer log; `pi_solution_memory` FK | transitions "only added" (docstring, not DB-enforced: no trigger seen; `brain_erase.py:322` deletes them); documents have `version`, `superseded` | Correct; append-only is by convention, not enforced |
| status ladder Proposed to Delivered; storage stops at in_build/S13 | `flow.State` ends at `S13_IN_BUILD` (+ X_ states); `Box.STATES` ends at `revised`; `context_memory_types.IMPLEMENTED_STATES = ("delivered",)` and `IN_PROGRESS_STATES = ("kickoff","in_build")` | Correct, plus: INFERENCE: nothing stores the string `delivered`, so "implemented" cannot be reported today |
| decisions derived now, ledger only if proven insufficient | PS-8 derives `DecisionItem` from offer log + open items + doc approval | Correct |
| constraints: extend B2a JSON | column exists, `deferred=True` | Correct |
| documents: new extracted-text store; `knowledge_documents` workspace-wide | `KnowledgeDocument` has no `customer_id` | Correct |
| rejections: `PiSolutionMemory.reaction='rejected'` only store | PS-8 also scans messages for rejections (`scan_rejections`, derived) | Correct, plus a derived scan |
| graph: `pi_problem_links` persists PS-7 edges | table already exists and is written by `problems.py` link op; PS-7 never writes it | CORRECTED: no new table; additive columns only |
| reader: `context_memory.build_context` single; `memory_block.load` a view | both live on ps-flow brain turns (section 1.1) | Correct as target; today not done |
| knowledge states shared enum | no shared enum; vocabularies: problem cause (owner_said/confirmed/pi_inferred), link evidence (owner_said/pi_inferred/confirmed), PS-8 fact status (owner_said/confirmed/pi_inferred/page_read/remembered), profile fact (`source` owner/page/photo + `confirmed`) | Correct; mapping table in section 5 |

## 5. Knowledge-state vocabulary mapped onto existing columns

| Target state | Existing value that already says it |
|---|---|
| owner-confirmed | `pi_profile_facts.confirmed = true`; cause `owner_said`/`confirmed`; link `evidence=confirmed` |
| document-extracted | none (S14 produces no stored record); new `source_kind=document` |
| system-observed | profile fact `source=page`/`photo`; PS-8 `page_read`; behavioural signals |
| evidence-supported | none stored; PS-8 `derived` scans |
| pi hypothesis | cause `pi_inferred`; link `pi_inferred`; `pi_hypotheses` table |
| unknown | empty field; PS-5 unknown options (ps-flow) |
| disputed | none |
| superseded | `pi_memories.status=archived`; `pi_brain_documents.status=superseded`; revisions |
| withdrawn | `pi_problems.status=withdrawn`; cause `withdrawn` |

## 6. One retrieval path (ADDENDUM A4), verified

| Step | Exists | Evidence |
|---|---|---|
| structured SQL | yes, two separate readers | section 1.1 |
| keyword | knowledge only (`content_tsv` computed column, `models.py:535`) | not applied to owner memory, messages, problems |
| semantic | knowledge chunks only: `embedding_values` is `ARRAY(Float)` (migration `ea6781564d8a`), cast to `VECTOR(n)` at query time (`semantic.py:81-94`): exact scan, no index possible. A second, separate store: `pi_learning_examples.embedding JSONB` with Python cosine (`learning_bank.py:455-462`). `pi_memories.embedding_model` exists but no embedding is stored for memories (grep: only `runtime.py:1505` and `semantic.py` use embeddings, both for knowledge). Gated by `settings.semantic_search_enabled` and the `vector` extension | CORRECTION to A4: there is no pgvector column in the migrations I read; pgvector columns are "optional, applied manually" (`0002_business_platform_pi.py:7`), unverified on the real database |
| graph | `pi_problem_links` read for documents and a review route only; PS-7 is used on ps-flow `1653b510` for wording only (`graph_voice`), not for persistence | section 3 |
| validity + tenant + permission filters | tenant+env in every query; `pi.memory.read` route permission; no validity filter (no validity columns) | |
| evidence ranking, conflict detection | none (PS-8 only separates owner status from hypothesis) | |
| context assembly priority | partial: PS-8 caps and ordering; no stated priority list in code | |
| log which memory items influenced a reply | `pi_reply_audits` stamps prompt and pack versions only (FACT `learning_models.py:154`, `drift_check.py`) | no per-item log |

Target (unchanged from A4, plus the correction): build the path as ordered stages inside `context_memory.build_context` (it already has the savepoint-per-source, cap and `truncated` discipline), add keyword search over owner memory via a computed tsvector only after the document/extracted-text store exists, and treat semantic search as an owner decision (cost, privacy, index) that must unify `knowledge_chunks.embedding_values` and `pi_learning_examples.embedding` on one embedder (`learning_embed.make_embedder` wraps `app.ai.embeddings.embed`, the same function `semantic.py` uses).

## 7. Tenant, environment and security design constraints (FACT-based)

| Constraint | Evidence | Design rule |
|---|---|---|
| every new table carries `tenant_id, environment_id` and composite FKs | `WorkspaceRow`, `workspace_args`, `scoped_fk` (`app/shared/models.py`, used throughout) | new tables use the same helpers |
| customer scope | `customer_id` on every owner-memory table | new tables carry `customer_id`, and `business_id` only where profile sharing is needed (R-MEM-06) |
| redaction before store | `safety.redact` used by `memory_block`, `problems` | extracted document text must pass the redactor before storage; an unredacted copy stays only in `customer_files.data` |
| erase | `brain_erase.REMOVED_KEYS` + `_run_steps` savepoints; test `pi/r-ft01` `60b1fa66` (not merged) checks every `customer_id` table is erased or listed | every new table needs an erase step and an entry in that test |
| export | `inbox_routes.export_customer`, permission `pi.customers.export`, audited | extended, not replaced |
| RLS | not enabled; D8 proposal on `pi/d-decision-docs` `71218948` (not merged) | owner decision; new tables work with or without RLS |

## 8. Integration ownership (INFERENCE from CLAUDE.md and lane rules; "one wiring owner")

| Area | Owner for production wiring | Rule |
|---|---|---|
| `service_conversation.py`, `runtime.py` | flow lead (ps-flow) | no memory work lands there without the flow lead |
| `memory_block.py`, `context_memory.py` | memory lane (Stage 2) | one reader; `memory_block.load` becomes a view |
| migrations | owner approval first; numbered by hand after `alembic heads` | next number is 0055 or later (FACT: last file `0054`); check heads |
| `brain_erase.py`, export route | erase lane (`pi/u-erase-g1-g10` merged, `pi/d-erase-gaps` docs) | every new table adds a step |

## 9. What I could not verify

- Whether the prompt receives both `what_i_know` and the PS-8 bundle in full (I read the call sites, not the prompt assembly).
- The last part of `customer_profile` (after tickets, lines past 420) was not read; it may add fields.
- Whether pgvector exists on the real Neon database; whether any real data sits in `pi_memories.embedding_model`.
- Any production data volumes.
