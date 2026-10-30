# Erase gaps G1 to G14: what `erase_customer` leaves behind

2026-10-30. Docs only. Nothing here changes `brain_erase.py` or any data, and nothing is decided: every
"recommended action" is a proposal for the owner. Source of the list: `KNOWN_GAPS` in
`apps/api/tests/unit/test_pi_erase_completeness.py:51-80` (lane R, FT-E2b); that test scans every table in
the pi, pi_saas, pi_customer, customers, orders, quotes, sales and billing modules that has a
`customer_id` or `conversation_id`, and fails on a table that is neither erased nor listed with a reason.

## 0. What the erase does today (the baseline)

`erase_customer(session, scope, customer_id)` (`apps/api/app/modules/pi/brain_erase.py:128`), reached by
`POST /pi/brain-data/erase/{customer_id}` with `confirm: true` and the permission `pi.settings.manage`
(`brain_erase_routes.py:26-47`), which also writes an audit event. It deletes pi's own brain tables
(problems, map, boxes, offer log, open items, memory, profile, learning, hypotheses, move log, quarantine),
blanks every message body and media (`brain_erase.py:252-258`), blanks conversation summary, preview and
brief (`:259-270`), clears the industry fields on the CRM customer (`:284`). It keeps documents and
payments on purpose (`:286-313`, `kept_reasons`). Everything in G1 to G14 lies outside that list, so it
survives an erase request. It is not a security fault (no cross-tenant read), it is a completeness and
privacy-promise gap: the owner is told the customer's data is erased, and these rows still hold the
customer's words or number.

Scope reminder: every table below except `customer_share_links` carries `tenant_id` and
`environment_id` (`WorkspaceRow`), so an erase can and should filter by `mine(model)` as the existing
code does.

## 1. Priority finding: G10 `customer_share_links.phone`

| | |
|---|---|
| Table / model | `customer_share_links`, `CustomerShareLink` (`apps/api/app/modules/pi_customer/models.py:59-73`) |
| Data | `phone` (String(20), not null, indexed): the customer's WhatsApp number in the clear. Also `conversation_id` (nullable), `token_hash`, `expires_at`, `revoked_at`, `views`. |
| Who writes it | `POST /pi-customer/share` (`pi_customer/routes.py:458-474`): the signed-in customer makes a view-only link; the row stores `customer.phone`. |
| Where it is read | `list_shares` and `revoke_share` filter by phone (`routes.py:481-503`); `open_share` (`routes.py:512-560`, no sign-in, token only) loads `service.conversations(session, link.phone)` and shows the customer's requests (title, stage, next step, urgency, impact, summary) to whoever holds the link. |
| Structure | **No `tenant_id`, no `environment_id`, no `customer_id`.** It is keyed by phone only, and a link with `conversation_id = NULL` covers the customer's conversations in **every** business that has the portal on (`service.py:49-83`). The erase, which is per workspace and per `customer_id`, has no key to find it by. |
| Sensitivity | **High.** A direct identifier (a phone number) that outlives the erase, in a table that also drives an unauthenticated read path. |
| Current erase behaviour | None. Not in `brain_erase.py`; not cascaded. Verified by the static completeness test (listed as a known gap). |
| Can it be reached after an erase? | Yes, in two ways. (a) The row, with the phone, stays in the database for good: expiry only flips a check (`open_share`), nothing deletes expired rows. (b) For up to 7 days (`SHARE_DAYS`) an unexpired, unrevoked link stays live: the erase blanks the old chat, so the link shows nothing for that history, but any **new** chat by the same number after the erase appears on the same old link, because it resolves live by phone. I did not reproduce (b) end to end; it follows from reading `open_share` and `conversations`, so it is VERIFIED BY READING, not by a test. |
| Exposure path | Link holder (a boss or partner the customer chose) opens `/pi-customer/shared/{token}` and sees the customer's requests across businesses. The token is stored only as a hash, so a database reader cannot rebuild the URL, but can read the phone and which businesses/conversations it was scoped to. No cross-tenant leak between businesses' staff was found. |
| Retention purpose | None beyond the link's own 7-day life. The phone on this row is a lookup key, not a record the company must keep. |
| Recommended action | **Erase now.** In `erase_customer`: (1) delete the customer's links scoped to the erased conversations (`conversation_id IN conversation_ids`); (2) for links with `conversation_id IS NULL` and `phone = customer.phone`, **revoke and overwrite the phone** (set `revoked_at = now`, `phone = "erased:" + id`), instead of deleting, because such a link spans other businesses and only the customer's own consent should end the sharing there. Revoking it also stops sharing for the customer's other businesses; that side effect needs an owner yes (see decision R1 below). |
| Code size | Small: about 25 lines in `brain_erase.py`, one integration test (two workspaces, same phone, link with and without `conversation_id`). No migration. Needs the customer's phone from `Customer.phone` (already loaded by the route's caller context; the function loads it with one select). |
| Test to add first | Two tenants, same phone, one link each way; erase in A; assert A's link row is gone or revoked-and-anonymised, B's conversation-scoped link untouched, `open_share` returns 404 for the revoked one, and a new chat after the erase does not appear on it. |

Related, same family, **not in the G1 to G14 list**: `customer_prefs.phone` (`pi_customer/models.py:73-81`)
holds the number plus language and last-seen, keyed by phone, and `pi_conversations.contact_wa_id`
(`pi/models.py:217`) keeps the number on the conversation rows that erase deliberately keeps. The
completeness test only scans `customer_id` and `conversation_id` columns, so a phone-keyed table is
invisible to it. Proposed as new finding **G15** (customer_prefs, owner decision: prefs are the customer's
own settings, probably erase) and a note on the retained `contact_wa_id` (the CRM contact record is kept on
purpose, `brain_erase.py:312`; the owner should say whether "kept contact" includes the number on
conversation rows). Not verified beyond reading the models.

## 2. Table: recommend erase now (clear case)

These hold the customer's own words or are pi-made working notes about the chat; no spec or code reason to
keep them was found, and the erase already blanks the same words in messages and summaries, so leaving
them is inconsistent.

| # | Table (model, file:line) | Columns | Sensitivity | Retention purpose | Current erase | Recommended action | Code size |
|---|---|---|---|---|---|---|---|
| G10 | `customer_share_links` (`pi_customer/models.py:59`) | `phone` | High | none (lookup key) | none | delete conversation-scoped links; revoke and anonymise the phone on all-conversation links (section 1) | S, test needs two tenants |
| G3 | `pi_tickets` (`pi_saas/models.py:587`) | `subject`, `summary` | Medium-high: the customer's problem in words | support history; unknown whether the company must keep a ticket record: owner to decide for the row, but the free text has no record value after erase | none | blank `subject`/`summary` to `ERASED`, keep status and timestamps so SLA counts add up | S |
| G5 | `pi_handoffs` (`pi/models.py:406`) | `summary`, `resolution_note` | Medium-high: summary of the chat | audit of who took over; counts only | none | blank both texts, keep ids, status, timestamps | S |
| G4 | `pi_staff_requests` (`pi_saas/models.py:448`) | `question`, `context_summary`, `answer` | Medium-high: the chat in words | the answer may have been saved to Knowledge (`knowledge_document_id`) as a business fact | none | blank the three texts; do **not** touch the linked Knowledge document (it is the business's own content, separate decision) | S |
| G6 | `pi_pending_actions` (`pi/models.py:378`) | `payload` (JSONB draft order/details), `summary` | Medium-high | none after expiry (a draft, never auto-run) | none | delete rows of the customer's conversations (they are short-lived drafts) | S |
| G9 | `pi_documents` (`pi_saas/deal_models.py:41`) | `message_text`, `response_note` | Medium: words sent to and from the customer | the document itself (quote/invoice link) is a business record; the message text is not | none | blank the two texts; keep kind, quote/invoice ids, `token_hash`, status | S |
| G1 | `pi_conversation_notes` (`pi_saas/models.py:619`) | `body` (internal staff note) | Medium: staff free text about the customer | internal context | none | blank `body`; keep `author_label` and timestamps for the audit trail | S |
| G2 | `pi_conversation_tags` (`pi_saas/models.py:641`) | `tag` (40 chars) | Low | none | none | delete rows of the customer's conversations | XS |
| G7 | `pi_bookings` (`pi_saas/models.py:526`) | `notes` free text | Medium | the booking (time, service, status) is a business record; the free-text note is not | none | blank `notes`; keep the booking row | XS |
| G8 | `pi_tasks` (`pi_saas/models.py:559`) | `title`, `description`, `customer_visible_status` | Medium: the customer's request in words | task history for staff | none | blank the three texts on tasks with this customer or its conversations; keep status/dates | S |

"Clear" means: no spec text or code comment I found asks to keep the free text. It is still the owner's
call (the owner may choose to keep tickets whole). The proposed change shape is the one the code already
uses for messages: keep the row so counts and audit trails add up, remove the words.

## 3. Table: needs an owner retention decision (G11 to G14)

These sit in the CRM and sales modules, which `brain_erase.py` says "the customer module owns"
(docstring, lines 11-15). They are staff-maintained business records, some with legal or accounting weight,
so I do not recommend a silent erase.

| # | Table (model, file:line) | Columns | Sensitivity | Retention purpose | Current erase | Options | Recommended action (proposal) | Code size |
|---|---|---|---|---|---|---|---|---|
| G11 | `customer_notes` (`customers/models.py:96`) | `body` staff free text | Medium | owner to decide: staff memory about a client; may include contractual notes | none | (a) blank body, (b) keep | blank body when the customer asks for erase, keep author and date; owner to confirm | S |
| G12 | `customer_activities` (`customers/models.py:111`) | `summary` (240 chars, one line per event), `ref_type`/`ref_id` | Low-medium: event lines such as "quote sent", may name items | owner to decide: timeline of the relationship; partly derivable from kept quotes and orders | none | (a) keep (no new words from the customer; refs point to kept records), (b) blank summary | keep the row; blank `summary` only if the owner says the timeline must not name the person's requests | XS |
| G13 | `customer_files` (`customers/models.py:134`) | `data` (bytes in the row, up to 25 MB), `name`, `message_id` | **High**: documents and photos the customer sent, possibly ID or financial documents | owner to decide: receipts and quote attachments may be business records (`source` includes `receipt`) | none | (a) delete `source = whatsapp` files, keep `receipt` ones, (b) delete all, (c) keep all | delete files with `source = whatsapp` or `upload`; keep `receipt`; blank `name` on kept ones; owner to confirm, because deleting a file a quote or invoice points to would break that document | M (needs a check of what references a file: `PiStaffRequest.file_id`, `PiDocument.file_id`) |
| G14 | `sales_leads` (`sales/models.py:17`) | `requirements` (JSONB), `notes`, `title`, `missing_information` | Medium-high: what the owner told pi they need | owner to decide: a lead is the sales pipeline; pi writes structured requirements here for human follow-up (`models.py:17` docstring) | none | (a) anonymise the lead (clear requirements and notes, keep stage and value), (b) delete leads that never became a quote or order, (c) keep | (b)+(a): delete open leads of the customer, keep won or quoted leads with `requirements` and `notes` cleared; owner to confirm | M (a lead may link to a quote or order, so the delete needs the same reference check as G13) |

Questions the owner needs to answer, one line each:

- **R1 (G10):** may an erase in one business revoke an "all my businesses" share link of the same phone
  (the customer can recreate it), or should only conversation-scoped links go and the all-business ones
  be left? Recommended: revoke and anonymise, because the row's phone is the problem.
- **R2 (G3):** is a ticket a record the company must keep (SLA, complaints), or only its free text?
  Recommended: keep the row, blank the words.
- **R3 (G11, G12):** are CRM notes and the activity timeline the customer's "data" or the business's
  records? This sets the policy for every future CRM table.
- **R4 (G13):** which file sources are business records? (`receipt` yes by name; `whatsapp` and `upload`
  proposed no.)
- **R5 (G14):** may a lead that never reached a quote be deleted on erase?
- **R6 (G15, new):** include `customer_prefs` by phone, and say what happens to `contact_wa_id` on kept
  conversation rows.

## 4. Order of work if approved (smallest safe first)

1. G10 plus G2 and G6 (delete or revoke; no wording decisions): one commit, tests first.
2. G1, G3, G4, G5, G7, G8, G9 (blank the words, keep the rows; same shape as `messages_cleared`).
3. After the R-answers: G11 to G14 and G15.
4. For each: a failing integration test first (the erase leaves the words), then the change; remove the
   entry from `KNOWN_GAPS` (the stale-entry test at `test_pi_erase_completeness.py:242-249` forces it);
   add an assert in `test_pi_isolation_core.py` that another workspace's row for the same phone is
   untouched; the audit event `pi.brain_data_erased` gains the new counts.
5. The `kept` / `kept_reasons` block (`brain_erase.py:286-313`) must list what is still kept (files,
   leads, notes) so staff can tell the person plainly.

Not in scope here: backups and database snapshots (the real database is Neon, outside the repo; whether
erased rows persist in provider backups is a statement to make to customers, owner to decide) and logs.

## 5. Limitations of this document

- Read from the code at `cc462c5` (models, routes, `brain_erase.py`); no database was queried and no erase
  was run. The "survives after erase" claims come from the static completeness test plus reading, not from
  a fresh reproduction per table. The G10 "new chat appears on the old link" path is reasoned from the
  code and has no test yet; the failing test in section 1 would prove or disprove it.
- Column lists come from the models; `pi_handoffs`, `pi_pending_actions`, `pi_bookings` and `customer_files`
  were read only in part, so a column outside the ones named may also hold words.
- Retention purposes marked "owner to decide" have no statement in the code, the CLAUDE.md or the
  specifications I read for this task; I did not search the six PDFs for retention rules.
- Sensitivity is my classification, not a legal one.
