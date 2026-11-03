# pi's solution engine: one independent engine

Owner decision, 2026-10-27: pi must not depend on a pre-written pack entry matching. The models
already know each industry; pi gives them the owner's own words and the rules, and vets what comes
back. There is ONE engine for this: the expert advisor (`expert_advisor.py`, switched on with
`response_rules.brain.solution_source = "expert"`; the SQL is `docs/pi-saas/enable-expert-workzap.sql`).
A second "independent" mode that was built in parallel was dropped so that there is one engine.

## The path of one request for a fix

1. Router and guards as always. In expert mode the pack entries are not served first
   (`solution_context._expert_hold`): a request for a fix, and a rejection such as "solution glt hai
   again den", are answered by the expert.
2. **Diagnose** (one call): a senior operator of the owner's trade reads their words and facts, names
   the likely causes as hypotheses, writes candidate ideas and the one missing fact. Examples of level
   come first from the owner's gold ideas (`gold_ideas.py`, 28 trades), then from the matched pack entry.
3. **Judge** (optional, `expert_judge`): six qualities per candidate.
4. **Vet**: the idea guard, owner action, reply linter, the idea filter G1-G8, no promised outcome,
   not already given. Two are chosen.
5. A decisive missing fact and no question asked yet: the one allowed question comes first.
6. **Never a dead end**: if the expert gives nothing, the older free-ideas call tries; if that gives
   nothing, the library category the cue words name gives two ideas (`packs/library/cues.json`, eight
   languages), through the same filter. Only then the honest line.
7. Two ideas per problem, up to eight per business (Book 5 decision 5). Rules are code, not prompt.

The packs, the library and the gold ideas are examples and the safety net, not the first source:
an owner-approved deviation from Addendum 2 Part 2.1.
