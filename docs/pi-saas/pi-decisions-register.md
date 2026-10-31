# PI decisions register (2026-10-31)

Taken by the coordinator under the owner's delegation ("take the better decision yourself").
Rule used: pick the safer, reversible option that matches CLAUDE.md non-negotiables and the
specs' own precedence; never decide money, security, privacy retention, production or
real-model spend. Every row says how to reverse it. The owner can overrule any row.

## Decided (reversible, in force for Stage 2 work)

| # | Question | Decision | Why | Reverse by |
|---|---|---|---|---|
| 1 | Is a bare "ok" a yes? (ROFFER03 vs yes-classifier list) | No. "ok", "hmm", "maybe", "let me think" are never a yes. The classifier list must not contain a bare "ok". | CLAUDE.md non-negotiable; fail-safe (a missed yes costs one more question, a false yes starts a quote). | Owner changes CLAUDE.md and the classifier test. |
| 2 | Ideas cap (RVAL02: 4 per conversation vs Book 5 decision 5) | Keep 2 per problem, up to 8 per business (current code, CLAUDE.md). | The specs' precedence table lets Book 5 win over Book 3; code already matches. | One constant in `brain_config.py`. |
| 3 | D-1: a price question at the offer | Answer it first; it does not start the quote. Only an explicit request for the quote or price document (R1) does. | Keeps "a question is not a yes". | Owner approves BS1 text literally; one gate in `decisions.py`. |
| 4 | Warm-up first message: fixed template vs model-written (18.2) | Model-written with the fixed line only as the fallback after two failed gate attempts. Fallback stays and is logged. | Safe; matches live behaviour. | Remove the fallback (then a failure sends nothing). |
| 5 | `ask_which_language` wording | Use the existing fixed-line mechanism with a short neutral line in the owner's last script plus English; mark every translation "needs native review". | No spec rule; reversible text only. | Edit the fixed lines. |
| 6 | Dashboard login with the customer's number as the password (Book 5 4.9, ST1-ST12) | Not built. Keep the existing two-step portal. | CLAUDE.md: never accept a password or OTP in chat; the audit's F7 advice. | Owner's explicit security approval, then a new lane. |
| 7 | Erase from chat ("delete everything") | No automatic erase. The owner gets an acknowledgement and a staff-approval request that reuses `brain_erase.py`. | Destructive and irreversible; retention rules are undecided. | Owner sets retention (R1-R6) and approves automation. |
| 8 | pgvector / embeddings | Not now. Retrieval = exact SQL + keyword + graph + validity/tenant filters first. | Cost and privacy are owner decisions; no ANN index exists. | Owner approves cost and indexing. |
| 9 | Postgres RLS (d8) | Defer. Keep scoped SQL and composite FKs (ADR 0004) plus two-tenant leakage tests. | Large change; current scoping is tested. | Owner commissions d8. |
| 10 | "Delivered/verified" marker | Design only. Prepare an additive migration and its SQL on the disposable database; do not apply to Neon. | Needs a migration; nothing stores delivery today. | Owner reviews the SQL, then applies. |
| 11 | Memory additions (decisions ledger, constraint validity, rejection store, extracted document text) | Derive first (PS-8 already derives decisions). Add structures only where the gap analysis proves derivation insufficient, each as a small additive migration prepared on the disposable database only. | Avoid new parallel stores. | Owner approves each migration. |
| 12 | Failing "known" tests | Stale tests are updated deliberately with a written reason; real production bugs are listed, not hidden. | Honest baseline. | n/a |
| 13 | Merge policy | Docs and test-only: merge after review. Live-path code: only after an independent PASS audit, fast-forward, full unit run, no new failures against the clean baseline. | The owner's safeguards. | n/a |

## Not mine to decide (still waiting for the owner)

- SEC-1 design and `quotes.approve`.
- Safety model-hybrid pilot (spend, provider, retention, privacy wording, who writes the held-out corpus).
- Neon migrations 0053/0054, any migration or deploy on production.
- Real-model replay budget and key; embedding spend.
- Erase gaps G11-G14 and R1-R6 retention periods; Appendix D-4 retention and D-6 Meta templates (go-live blockers).
- Level 3 tool registry and `PI_EXECUTION_SEAL_KEY`.
- Two named human reviewers for FT-A3; evaluation thresholds and per-industry case counts.
- The remaining Book 5 Part 15 and Appendix D decisions not listed above (see the traceability matrices).
