# pi memory: proposed entities and lifecycle, ONLY for genuinely missing structures (Stage 1, design only)

Status: DESIGN PROPOSAL for owner review, 2026-10-31. **Nothing here is created.** No migration file, no SQL, no model, no code. Every table below needs an owner-approved migration before Stage 2 builds it. Labels: FACT (read in code or docs, refs in the architecture and gap documents), INFERENCE (my design reasoning).

## 0. Rules that apply to every proposal

| Rule | Basis |
|---|---|
| Reuse first: a structure is proposed only where the gap analysis found no existing store that can carry it | `pi-memory-gap-analysis.md` section 1 |
| Every new table is a `WorkspaceRow` (`tenant_id`, `environment_id`, composite FK via `scoped_fk`, `workspace_args`) and carries `customer_id` | FACT: pattern used by `PiProblem`, `PiMemory` (`models.py:444`, `problem_models.py:55`) |
| Additive only: new nullable columns or new tables; no rename, no drop, no type change of anything created by migrations up to `0054` | INFERENCE, protects the real database which is migrated by pasting `alembic upgrade --sql` (CLAUDE.md) |
| Code reading a new column must survive its absence until the migration runs (savepoint, SQLSTATE 42703 or 42P01 tolerated, reported as unavailable) | FACT: the PS-8 pattern (`context_memory.py` header on ps8) and `brain_erase._run_steps` |
| Next migration number after `0054_payment_idempotency.py`; run `alembic heads` first (three non-numbered revisions exist: `0cb6ac1ccb54`, `3ad535597720`, `ea6781564d8a`) | FACT: directory listing |
| Raw model interpretation is never written directly; redaction first (`safety.redact`) | ADDENDUM A5, FACT for redact use in `memory_block`, `problems` |
| Learned or retrieved text is data below the rules and never overrides them | CLAUDE.md non-negotiables |
| Hard delete of customer-scoped rows on erase, except what the retention decision lists as kept | `brain_erase.py` docstring (`kept`, `kept_reasons`) |

## 1. Summary of what is proposed

| Id | Structure | Kind | Needed for | Priority |
|---|---|---|---|---|
| E1 | `pi_file_extracts` + `pi_file_segments` | 2 new tables | M1, M10 | high |
| E2 | `pi_decisions` ledger | 1 new table, CONDITIONAL on the gap test | M2 | decide in Stage 2 |
| E3 | `pi_owner_rejections` | 1 new table | M4 | medium |
| E4 | `pi_problem_links` extra columns | additive columns | M5 | high |
| E5 | `pi_profile_facts` validity and state columns | additive columns | identity layer, D1 | high |
| E6 | `pi_solution_memory.problem_uuid`; `pi_solution_outcomes` | 1 column + 1 new table | M6 | medium |
| E7 | `pi_reply_audits.memory_used` | 1 JSON column | M7, X6 | low |
| E8 | constraint element shape in `pi_problems.constraints` | JSON shape, no DDL | M3 | high |

Not proposed: a graph database, a parallel memory table, a second embedding table, a general "events" log. The shared knowledge state is a column on new tables and E5, not a new table.

## 2. Knowledge-state vocabulary (one shared set)

| State | Meaning | Who may set it | Counts as fact for gates and customer-facing claims |
|---|---|---|---|
| owner-confirmed | the owner said it or confirmed pi's restatement, with a message id | owner action only | yes |
| document-extracted | read from an owner's document, reference to file, page/sheet/section | extraction pipeline | yes, shown with its reference; owner may dispute |
| system-observed | seen by the system (website page, payment, delivery event, staff action) with its source | pipeline | yes, labelled as observed |
| evidence-supported | pi inference backed by at least one cited record | pipeline | no for gates; may be offered as a question |
| pi hypothesis | pi inferred, no owner or document evidence | pipeline | never; asked or checked, never asserted |
| unknown | the field is needed and nothing is known | n/a | never invent |
| disputed | two records conflict, both kept | conflict step | neither used for a gate until resolved |
| superseded | replaced by a newer record; kept as history | write step | no (history only) |
| withdrawn | the owner said it no longer applies | owner action | no |

Mapping from existing values is in `pi-memory-architecture.md` section 5. Stored as a short string column with a CHECK constraint on new tables; on existing tables the existing columns keep working and a view function maps them (no data migration first).

## 3. E1: extracted document text with references (M1)

Purpose: keep what a document says, with where it says it, so a later question is answered from stored text. Original bytes stay in `customer_files` (FACT: `data` bytes column), which is not changed.

**`pi_file_extracts`** (one row per extraction run of a file)

| Column | Type | Notes |
|---|---|---|
| id, tenant_id, environment_id, created_at, updated_at | WorkspaceRow base | |
| customer_id | Uuid | scoped FK to `customers` |
| file_id | Uuid | scoped FK to `customer_files(id)` |
| extract_version | int | 1 first run; a new run (better reader) is version+1, never overwrites |
| reader | str(40) | `pdf_text`, `docx_text`, `office_text`, `vision` (label of the reader; FACT these functions exist in `documents.py`) |
| status | str(12) | `ready`, `unreadable` (the `FILE_UNREADABLE` case), `partial` |
| page_count, sheet_count | int null | |
| content_hash | str(64) | sha256 of the source bytes, for idempotency |
| language | str(16) null | detected language |
| knowledge_state | str(24) | default `document-extracted` |

**`pi_file_segments`** (one row per page, sheet, or heading section)

| Column | Type | Notes |
|---|---|---|
| id, tenant_id, environment_id, customer_id | as above | |
| extract_id | Uuid | scoped FK to `pi_file_extracts` |
| ordinal | int | order inside the file |
| ref_kind | str(8) | `page`, `sheet`, `section` |
| ref_label | str(80) | "page 3", "Sheet Prices", "Section 2.1 Payment" |
| text | Text | redacted text (raw bytes remain in `customer_files`); capped per segment |
| text_hash | str(64) | |
| tsv | TSVECTOR computed | `to_tsvector('simple', text)` like `knowledge_chunks` (FACT `models.py:535`) |

| Aspect | Design |
|---|---|
| Relationships | `customer_files` 1..n `pi_file_extracts` 1..n `pi_file_segments`; a segment is cited by a memory item through `source_ref` (see section 8) |
| Indexes | `(tenant,env,customer,file_id)`; unique `(tenant,env,file_id,extract_version)` on extracts; unique `(tenant,env,extract_id,ordinal)` on segments; GIN on `tsv` |
| Constraints | CHECK on `status`, `ref_kind`, `knowledge_state`; `ordinal >= 0`; text length cap |
| Scope | tenant + environment + customer; never reachable through knowledge search (FACT: `KnowledgeDocument` is workspace-wide and must not hold customer files) |
| Lifecycle | extract on upload (after `_keep_file`, `runtime.py:1051`); re-extract creates a new version and marks the old `superseded` by being not-latest; file deletion by staff cascades |
| Retention | follows the `customer_files` retention decision (erase gap G13, OWNER DECISION pending); proposal: same as the file |
| Erase | new step in `brain_erase.REMOVED_KEYS` (`file_segments`, `file_extracts`) deleted with the customer, before the file decision; INFERENCE: if G13 resolves to keep files, extracted text should still be deleted because it is searchable and easier to leak |
| Backward compatibility | pure additions; nothing reads them until Stage 2 code ships; before the migration, extraction is simply skipped (reader treats missing table as unavailable) |
| Idempotent upsert | key `(file_id, content_hash)` decides whether a run exists; `INSERT ... ON CONFLICT (tenant, env, file_id, extract_version) DO NOTHING`; the segment write is one transaction with the header, so a retry never leaves a half-extracted file |
| Risk | privacy (ID/finance documents), volume (cap per file and per customer), scanned PDFs (no text layer: status `unreadable`, vision reader is a model call and an owner cost decision) |

## 4. E2: decisions ledger (M2), conditional

Build only if a written test shows derived decisions cannot answer "valid now? replaced by what?". Derivation sources that already exist: `pi_offer_log`, `pi_box_transitions`, `pi_brain_documents` (versions, `superseded`, `approved_by/at`), `pi_open_items` (FACT).

**`pi_decisions`**: `id`, scope columns, `customer_id`, `conversation_id` null, `kind` (offer, approval, scope_choice, price_acceptance, option_choice, other), `subject_ref` (type:id of the box, document or problem), `decision` (short text, redacted), `decided_by` (owner/staff/pi), `actor_ref`, `source_message_id` null, `alternatives` JSONB, `valid_from`, `valid_to` null, `supersedes_id` null (self FK), `status` (active/superseded/withdrawn), `knowledge_state`.

| Aspect | Design |
|---|---|
| Indexes | `(tenant,env,customer,status)`, `(tenant,env,subject_ref)`; unique partial index: one `active` decision per `(tenant,env,customer,kind,subject_ref)` |
| Rule | a new decision for the same subject sets `valid_to` and `status=superseded` on the old one in the same transaction (see section 9) |
| Retention and erase | follows the P-4 decision retention table (`pi-decision-retention-review.md` on `pi/s-s7a-audit` `169e4763`, owner questions Q1 to Q4 pending); default delete with the customer unless the owner lists it as a business record |
| Idempotent upsert | natural key `(tenant, env, customer, kind, subject_ref, source_message_id)`; replays of the same message do nothing |
| Compatibility | derived DecisionItem stays; the ledger, if built, becomes the first source and the derived items the fallback for rows before it |

## 5. E3: owner rejection history (M4)

**`pi_owner_rejections`**: `id`, scope, `customer_id`, `target_kind` (idea, document, price, channel, option), `target_ref` (idea arm id, document id or normalized text key), `problem_id` null (scoped FK to `pi_problems`), `owner_words` (redacted, <=300), `reason` (<=300, owner-stated, may be empty), `source_message_id`, `valid_from`, `valid_to` null, `status` (active/reversed/expired), `knowledge_state` (owner-confirmed or evidence-supported when pi inferred the rejection from a refusal word).

| Aspect | Design |
|---|---|
| Indexes | `(tenant,env,customer,status)`, `(tenant,env,customer,target_kind,target_ref)`; unique `(tenant,env,customer,target_kind,target_ref,source_message_id)` |
| Relation to existing | `pi_solution_memory.reaction='rejected'` stays the idea-level index (FACT `context_memory.py:887`), written in the same transaction; the rejection row adds the words, reason and validity |
| Lifecycle | reversal when the owner later accepts the same target (status `reversed`, row kept); expiry only when the owner gave a time limit |
| Erase | deleted with the customer (new `REMOVED_KEYS` entry) |
| Compat | additive; PS-8 `scan_rejections` (derived) stays as the fallback |

## 6. E4: relationship edges (M5), additive columns on `pi_problem_links`

| Column | Type | Purpose |
|---|---|---|
| basis | str(32) null | `owner_stated`, `shared_cause`, `shared_resource_or_process`, `category_family` (PS-7 `EdgeKind`, FACT ps7 `problem_graph.py:80-84`) |
| evidence_text | str(300) null | the owner's quote (redacted) |
| source_message_id | Uuid null | message of the quote |
| strength | str(8) null | strong/medium/weak (PS-7 `STRENGTH_RANK`) |
| valid_to | timestamptz null | set when an end problem is withdrawn or the owner removes the link |

Existing columns reused: `type` (9 values; FACT `taxonomy.py:103`), `confidence`, `created_by`, `status` (suggested/confirmed/rejected), `evidence` (owner_said/pi_inferred/confirmed). Existing unique `(tenant,env,from_id,to_id,type)` is the idempotent upsert key: re-running the graph updates `confidence/basis/evidence_text` only when the new evidence is stronger or the state moves forward (never `pi_inferred` over `confirmed`, never `confirmed` by pi). Mapping PS-7 to `type`: owner_stated to `causes` or `worsens` by the stated relation; shared_cause to `same_root_suspected`; shared_resource to `same_area`; category_family stays unpersisted (weak, hypothesis). INFERENCE: the mapping is my proposal; PS-7 does not define it.

Erase: already deleted with the problem (FACT `brain_erase.py` docstring); no new step. Compatibility: nullable columns, no default needed.

## 7. E5: identity facts validity and state (additive columns on `pi_profile_facts`)

Today unique `(profile_id, key)` and the value is overwritten (FACT). Proposal keeps the current row as the "current" fact and adds history without breaking the unique:

| Column | Type | Purpose |
|---|---|---|
| knowledge_state | str(24) null | section 2 vocabulary; null means "derive from `source` and `confirmed`" |
| valid_from | timestamptz null | when the value became true or was learned |
| valid_to | timestamptz null | set when superseded or withdrawn |
| version | int default 1 | increments per overwrite |
| superseded_by | Uuid null | not usable on a unique-per-key row; see below |

Because the unique per key blocks keeping old rows in the same table, the proposal is: before an overwrite, the old value goes to `pi_problem_revisions`-style history. INFERENCE: choose between (a) relax the unique to a partial unique index `WHERE valid_to IS NULL` so old rows stay in the same table (needs an owner-approved migration that drops a constraint, the only non-additive item in this document) or (b) a small `pi_profile_fact_history` table (profile_fact_id, version, value, source, changed_at, changed_by, reason). Recommendation: (b), purely additive. Erase: the history table is deleted with the profile (add to `business_profile_store` erase step, FACT: `business_profiles` step exists). `pi_memories` business keys are folded in by a one-off, owner-approved data step; it is not part of Stage 1.

## 8. E6 and E7: solution outcomes, string-id fix, reply influence log

**E6a** `pi_solution_memory.problem_uuid` (Uuid null, scoped FK to `pi_problems`), filled for new rows from `problem["id"]` where it parses as a uuid (FACT `solution_ideas.py:286` passes the problem id as a string); old rows stay null. Index `(tenant,env,problem_uuid)`.

**E6b `pi_solution_outcomes`**: `id`, scope, `customer_id`, `box_id` (scoped FK to `pi_solution_boxes`), `document_id` null, `problem_id` null, `state` (`implemented`, `verified`, `delivered`, `failed`, `abandoned`), `evidence` (text, redacted), `evidence_ref` (message id, payment id or file id), `recorded_by` (owner/staff/system), `verified_by` null, `recorded_at`, `knowledge_state`. Append-only by rule (superseding rows, never update). States beyond `S13_IN_BUILD` need owner approval (OWNER DECISION: delivered marker). Unique `(tenant,env,box_id,state,evidence_ref)`. Erase: with the customer unless the owner keeps delivery records as business records (quotes and payments are already kept, FACT `brain_erase.py` docstring).

**E7** `pi_reply_audits.memory_used` JSONB null: list of `{kind, id, state}` of memory items placed in the prompt, ids only, no text. Written with the audit row; erased with it (FACT: reply audits belong to the existing audit lifecycle; I did not read their erase rule: UNVERIFIED).

**E8** constraint element shape inside `pi_problems.constraints` (no DDL): `{id, kind (budget|staff|deadline|cannot_change|other), text, value, scope (problem|business), source_message_id, state (owner-confirmed|pi hypothesis|withdrawn|superseded), valid_to, said_at}`. The reader `requirements_read.parse_constraints` must accept both the legacy shape (strings and `{kind,text}`, FACT case-format doc section on constraints) and the new one.

## 9. Conflict and versioning policy

| Situation | Rule |
|---|---|
| New value, same key, from the owner | write a new version; old becomes `superseded` with `valid_to`; owner statement beats everything else; history kept |
| New value from a document or page vs owner-confirmed value | keep both; the owner value stays active; the other is `disputed` and may be asked once if it affects a decision (A4: ask only when it affects a decision) |
| Two owner statements disagree (this chat vs earlier) | later wins by date; earlier `superseded`; if the owner says "no, I meant ..." that is a correction (revision `by=person`) |
| pi hypothesis vs owner statement | hypothesis is dropped to history; it never overwrites |
| Withdrawal ("not true anymore") | state `withdrawn`, `valid_to` now, value hidden from prompts and kept for history; erase request is different (hard delete) |
| Staff edit | recorded with actor `staff`; weighs as owner-confirmed only if the dashboard edit is an owner-role action (INFERENCE; owner decision) |
| Same text repeated | idempotent: same content hash does nothing (FACT `pi_memories` unique on `content_hash`) |
| Both kept | the bundle shows the disputed pair and says it is unresolved; no gate uses either |

## 10. Memory-update pipeline stages (design; Stage 2 builds, ADDENDUM A5)

| # | Stage | Existing piece | New piece |
|---|---|---|---|
| 1 | identify tenant, environment, customer; reject cross-scope ids | `WorkspaceScope` | none |
| 2 | language and script | PS-9 `language_script` (not wired) | wiring by flow lead |
| 3 | extract | `problem_extract`, problems ops, B2a, profile | document extractor (E1) |
| 4 | detect correction or withdrawal | revisions by person; cause withdrawal tests exist on ps-flow (`test_pi_cause_withdrawal.py`, not run by me) | shared detector |
| 5 | compare with memory | PS-8 bundle | comparison helper |
| 6 | dedupe and conflict | content hash; none for conflicts | conflict policy (section 9) |
| 7 | validate provenance | `source_message_id` on memory rows | require a source on every owner-confirmed write |
| 8 | transactional write with history | `begin_nested` savepoints | one contract function |
| 9 | rebuild derived views | `sync_context`, `memory_block.refresh` | summary and block rebuild (section 12) |
| 10 | quality checks | PS-10 `self_review` (14 of 16 checks per plan; not run by me) | memory checks added to PS-10 |

## 11. Validity and decay

| Item | Rule |
|---|---|
| Owner-confirmed identity facts | no automatic decay; shown with `confirmed_at`; asked again only on a trigger (a conflicting observation, a stated change, or an owner-set review age) |
| System-observed facts (website, page) | `fetched_at` age drives staleness; stale facts are not used for gates and are re-read before use |
| Constraints | active until `valid_to` or withdrawal; expiry date checked at read time |
| Decisions | valid until superseded; a quote past `valid_until` (FACT column on `pi_brain_documents`) is expired, not deleted |
| pi hypotheses | never decay into facts; they are re-derived each time, never confirmed by age |
| Rejections | active until reversed; time limit only if the owner stated one |
| Document extracts | valid while the file exists; a replaced file creates a new extract version |
| Learned (industry) content | never decays into owner memory; stays data below the rules (CLAUDE.md) |

## 12. Summary regeneration

| Rule | Detail |
|---|---|
| Summaries are views | `pi_conversations.summary` (FACT, with `summary_message_count`) and the 700-char `what_i_know` block are rebuilt from records, never the only copy |
| Trigger | a correction, withdrawal or supersession of an item that the summary cites; or `summary_message_count` older than N messages (N owner/engineering decision) |
| Content | each summary line carries the source ids it was built from (stored next to it as JSON in the same row; no table); lines whose source is superseded are dropped on rebuild |
| Order | rebuild after the write transaction commits, outside it; failure leaves the old summary and logs a count only (log counts, never the owner's words: PS-8 rule) |
| Erase | summary text blanked with the conversation, as `brain_erase` already does for `service_brief` (FACT) |

## 13. Transparency, export, correction, deletion design (reuse, no new route family)

| Capability | Reuse | Change |
|---|---|---|
| "What do you remember" in chat | `memory_block.memory_reply` | render from the PS-8 bundle, list each item with its source label and date; needs wiring of the chat phrase to export-like output (plan A1: RMEM05 not wired) |
| "Why do you remember X" | `source_message_id`, `evidence_snippet`, `source_message_ids` | one explanation function over the bundle (gap M7) |
| Export | `GET /customers/{id}/export` (`inbox_routes.py:550`, permission `pi.customers.export`, audited) | add problems (+ revisions, links), boxes (+ transitions), brain documents, solution memory, profile facts and history, extracts, rejections, outcomes, decisions; same permission and audit |
| Correction | `PATCH /memory/{id}` (`inbox_routes.py:517`) | route all corrections through the contract: archive old, write new with `by` and reason; extend to profile facts and constraints |
| Withdrawal | problem `withdrawn`, cause `withdrawn` | one owner phrase set, same state vocabulary |
| Deletion | `erase_customer` and `brain_erase_routes.py` | every new table adds a step to `REMOVED_KEYS`; the completeness test (`pi/r-ft01` `60b1fa66`) must list the new tables; chat "delete everything" stays a staff action until the owner decides (open) |
| Owner control surface | dashboard business profile edit (`business_profile_routes.py`, FACT exists) | show state and source per fact |

## 14. Migration and compatibility plan (design only)

| Step | Content | Owner approval |
|---|---|---|
| M-A | E4, E5 (history table), E6a: additive columns/table, no data change | yes |
| M-B | E1 tables | yes (privacy review) |
| M-C | E3, E6b | yes |
| M-D | E2 only if proven needed | yes |
| M-E | E7 | yes |
| Each | `upgrade` and `downgrade` pair; offline `--sql` file under `docs/pi-saas/migrations-00NN.sql` like earlier ones (FACT: `migrations-0034-0040.sql` to `migrations-0054.sql` exist); pasted into Neon only when the owner asks (CLAUDE.md) | |
| Tests before shipping | model/migration parity, a fresh-database upgrade on the disposable database (`. ../../scripts/pi-test-env.sh`), erase completeness, cross-tenant isolation | |

## 15. What this design does not decide

pgvector and embeddings, RLS, retention periods, whether staff edits count as owner-confirmed, the delivered marker, the retention of files and extracts. These are in `pi-stage1-roadmap-and-blockers.md` section 3.
