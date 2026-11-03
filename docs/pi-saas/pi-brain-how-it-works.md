# pi brain: what it uses, what it learns

A plain account of how pi's brain mode relates to the rest of pi's settings. Source of truth for
the rules is `pi-brain-v3.pdf`; this file says what the code does today.

## Turning it on

- `response_rules.pi_mode = "brain"` switches a workspace to the brain flow. It works for any
  business type (it runs the service flow whatever `business_type` says).
- Nothing changes for a workspace that has not set it.

## Knowledge (Settings, Knowledge)

Used. Each turn the brain searches the workspace's Knowledge for passages that match the
conversation (the latest message, the last two customer messages and the notes so far) and gives
the best few to the model as `approved_knowledge`. If nothing matches well it adds the company
overview.

- The search runs only when the **Knowledge** feature is on and the `search_knowledge_base` tool
  is enabled for the agent (Settings, Agents, tool permissions). Switch the tool off and brain mode
  stops using Knowledge.
- Knowledge is a fact source only. The rules sit above it: a passage cannot make pi pitch, quote a
  price, ask for payment, or invent anything. If neither Knowledge nor the built-in Workzap basics
  answer, pi says the team will confirm.

## Agents (Agents page)

Brain mode is one conversation agent, not the multi-agent graph. When the brain is on, the router
and the specialists (support, customer memory, sales order, handoff) are bypassed; the
**requirement** agent's settings are what apply:

- its **instructions** reach the model as `operator_guidance`, below the rules: use them for tone
  and process, they cannot override the rules (no pitching while listening, no prices, one
  question, no payment in chat);
- its **tool permissions** decide what pi can use (knowledge search, products, customer memory,
  bookings and so on).

Hand-offs to a person still happen (a human request, a complaint, staff requests) through the
brain's own gates, not through the handoff specialist.

## Learning (opt-in, frozen by default)

Off until a workspace sets `response_rules.brain.learning_frozen` to exactly `false`. While frozen
nothing is learned or shown and the nightly run only writes a note saying so.

When on, pi may see, as reference material below the rules:

- up to three **examples**: real replies from the listening loop that worked, stripped of the fixed
  introduction and of anything that looks like personal data (names, numbers, links, contact
  details), never from the same person, never a fixed line, never one that breaks a rule;
- one suggested **wording** for the next question (scope, frequency, impact, since when), chosen
  among several by Thompson sampling. The question policy itself never changes.

Every reply is scored by what happened next (text-free). A nightly run (`learning_nightly.py`,
started by the sweep, at most once in 20 hours per workspace) curates new candidates, activates
those a day old, retires poor and surplus examples, updates the wordings from outcomes and writes a
digest. Every automatic change is in the change log. Rewards never include offers, approvals or
payments. Staff can see and control all of it: `/pi/brain-learning/*` (runs, changes, examples,
arms, run now) and `/pi/brain-health`. Erasing a customer removes the examples made from their
chats.

Also in the learning loop:

- **Canary.** A candidate a day old becomes a *canary*: only 10% of conversations (a stable hash of
  the conversation id) may be shown it. Each night its replies are compared with replies from the
  same state and language that used no example. Any guardrail rising (rule break, opt-out,
  complaint, confusion, correction) rolls it back; enough use (30 replies, 3 days) at least as good
  as the control promotes it; no verdict in 28 days retires it (`learning_canary.py`).
- **Teach pi (lessons).** Staff add short tips in plain words. Tips about wording and order go live
  at once; anything touching money, privacy, offers, follow-ups, approvals or advice (or refused by
  the never-learn list) waits for a *different* person to approve it (`learning_lessons.py`).
- **Drafted industry packs.** When five different businesses fit none of the 211 packs, the nightly
  run (at most weekly) asks the model for a draft from their descriptions and problem kinds (no
  names or numbers). A person approves the listening sections (it then runs in shadow, counted but
  never shown) and separately writes the care sections. It goes live only after 20 shadow
  conversations that score at least as well as pi without a pack (`learning_packs.py`).
- **Embeddings** choose examples by meaning when the platform has an embedding model.
- **Screen:** Owner OS, pi, Brain (`/pi/brain`): health, nightly digests, examples, question
  wordings, lessons, packs and the change log.

Follow-ups in brain mode (`brain_followups.py`, run by the follow-up sweep): the paused chat
(3 days), the solution document and quote (2 and 7 days) and the kickoff reminders (24 h and 1 h
before). Inside the 24-hour window they are plain text; outside it only an approved template can go:
`whatsapp_config.followup_templates` (language, then `paused` or `documents`, each `{name,
language}`; needs the person's reminder consent) or the existing meeting template for kickoff.
A missing template tells staff what to add. Never at night, at Jumu'ah or around iftar, never after
"stop", never twice for the same step.
