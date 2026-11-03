Simulate a conversation with pi. Persona: $ARGUMENTS (for example "dairy farmer in Okara, Roman Urdu, 60 buffaloes, milk payments late")

Use the disposable database (`. ../../scripts/pi-test-env.sh`). Build the workspace and conversation
as `tests/integration/test_pi_golden.py` does, with a real or faked model as the user asks (a real
model needs a key in the environment; never read `apps/api/.env`). Play the person realistically for
15 turns. Then show the transcript, the problem records created (`pi_problems`), the flow state after
each turn, the reply linter result per reply, and which examples, wording and pack pi used. Grade it
with the `grader` subagent (never in the same call that produced it) and list any rule break.
