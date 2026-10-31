# pi memory gap analysis: ten missing capabilities and four duplicate paths (Stage 1, documentation only)

Status: PROPOSAL for owner review, 2026-10-31. Companion of `pi-memory-architecture.md` (read its sections 0 and 1 for labels and evidence). No migration, no code. FACT = read in file or `git show` ref; INFERENCE = my reasoning. I ran no test; named tests are claims of their lanes, not results.

Ids: M1 to M10 are the owner's ten capabilities (so they do not clash with erase gaps G1 to G14). D1 to D4 are duplicate paths.

## 1. The ten capabilities

Common to all: "migration" means a new table or column and needs an owner-approved migration (numbers after `0054`, hand-numbered, check `alembic heads`). "Test evidence" is what must exist and be executed before the item is called done; a row count, a screen or a prompt line is not evidence.

### M1 Persistent extracted document text with page, sheet, section references
| Field | Content |
|---|---|
| Why needed | Owner documents (price lists, contracts, sheets) must be searchable and quotable later with an exact reference; today they are summarised once and forgotten |
| Existing | `customer_files.data` bytes (`customers/models.py:139`); `documents.office_text/pdf_text/docx_text/document_text` (`documents.py:67,187`) return text with a label like "PDF, 3 pages" but capped at `MAX_TEXT`; `read_document` returns a summary <=4000 chars used in the prompt (`runtime.py:1055`); `knowledge_documents` stores text but is workspace-wide (no `customer_id`) |
| Missing | any stored text per file; page/sheet/section anchors; per-customer permission on the text; a retention and erase rule for it |
| Must change | new customer-scoped extracted-text store (entities doc E1); readers return per-page/sheet segments instead of one string; redact before store |
| Dependency | owner decision on `customer_files` retention (G13) because erase must cover the text; reader change in `documents.py` |
| Test evidence | integration: upload PDF and XLSX fixture, assert segments with page/sheet numbers; cross-tenant read returns nothing; erase removes segments; redaction test on a fixture with a card number |
| Completion | a question about an old file is answered with the file name and page or sheet, from stored text, after a restart |
| Risk | high privacy (documents may hold ID or financial data); storage volume; scanned PDFs have no text layer (`FILE_UNREADABLE` path) |
| Migration | YES (new table) |

### M2 Versioned decisions with validity and supersession
| Field | Content |
|---|---|
| Why needed | "What did we decide, is it still true, what replaced it" must be answerable; a changed price or scope must not silently overwrite history |
| Existing | derived only: `pi_offer_log` (`rule, allowed, blocked_reason`), `pi_box_transitions` (append-only by docstring), `pi_brain_documents` (`version`, status `superseded`, `approved_by/at`), `pi_open_items`; PS-8 `DecisionItem` (ps8 `context_memory.py:746-800`) reads them |
| Missing | validity window; explicit "supersedes"; who and why for non-document decisions (owner chose option B over A); decision history across conversations |
| Must change | first derive validity from transitions and document versions (no table); add the ledger (entities doc E2) only if a written gap test shows derivation cannot answer "is this still valid" |
| Dependency | M3 (constraints share the validity vocabulary); owner decision on retention of decisions (`pi-decision-retention-review.md` on `pi/s-s7a-audit` `169e4763`) |
| Test evidence | scenario: owner approves option A, later changes to B; context shows A superseded by B with both dates; erase follows the retention table |
| Completion | context bundle returns current and superseded decisions with dates and sources |
| Risk | medium; duplicating the box history would create a second authority |
| Migration | NOT YET (derive first); YES only if the ledger is proven necessary |

### M3 Structured constraints with expiry, withdrawal, scope
| Field | Content |
|---|---|
| Why needed | "no budget over X until March", "cannot stop production" must gate ideas and then lapse or be withdrawn |
| Existing | `pi_problems.constraints` JSONB (B2a, `problem_models.py:112`, migration 0053, on main); parsed by `requirements_read.parse_constraints` (ps-flow); hard gate L2-1 on `pi/l2-hard-gate` `b3f3944a` (not on main; wiring on ps-flow); evalkit constraint kinds `budget, staff, deadline, cannot_change` (case format doc) |
| Missing | element fields `scope` (problem vs business), `source` (message id), `status` (active/withdrawn/expired), `valid_to`; a business-level constraint (today per problem; the earlier design placed business values in `pi_memories` kind `requirement`, `pi-memory-schema-reconciliation.md` section 2) |
| Must change | extend the JSON element shape (no table) per A3; business-level constraint through `pi_profile_facts` keys or a `requirement` row after the contract exists |
| Dependency | PS-flow merge of L2-1; M2 for validity wording |
| Test evidence | withdrawal: owner says the limit no longer applies, the gate stops blocking and history keeps the old value; expiry on date; scope isolation between two problems |
| Completion | all three transitions are covered by executed tests and visible in the bundle |
| Risk | medium; the gate is a safety-adjacent rule, learned content must never relax it (CLAUDE.md non-negotiables) |
| Migration | NO for the JSON shape; YES only if business-level constraints need a table (decided in Stage 2) |

### M4 Owner rejection history
| Field | Content |
|---|---|
| Why needed | pi must not re-suggest what the owner refused, and must remember why |
| Existing | `pi_solution_memory.reaction` (String 12, value `rejected` read by PS-8 `_idea_memory`, ps8 `context_memory.py:887-907`); PS-8 `scan_rejections` (derived from messages); `pi_idea_feedback` (statistics) |
| Missing | owner's own words, source message id, reason, validity (a rejection can be reversed or time-limited); rejection of a document, price or channel (not an idea arm) |
| Must change | extend the contract (not a new parallel store): record kind `rejection` in the contract tables chosen in Stage 2; keep `pi_solution_memory` as the idea-level index |
| Dependency | M2 for decision linkage; M5 for problem link |
| Test evidence | owner rejects idea X in chat A; chat B (same customer) does not offer X and can say why; owner later accepts X, rejection marked reversed |
| Completion | executed scenario above, plus erase test |
| Risk | low to medium |
| Migration | YES if a rejection table is chosen (entities doc E3); NO if the first cut stores the owner's reason in existing columns (not recommended: `reported_result` means something else) |

### M5 Persisted problem relationships and graph edges
| Field | Content |
|---|---|
| Why needed | root causes span problems; PS-7 computes edges but nothing keeps them |
| Existing | `pi_problem_links` (`problem_models.py:143`): type (9), confidence, status suggested/confirmed/rejected, evidence owner_said/pi_inferred/confirmed; written by the model op in `problems.py:957` and `business.py:229`; PS-7 `problem_graph.py` (pure, `d1a33810`): on ps-flow `1653b510` it is imported only by `graph_voice.py` (wording) and nothing persists its edges (FACT `git grep`; at `a07fe1e0` it had no importer) |
| Missing | evidence basis (owner_stated, shared_cause, shared_resource_or_process, category_family), the quote, the source message id, validity; a writer that persists PS-7 edges through the problem ops; mapping PS-7 `EdgeKind` to `LINK_TYPES` |
| Must change | additive nullable columns on `pi_problem_links` (entities doc E4); wire PS-7 output into the existing "link" op with evidence required (spec 4.2/4.3: links must have evidence) |
| Dependency | flow lead wiring (PS-7 is one of the not-wired lanes); the plan's A3 claim that a table is needed is corrected: the table exists |
| Test evidence | PS-7 edge with owner quote persisted once (idempotent re-run: unique `(tenant,env,from,to,type)` already holds); status transitions; cross-tenant isolation (`test_pi_isolation_core.py` exists on main, I did not run it) |
| Completion | edges survive restart, carry basis and quote, and a withdrawn problem hides its edges |
| Risk | medium (wrong edges mislead ranking; hence evidence-only rule) |
| Migration | YES (additive columns); no new table |

### M6 Solution revision and outcome history
| Field | Content |
|---|---|
| Why needed | "what did we offer, what changed, did it work" over months |
| Existing | `pi_solution_boxes.version/parent_box_id`; `pi_box_transitions`; `pi_brain_documents.version/superseded`; `pi_solution_memory.reported_result/said_will_try`; `flow.State` up to `S13_IN_BUILD`; `context_memory_types.IMPLEMENTED_STATES=("delivered",)` |
| Missing | link of `pi_solution_memory.problem_id` (string) to `pi_problems.id` (FK); states beyond in_build (implemented, verified, delivered, failed) with evidence; outcome record with date and who verified; INFERENCE: today nothing writes `delivered` so PS-8 can never report "implemented" |
| Must change | additive `problem_uuid` FK (nullable) and an outcome record or owner-approved extension of box states; keep "a proposed solution is never reported as implemented" (PS-8 guarantee) |
| Dependency | owner decision "delivered marker"; Level 3 (`pi/l3-exec-scope` `56c478d1`, `pi/s-p6-evidence-design` `856c63cc`: P-6 evidence-backed outcome verification design) |
| Test evidence | proposal then approval then work then verified outcome; at each step the bundle reports exactly that state; failed outcome is recalled when the same problem returns |
| Completion | executed scenario; no path reports implemented without a stored verified marker |
| Risk | high (claims to customers; spec forbids promised results) |
| Migration | YES (owner-approved) |

### M7 Memory explanation: why pi remembers X and its source
| Field | Content |
|---|---|
| Why needed | owner transparency requirement |
| Existing | `pi_memories.source_message_id` (nullable); `pi_profile_facts.source/evidence_snippet/source_url`; `pi_problems.source_message_ids`, `pi_problem_revisions.by/reason`; export exposes memory `source_message_id`; `memory_block.memory_reply` answers "what do you remember" from the 700-char block |
| Missing | one explanation function over all stores ("you told me on date, message ..., I used it in reply ..."); the RMEM05 chat path "show me what you keep" is not wired to the export (plan A1); per-reply log of items used |
| Must change | an explanation view over the bundle (section 4 of the architecture doc); record used item ids per reply in `pi_reply_audits` (JSON column addition) |
| Dependency | one reader (D2); knowledge-state vocabulary |
| Test evidence | ask "why do you think I have two shops": answer names source message and date; a fact with no source says so and is marked unknown, never invented |
| Completion | executed test, multilingual (en, Roman Urdu, Urdu, Arabic, Hindi) |
| Risk | medium (leaking another contact's data inside a shared business: R-MEM-06 scope) |
| Migration | maybe (one JSON column on `pi_reply_audits`) |

### M8 Consistent export, correction, deletion
| Field | Content |
|---|---|
| Why needed | subject access and owner control |
| Existing | export route returns customer, conversations, 50 memories, consents, handoffs/tickets, bookings, tasks, 5000 messages (`inbox_routes.py:342-585`); correction route `PATCH /memory/{id}` changes `content` and hash (`:517`; it archives nothing: INFERENCE from the lines read: no history row is written, only an audit record `pi.memory_corrected`); `erase_customer` covers about 30 steps (`REMOVED_KEYS`); chat "delete everything" goes to staff, not automatic (plan A1); erase gaps G10 (links, fixed on `pi/u-erase-g1-g10`, merged), G11 to G14 and R1 open |
| Missing | export of problems, revisions, links, boxes, documents, solution memory, profile facts, files (not returned today); correction through the contract (archive + new row) for facts other than `pi_memories`; erase of any new table; G11-G14 and R1 decisions |
| Must change | one export builder reading the same bundle as retrieval; correction writes history; add an erase step per new table plus the FT-E2b completeness test (`pi/r-ft01` `60b1fa66`) |
| Dependency | owner decisions on G11-G14, R1, retention |
| Test evidence | create data in every store, export, assert every store present; erase, assert nothing remains except the documented kept set (`kept`, `kept_reasons`); correction keeps old value as history |
| Completion | export and erase tests covering 100% of tables listed by the completeness test |
| Risk | high (legal and trust) |
| Migration | NO for export code; YES for any new table's erase (inherits M1-M6) |

### M9 Context reconstruction from authoritative records
| Field | Content |
|---|---|
| Why needed | after a long gap or a deleted summary, pi must rebuild what it knows from records, not from a cached summary |
| Existing | PS-8 `build_context` (read-only, never raises, savepoint per source, `truncated` flags, erased customers return empty bundle; ps8 header); `pi_conversations.summary` regenerated with `summary_message_count`; messages kept verbatim |
| Missing | PS-8 on main (it is on ps8/ps-flow only); summary regeneration rule and source ids; reconstruction test comparing bundle to ground truth across many sessions |
| Must change | merge path decided by flow lead; regeneration rules (entities doc section 7); reconstruction test set |
| Dependency | ps-flow merge; M1-M6 stores |
| Test evidence | historical reconstruction accuracy metric on a labelled long-history set (owner sets threshold before measuring); today: `test_pi_context_memory_pure.py` and `test_pi_context_memory_db.py` exist on ps8 and test the bundle (not run by me) |
| Completion | measured accuracy against owner-set threshold on a held-out history set |
| Risk | medium |
| Migration | NO |

### M10 Retrieval across messages, problems, documents, decisions, solutions, outcomes
| Field | Content |
|---|---|
| Why needed | one question can need all of them |
| Existing | PS-8 reads messages, problems, solutions, files (names only: `FileItem`), decisions, facts, corrections; `knowledge.py` tsvector and `semantic.py` for workspace knowledge |
| Missing | keyword search over owner messages/problems/documents; any search over document text (M1); outcomes (M6); ranking by evidence and validity; conflict detection; per-reply influence log |
| Must change | one ordered retrieval path (architecture doc section 6); semantic is an owner decision |
| Dependency | M1, M2, M5, M6 |
| Test evidence | labelled retrieval set per kind with precision and recall (owner thresholds first); cross-tenant leakage must be 0; multilingual queries |
| Completion | metrics reported on a sealed held-out set; no accuracy claim from development tests |
| Risk | medium to high (cost, privacy if embeddings are enabled) |
| Migration | maybe (index or computed tsvector column) |

## 2. Duplicate paths found

| Id | Duplicate | Evidence (FACT) | Divergence risk (INFERENCE) | Consolidation recommendation |
|---|---|---|---|---|
| D1 | Four fact stores: `pi_memories`, `pi_profile_facts`, `service_brief["business_profile"]`, `customers` columns and `PiProblem.person_believes_cause` | S3, S4, S2, S5, S6 in architecture doc; `memory_block.FACTS` and profile keys overlap (business_name, location, channels, website, goal vs profile fields); `sync_context` already copies profile facts into the brief each turn | a correction in one place is not seen in another; `memory_block.refresh` and the dashboard edit write different tables | Canonical `pi_profile_facts` (+ validity columns). `pi_memories` keeps person-level preferences and requirement rows only, written through the contract; business facts migrate by a data step once approved. `brief["business_profile"]` stays a per-turn mirror (no write path of its own); customers columns and `person_believes_cause` derived. Do not start before the contract exists |
| D2 | Two context assemblers: `memory_block.load/build` (700 chars) and `context_memory.build_context` | section 1.1 of architecture doc; both called in one brain turn on ps-flow (`service_conversation.py:1638` and `:4335`) | two answers to "what do you know"; token waste; erase must cover both | `build_context` is the single reader. `memory_block.build` becomes a renderer of the bundle (same 700-char cap), `memory_reply`, export and delete read the bundle. Done in one lane with the flow lead, behind a test that the old and new blocks agree on a fixture |
| D3 | Solutions in five places: `pi_solution_boxes`, `pi_brain_documents`, `pi_solution_memory` (`problem_id` string), `pi_idea_*` catalogue, `pi_documents` (`pi_saas/deal_models.py:41`) plus `conversation.service_brief` keys | models cited; `solution_ideas.py:286,454,460` writes the string id | an idea, a box, a document and a deal document can disagree on state | Keep each for its own concern (idea reaction, offer/state, versioned document, deal document); add the FK `problem_uuid` on `pi_solution_memory`; the bundle exposes one `SolutionItem` per solution with the exact stored state (PS-8 already does); the deal-flow `pi_documents` is a separate older product flow: audit whether brain mode still writes it (not read) |
| D4 | Two embedding / similarity stores: `knowledge_chunks.embedding_values ARRAY(Float)` + pgvector cast; `pi_learning_examples.embedding JSONB` + Python cosine; also `pi_memories.embedding_model` unused | `semantic.py`, `learning_bank.py:455-462`, `models.py:465,537-539` | different models, no shared index; memories not embedded | Decision first (D-pgvector). If approved: one embedder (`learning_embed.make_embedder` over `app.ai.embeddings.embed`), one vector column type and index, learning examples and (optionally) memories use it. If not approved: keep keyword retrieval only and delete nothing |

## 3. Cross-cutting findings

| # | Finding | Label |
|---|---|---|
| X1 | Wiring on ps-flow moved during this session. At `a07fe1e0`: PS-7 and PS-9 had no importer. At `1653b510`: PS-9 `language_script` is called from `service_conversation.py:1646-1657` (per-turn detection and fixed-line key) and PS-7 from `graph_voice.py`; PS-8 `context_memory` and PS-10 `self_review` were already called. Still absent at `1653b510`: any `current_language` store (RLANG09 conversation-level language is not persisted) and any persistence of PS-7 edges | FACT: `git grep` at both commits |
| X2 | Append-only box history is a convention; `brain_erase.py:322` deletes rows by design | FACT |
| X3 | Correction route for `pi_memories` edits content in place | FACT lines read (`inbox_routes.py:537-538`); history absent is INFERENCE |
| X4 | `pi_memories` unique is `(tenant,env,customer,content_hash)`: same text cannot duplicate, a changed value is a new row by `memory_block.refresh` archiving the old (module docstring) | FACT |
| X5 | The export omits most problem-solving records | FACT (code read) |
| X6 | No store records which memory items influenced a reply | FACT: `PiReplyAudit` stamps prompt/pack versions only |

## 4. Order of dependency (INFERENCE)

contract and reader consolidation (D2, D1) -> M3 JSON shape, M5 columns, M6 FK -> M1 document text -> M4 rejection record, M2 ledger decision -> M7, M8 on the single bundle -> M10 retrieval metrics -> M9 reconstruction metric.
