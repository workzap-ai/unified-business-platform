# pi rule coverage

Every rule ID in `pi-brain-v3.pdf` and where it is enforced today. The specification asks for each
rule to be (a) a line in the prompt, (b) a guard in code, or (c) an automated test, and for the most
important ones all three. Status: **code** = guarded in code with tests; **prompt** = only asked of
the model; **open** = nothing yet (with the phase that closes it). Update this file in the same
commit that changes a guard. Brain mode = `response_rules.pi_mode = "brain"`.

Files: linter `constitution.py` (tests `test_pi_constitution.py`, `test_pi_redteam.py`) · states
`flow.py` (`test_pi_flow.py`) · problems `problems.py`, `taxonomy.py` (`test_pi_problem_model.py`,
`test_pi_brain_problems.py`) · gates `decisions.py` (`test_pi_decisions.py`,
`test_pi_brain_decisions.py`) · documents `brain_docs.py`, `brain_pdf.py`
(`test_pi_brain_docs.py`, `test_pi_brain_documents.py`).

## Constitution (Part 1)

| Rule | What | Status | Where |
|---|---|---|---|
| R-DISC-01 | First message says it is an AI | code | linter hard rule + `repair` adds the line; fixed opening in `greeting_reply` |
| R-DISC-02 | "Are you human?" answered in sentence one | code | linter plus a fixed pre-model answer (`safety.identity_asked`) |
| R-DISC-03 | No human name, body, gender, place | code | linter `HUMAN_CLAIM` (persona names, places, family, meals) |
| R-DISC-04 | No "a human is reading" unless one took over | open | X_HUMAN is not driven by the inbox handover yet (P6) |
| R-DISC-05 | Re-disclose after 30 days | open | needs last-message age in the opening (P6) |
| R-SELL-01, 02 | No fix, product, document or quote while listening | code | linter by state (S0 to S4, S5b), hard |
| R-SELL-03 | No urgency, scarcity, discount | code | linter, hard (a refusal "I can't give a discount" is allowed) |
| R-SELL-04 | Direct "can you fix this?" gets one honest line | code+prompt | linter lets the line through when asked; wording is the prompt's |
| R-SELL-05 | A no is accepted once, no re-offer | code | `decisions` S5 to S5b; S5b only re-offers when the person raises it |
| R-HONEST-01 | Never invent prices, timelines, features | code | digits and currency blocked in service replies (`price_policy`), money in linter, quote only from reviewer |
| R-HONEST-02 | Say what is not ready (nori Vision) | open | needs the approved company profile (Appendix D) |
| R-PROM-01 | No promised results | code | linter (`will increase`, `guarantee`, `you will save`), documents use "would" |
| R-PROM-02, 03 | Does not decide or forecast for them | prompt | |
| R-PAY-01 | No payment in chat | code | brain mode ignores `action="payment"` (`run_service_action`); the quote carries a bank transfer only |
| R-PAY-02 | Never asks for card, CVV, bank login, OTP, PIN, password | code | linter, hard (verbs and "what is your PIN?") |
| R-PAY-03 | Bank details only on the approved quote | code | linter blocks IBAN and account numbers; details only in `brain_pdf.render_quote` |
| R-PAY-04 | Changed bank details are fraud, escalate | open | P6 (escalation reasons) |
| R-PAY-05 | "Payment received" only when staff confirm | code | linter, hard; only `POST /pi/brain-documents/payments/{id}/confirm` (billing.write) confirms |
| R-PAY-06 | A payment screenshot is thanked, never confirmed | code | `decisions` S10: "I paid", "done" or an image/document makes the payment `claimed` and tells staff |
| R-PAY-07 | Refunds and disputes are noted and escalated | open | P6 |
| R-PRIV-01 | Never asks for card, password, third-party details | code | linter (see R-PAY-02) |
| R-PRIV-02 | Sensitive content redacted from records and logs | code | `safety.redact_pii` + `safety_guard` redact the message log; original encrypted in `pi_quarantine` (0039, 30 days, purged by the sweep); reminder once per kind; card/ID/OTP-only message gets only the reminder |
| R-PRIV-03 | Never asks for national ID, passport, account numbers | code | linter |
| R-PRIV-04 | Roles, not third-party names | prompt | |
| R-PRIV-05 | One contact's chats are never shown to another | code | tenant scope and per-customer records (shared workspaces are open) |
| R-BOUNDARY (RT14, RT15, RT20, RT22, RT24) | Other people's chats, fake invoices, politics, competitor comparison, outcome promises | code | `safety.boundary_asked`, fixed answers before the model |
| R-PAY-04 | Claimed bank-detail change: never confirm, escalate | code | `safety.Boundary.BANK_CHANGE`, fixed reply, high-priority staff request marked possible fraud |
| R-ADV-05 | No general-purpose help (homework, code, jokes) | code | `safety.Boundary.OFF_TOPIC` |
| R-ROUTE-01 | Demo, jobs, vendor, partnership, press enquiries routed, not noted as problems | code | `safety.enquiry_asked`, fixed replies, staff request (nori facts and pricing lines still open) |
| R-DISC-05, R-MEM-03 | Returning after a gap: welcome back, re-disclose after 30 days | code | `welcome_back` in `service_conversation.py` |
| R-PRIV-06 | Says what it keeps, honours deletion | partial | `safety.boundary_asked` DELETION: fixed reply plus a high-priority staff request; the deletion itself is manual, no automated erase yet |
| R-PRIV-07 | Learning only after redaction | open | learning loop not built |
| R-PRIV-08 | Never pressures for detail | prompt | |
| R-ADV-01 to 05 | No legal, medical, financial advice; no politics; no off-topic help | code | `safety.advice_asked` (legal, tax, financial, medical, veterinary) answered with fixed text before the model; politics and off-topic stay prompt |
| R-EMER-01 to 04 | Emergency numbers, stop noting, escalate | code | `safety.emergency` before the model; fixed reply with local numbers (PK, AE, CA/US, all if unknown); X_EMERGENCY; high-priority staff request; next ordinary message returns to S1 |
| R-META-01 | Not made or endorsed by WhatsApp or Meta | code | `safety.identity_reply` (person, gender, scam, Meta, model, rules, company) |
| R-BRAND-01 | Workzap only (never Artwing, a.hub) | code | linter, hard; PDFs use Workzap's letterhead |
| R-ROUTE-01 to 05 | Every enquiry starts with pi | open | enquiries routing (P6) |

## Voice and conversation (Parts 2 and 3)

| Rule | What | Status | Where |
|---|---|---|---|
| R-VOICE-01 | Short (60, summary 160, document cover 120 words) | code | linter, soft |
| R-VOICE-02, R-ASK-01 | One question, and it is last | code | linter, soft |
| R-VOICE-03 | No jargon they did not use | code | linter |
| R-VOICE-04 | Mirror language and register; no same opening twice | code | language guards (`reply_language`) and linter on openings |
| R-VOICE-05, 06 | No hype, no scripted empathy, no template phrases | code | linter |
| R-VOICE-07, 08 | No "!", no emoji (except a tick, or theirs) | code | linter; `repair` fixes it |
| R-VOICE-09, 10, 12 | WhatsApp formatting; "noted" not "logged"; never lecture | code | linter |
| R-VOICE-11, 13, 14 | Their names for things; contractions; British spelling | prompt | |
| R-LANG-01 | "Sorted" is not "solved" | code | linter; summary text |
| R-LANG-02 | Language per message | code | existing language detection and guards |
| R-LANG-03 | Their words kept, English title for Workzap | code | `ProblemNote` (`user_words`, `title`, `title_local`) |
| R-LANG-04, 06 | Lakh and crore, dates like "kal" | open | |
| R-LANG-05 | Currency from the country | code | quote currency from the number (PKR, AED, CAD) |
| R-LANG-07, 08 | Voice notes; religious courtesy | partial | transcription exists; courtesy is prompt |
| R-ASK-02 to 06 | At most 3 clarifying questions; never re-ask; no sensitive asks | prompt | `noted_problems` lists what is missing |
| R-NOTE-01 to 08, R-CORR-01 to 04 | Notes in their words, groups, corrections applied | code | `problems.py` ops with revisions; titles checked |
| R-MEM-01, 02 | Profiles; never ask twice | partial | profile and `noted_problems`; no cross-conversation memory check |
| R-MEM-03, 06 | Welcome back; shared workspace | open | |
| R-MEM-04 | Corrections override, history kept | code | revisions |
| R-CANT-01 to 03 | "I can't do that" and what next | prompt | |
| R-OFFER-01 | Offer only after the summary is confirmed | code | `decisions` S4 |
| R-OFFER-02 | The fixed offer text | code | `decisions.TEXT["offer"]` |
| R-OFFER-03 | Only an explicit yes starts anything | code | `decisions.classify` at 0.9, hedges refused |
| R-OFFER-04 | "All or only some?" once | code | `decisions` S5 |
| R-OFFER-05 | Cost before a quote: honest, no range | code+prompt | cost questions go to the model, numbers blocked |
| R-OFFER-06 | A member who is not the decider | code | `customers.can_approve` |
| R-FUP-01 to 05 | Follow-up policy, quiet hours, opt-out | open | the shared ladder is not aligned to 3.9.1 (P6) |

## Documents, decisions, payment (Part 5)

| Rule | What | Status | Where |
|---|---|---|---|
| R-DOC-00 | A reviewer approves everything first | code | `brain_docs.approve` refuses a rule break; `send` refuses unapproved |
| R-DOC-01 | Section 1 in their words | code | `solution_content` |
| R-DOC-02, 03, 04 | Every component maps to a problem; every problem addressed or listed; "won't do" never empty | code | `check_solution` |
| R-DOC-05 | Plain words | partial | jargon and sentence length; no reading-age score |
| R-DOC-06, 09 | "Would" not "will"; no price in the document | code | `check_solution` |
| R-DOC-07 | Their language plus an English copy | code | `content` and `content_en`; Urdu script and Arabic draw from English (the PDF font is Latin only) |
| R-DOC-08 | Workzap branding only | code | PDF letterhead |
| R-QUOTE-01 | Prices only from Workzap | code | the draft has no price; only a reviewer sets it |
| R-QUOTE-02 | No negotiation; cheaper is a change request | code+prompt | S8b `change_requests` |
| R-QUOTE-03 | Explains only what is printed | prompt | `open_quote` is the only source |
| R-QUOTE-04 | "An offer, not a charge" in the cover | code | cover text and PDF |
| R-QUOTE-05 | Validity never used as pressure | code | linter (urgency) |
| R-QUOTE-06 | Bank details only in the approved PDF | code | |
| R-QUOTE-07 | Currency of the business's country | code | |
| R-QUOTE-08 | A revision is a new version | code | `brain_docs.revise` |
| R-QUOTE-09 | "A quote without the document" | open | prompt line to add |
| R-DEC-01 | Approval needs two confirmations | code | `decisions` S8 |
| R-DEC-02 | Only `can_approve` approves | code | |
| R-DEC-03 | Ask for changes: note, confirm, send to Workzap | code | |
| R-DEC-04 | A no is fine; nothing charged | code | |
| R-DEC-05 | Cancel before payment is accepted | code | S10 |
| R-KICK-01 | After staff confirm, pi tells them and offers kickoff times | code | fixed notice (also after the 24-hour window, on their next message); slots come from the existing booking tools |
| R-KICK-02, 03 | Booked slot confirmed, reminders; no invented agenda | partial | a booking moves S11 to S12; reminders 24 h and 1 h are P6 |
| R-COMPL-01 to 03 | Complaints are feedback, escalated | open | P6 |

## Red-team (Part 10.2) and what is not covered yet

Covered by tests (`tests/unit/test_pi_redteam.py`): RT1, RT2, RT3, RT4 (as text that cannot move a
gate), RT5, RT6, RT7, RT12, RT13, RT23, RT24, RT25, RT26.

Open, in the order they should be built: RT10 and RT28 (emergency classifier), RT6 and RT21 (PII
detection in the message log), RT8 (changed bank details), RT9 and RT27 and RT20 and RT22 (advice
and opinion limits), RT14 (other people's chats), RT15 (illegal requests), RT16 and RT17 (deletion
and opt-out), RT18 (burst debounce), RT19 (languages not supported), RT29 (served trades).
Golden conversations G1 to G15 (Part 10.1) are built as scripted tests as their phases land:
G5, G10, G11 and G13 are covered by `test_pi_brain_decisions.py` and `test_pi_brain_documents.py`.
