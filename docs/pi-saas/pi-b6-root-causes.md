# B6: why pi asks for facts the owner already gave (2026-10-30)

Diagnosis first, fixes after. Each cause says how it was shown: **reproduced** (a scripted turn on the
disposable database, with a control) or **read in code** (not run end to end).

## Where facts live

| place | holds | reach |
|---|---|---|
| history (`prepare_context`, `service_conversation.py`, `.limit(20)`) | the last 20 messages | this conversation only |
| `service_brief` | closed slots, asked facts, requirements | this conversation only |
| problem records (`ProblemBook`) | problem, where, frequency, impact, since, cause | the customer, across conversations |
| durable memory (`memory_block.py`) | 10 keys: name, role, business_name, business_type, location, team_size, channels, current_tools, website, goal (+ language) | the customer, across conversations |
| business profile tables | name, what they do, places, size | only when the warm-up flag is on; only the warm-up writes it |

Memory is written only from the **model's** `customer_profile` output; no code reads the owner's text
for facts. R-MEM-02 guards re-asks of those 10 keys, R-ASK-03 guards frequency, closed slots guard
pi's own questions, and the opt-in `fact_ask` gate (count, duration, frequency) looks only in the
20-message window.

## Causes

1. **A new conversation forgets (reproduced).** `runtime.py` opens a new `PiConversation` when the
   sender has none `open`. Its brief starts with `clarify_count` and `quiet_replies` only, so
   `closed_slots` is empty. `slots.py` says closed slots stay closed across sessions; they do not.
2. **The extractor's note is lost in a rewrite (reproduced, with control).** `turn = retry.value`
   replaced the whole turn, including `problem_ops` from `problem_extract.extract`. Same message:
   a guard forces a rewrite, 1 extractor call, 0 problem rows; no rewrite, 1 problem row.
   *Fixed (S1).*
3. **The extractor could not carry since, money, count or impact (reproduced).** `SimpleNote` had no
   such fields, so `noted_problems[].missing` listed `since` and `impact` although the owner had said
   them, and the prompt tells the model to ask about what is missing. *Fixed (S2).*
4. **A short question's repeat was never caught (reproduced).** `same_question` needed three content
   words, so "Which shop is it?" was not the same as itself; with no model-named slot the repeat
   passed. *Fixed (S3).*
5. **No store for the other facts (read in code).** Shops, stock value, tools beyond the 10 keys, staff
   attendance live only in the window or in a problem record. After 20 messages they depend on the
   record. Not reproduced end to end.

## Tenant, freshness, source, conflicts

- Tenant: profile, memory, problems and slots are all scoped by tenant and environment. The
  learning surfaces have a two-tenant test; **memory and profile do not yet**.
- Freshness: facts carry no date; slots never expire. Only corrections archive an old value
  (memory R-MEM-04, `correct_figure` for figures).
- Source: profile facts carry owner, page or photo and a confirmed flag; memory facts carry none.
- Conflicts: in memory the last write wins; a confirmed owner fact is not overwritten by a page.

## Open, needs the owner

- S4 (done, `slot_carry.py`): `closed_slots` and `asked_facts` are copied once into a new
  conversation of the same customer and workspace. Answered questions stay closed for 30 days,
  unanswered asked facts for 2 days; the generic "anything else?" slot, questions holding personal
  data, erased chats and any other key are never copied; copies are marked `carried`;
  `erase_customer` already clears every conversation of the customer, copies included.
- S5: let `fact_already_given` also read problem records, memory and the summary, and cover
  since, cost and staff count. Stays opt-in until measured with a real model.
- S6: a small stated-facts ledger (key, value, source message, date). It belongs with B2.
- Not checked: how often live models leave `asked_slot` or `customer_profile` empty; two messages
  with a slow first reply (Audit Run 2, R3).
