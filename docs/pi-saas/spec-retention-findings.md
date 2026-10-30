# What the seven specs say about retention and erasure (searched 2026-10-30)

Source: the extracted text in `docs/pi-saas/spec-text/` (see `SPEC-INDEX.md`). Searched for: erase, erasure, delete,
deletion, forget, retain, retention, purge, anonymise, GDPR, personal data, data protection, opt-out, consent, "kept for", and
"N days/months/years" near delete/keep. About 550 raw hits; most are the taxonomy label `customers_retention` (customer retention
in the business sense, ignored) or repeats of the same rule across the cumulative spec files. Quotes are kept under 15 words;
everything else is paraphrase. Page numbers are PDF pages of v1.6 unless another file is named; brain-v3 carries the same Book 1 rules.
This is a search of text, not legal advice, and I did not read every page.

## The short answer

**No spec states a retention period for conversations, memory, documents, quotes, payments, consent records or tool-call logs.**
The specs state: (1) a rule that pi must honour a deletion request, with a tool and a table for it; (2) one numeric period, a
30-day expiry for the raw PII quarantine, with "or as Workzap's privacy notice defines"; (3) that learning data cascades on
deletion; and (4) that the actual retention periods are an **open decision for Workzap** that must match the privacy page.

## Findings

| # | Topic | Spec, page | What it says (paraphrase unless quoted) |
|---|---|---|---|
| 1 | Honour deletion | v1.6 p25, RPRIV06 (brain-v3 Book 1 Part 1.5) | pi tells the person what it keeps when asked and MUST honour a delete request: "route to request_deletion" |
| 2 | Deletion tool | v1.6 p77 (brain-v3 p431, p437) | tool `request_deletion`, argument: scope; allowed in any state |
| 3 | Deletion table | v1.6 p79 (brain-v3 p432) | `deletion_requests(id, contact_id, scope, status, completed_at)`; the `scope` values and what each removes are not defined in the text I read |
| 4 | Learning cascade | v1.6 p72 (brain-v3 p427) | every experience, example, arm statistic and lexicon item keeps source conversation ids; deleting a person's data removes their examples and recomputes statistics |
| 5 | Learning test | v1.6 p97 test L11 (brain-v3 p445) | a deletion request for a contact removes their examples, lexicon evidence and statistics |
| 6 | Redact before learning | v1.6 p25, RPRIV07 | a conversation is not used for learning until PII redaction has passed |
| 7 | Raw PII quarantine | v1.6 p53 (Part 6.3) | the raw message goes to an encrypted quarantine with a 30-day TTL, "or as Workzap's privacy notice defines"; a redacted copy goes to the normal message log |
| 8 | Quarantine table | v1.6 p79 | `pii_quarantine(id, message_id, encrypted_payload, expires_at)` |
| 9 | Open decision | v1.6 p100, Appendix D | "Retention periods for messages, quarantine and learning data" must match workzap.ai/pi/privacy: left for Workzap to decide |
| 10 | Return after a gap | v1.6 p174 | a returning owner is recognised "within the retention period, with consent for continued contact"; the period is not given |
| 11 | Delete my account (map product) | v1.6 p196 test ST12 and p205 | the map, login and devices are removed and the box history "follows the retention rules"; the page snapshot is deleted with the account |
| 12 | Open decision for the map | v1.6 p209, decision 13 | the exact retention period for maps and chats and the "delete my account" process are still to be filled in |
| 13 | Consent, opt-out | v1.6 p169 and many follow-up rows (p68, p79, p85 RT17) | the owner is told and can say no; an opt-out is a hard stop on follow-ups; consent for the quick look and for continued contact |
| 14 | Learning from owners | v1.6 p138 (industry solutions p22) | owner ideas are redacted and generalised before they are used |
| 15 | Fine-tuning | v1.6 p75 | a later Workzap decision; only redacted data with clear consent under the privacy notice |
| 16 | Failed tool call | v1.6 p57 (Part 6.11) | if a tool call fails, pi never pretends it succeeded; it tells the person it could not save |

## Answer per data type

| Data | Retention period in a spec? | Erase rule in a spec? |
|---|---|---|
| Conversations and messages | **No** (Appendix D leaves it open, p100) | Honour a delete request via `request_deletion` (p25, p77); the scope values are not defined |
| Raw PII (quarantine) | **Yes: 30-day TTL**, or as the privacy notice defines (p53) | Expires by `expires_at`; part of deletion by scope is not stated |
| Memory (profile and facts) | **No** | Covered only by "honour a delete request"; no separate rule |
| Problems, maps, boards | **No** (map retention is open, p209) | "Delete my account" removes the map, login and devices (p196, p205) |
| Documents and quotes | **No** | **No text found.** The spec keeps old quote versions as `superseded` (rule R-QUOTE-08 at v1.6 p48, brain-v3 p28: "old versions are marked superseded"), which is the opposite of erasing them |
| Payments | **No** | **No text found** |
| Consent and opt-out records | **No** | Opt-out is a hard stop (p85); how long the record is kept is not stated |
| Tool-call logs | **No** | **No text found** |
| Learning data (examples, arm statistics, lexicon) | **No** | **Yes:** cascades on deletion and statistics are recomputed (p72, p97) |
| Box history after "delete my account" | **No** ("follows the retention rules", which are undefined) | Not stated |

## What this means for the open decisions (P-4, R1 to R6)

- The specs support the principle "a delete request is honoured" and give the learning cascade, so erasing a customer's conversations,
  memory and learning examples on request is spec-aligned. They do not say how long anything is kept by default.
- Documents, quotes and payments are not covered by any erase or retention text, so the decision to keep them on an erase (or
  not) is a Workzap decision, not a spec requirement, and the spec's own audit trail for quotes (superseded versions) points to keeping them.
- Appendix D (v1.6 p100) and decision 13 (v1.6 p209) are the spec's own record that these periods are undecided; the owner should
  fill them in and publish them on the privacy page before any default is set in code.
- `request_deletion` and `deletion_requests` exist in the spec. This is relevant to the erase work: the spec expects a request record with
  a `scope` and a `status`; whether the code has an equivalent table was not checked in this task.

## Limits
- The PDF text layer was searched, not read page by page; a retention rule written in an image or a table cell split across lines may be missed.
- `pi-industry-solutions` page 50 has no text layer and was not searched.
- Only v1.6 pages were checked line by line for the findings above; brain-v3 pages are given where the same sentence appears there.
- No search was made of the privacy page on workzap.ai (outside the repository).
