# pi knows the client in a meeting (memory in the meeting job)

Part of PMB (`pi-meeting-brain.md`). Branch `pi/meeting-memory`. No migration. Status: built and tested locally.

## Why

On WhatsApp pi knows a returning customer: their name, language, open problems, what an earlier chat settled, what
they said no to. In a meeting it did not: `pilot.py` read only five problem titles and `voice.py` read no customer
memory at all. Now the meeting job uses the same single door the chat uses, `pi/shared_memory.brief()`
(`pi_meetings/meeting_memory.py::load`), so pi does not make the customer repeat themselves.

## The three cases (nothing is guessed)

1. **No memory** (meeting linked to no customer, a new customer, nothing recorded, an erased customer, or the memory
   read fails): `load` returns `{}`. pi behaves exactly as before: the normal opening, no memory in the prompt, no
   pretending to remember.
2. **Someone else opens the link**: the link belongs to a customer, but the person who opens it may be a colleague
   or the wrong person. When memory has a name the person gave pi earlier, the opening is "Hi, I'm pi, an AI
   assistant from Workzap. Am I speaking with <first name>?" (still the AI disclosure first, one question, last).
   The memory is used only after a clear yes. Any "no", any mention of another person (brother, wife, assistant, ...),
   and any unclear answer leaves it unused for the rest of the conversation. pi then says "Sorry about that. Who am I
   speaking with?" (fixed line, the model is not called) and goes on as for a stranger. The state is read from the
   stored transcript lines (`voice.confirm_state`), so a page reload cannot lose or fake it, and only the FIRST answer
   counts (a later "yes" cannot undo a "no"). Yes/no words cover English, Roman Urdu and Urdu script.
3. **Different person, memory never written**: what a different person says stays on the transcript with role
   unknown. It reaches the customer's record only through the reviewer-approved `brain_bridge`, which already writes
   to the customer only for a speaker a person has mapped to them.

## How memory is used

- Voice (pi speaking to a person on a link): the block goes into the prompt under `what_i_know` with the shared rule
  line (`shared_memory.system_line`) plus `voice.MEMORY_NOTE`: private context, never read out like a record, no
  money, numbers or other people's names from it, never say pi has a file on them; a pi guess is not stated as
  something the person said; what they just said wins over it. The reply still passes the same code gate
  (`voice.allowed`: one short question last, no price, no ask for money or ID, `constitution.lint`, safe fallback).
- Pilot (staff-facing next question): gets the block when the meeting is linked to a customer (staff already see that
  record), so it does not suggest a question the customer already answered.
- Meeting Q&A stays **transcript-only** on purpose: every answer cites transcript lines.
- Only an owner-stated first name greets a person (`meeting_memory.first_name`); a pi guess or a staff-record name
  does not.
- The audit entry `pi.meeting_pi_turn` now also holds `identity` (none, pending, confirmed, denied, unclear) and
  `memory` (true/false). Never words.

## Residual risk

A stranger who opens the link and says "yes" gets the same context the link holder would. The link itself is the
credential (staff create it for that customer), pi never recites the memory, and what is said is reviewed by staff
before anything is saved. For video rooms (plan PMB-5) the stronger rule applies: memory is used only for a speaker a
person has mapped to the customer, or a guest whose token is tied to that customer.

## Code and tests

`pi_meetings/meeting_memory.py`, `voice.py` (`opening(name)`, `classify`, `confirm_state`, `NOT_THEM`, `MEMORY_NOTE`,
`reply_to(..., what_i_know=)`), `voice_routes.py`, `pilot.py`, `pilot_routes.py`.
Tests: `tests/unit/test_pi_meeting_memory_rules.py`, `tests/integration/test_pi_meeting_memory.py`, one added to
`test_pi_meeting_pilot.py`.
