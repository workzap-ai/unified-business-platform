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

What is not built yet: a text embedding for similarity (examples are matched by shared words),
automatic pack drafting, a canary rollout, a lessons store, and a screen for any of this.
