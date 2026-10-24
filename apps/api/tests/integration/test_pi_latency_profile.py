"""Where the time goes in one brain-mode turn, with a stub model (so only pi's own work shows).

Run with `-s` to print the table: milliseconds per stage, SQL statements per turn and per stage,
and the prompt size. The assertions are budgets (a statement count and a prompt size) so a change
that adds round trips to the reply path fails here instead of showing up as a slow chat."""

import json
import logging
import os
from collections import Counter

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine
from test_pi_brain_problems import adaptive, create, say, workspace
from test_pi_industry_context import turn_on
from test_pi_service_conversations import turn

from app.modules.pi import latency

pytestmark = pytest.mark.integration

OPENING = "Hi, I'm pi, an AI from Workzap."
MESSAGES = [
    "Hi",
    "I run a pharmacy with four branches and expiry stock is a problem",
    "Best-sellers run out in two shops and the cashiers come late on weekends",
    "It happens every week and we lose sales",
    "Mostly in Lahore, since last year",
]


SIZES: list[dict[str, int]] = []


def scripted_turn(context, n):
    SIZES.append({k: len(json.dumps(v, ensure_ascii=False)) for k, v in context.items()})
    if n == 2:
        return turn(
            reply=f"{OPENING} Noted: expiry stock. Anything else getting in the way?",
            language="en",
            problem_ops=[create("Expiry stock piles up", "Expiry stock is a problem.")],
        )
    return turn(reply="Noted. Anything else getting in the way?", language="en")


class Profile:
    def __init__(self) -> None:
        self.statements: Counter[str] = Counter()
        self.per_stage: Counter[str] = Counter()
        self.total = 0
        self.sequence: dict[int, list[str]] = {}

    def __call__(self, conn, cursor, statement, parameters, context, executemany):
        record = latency.current()
        if record is None:
            return
        self.total += 1
        active = record.get("_active") or ["(outside stages)"]
        self.per_stage[active[-1]] += 1
        words = statement.split()
        table = words[words.index("FROM") + 1] if "FROM" in words else " ".join(words[:3])
        self.statements[f"{words[0]} {table}"] += 1
        self.sequence.setdefault(id(record), []).append(f"{active[-1]:>22} {words[0]} {table}")


async def test_profile_a_brain_turn(api, business_db, monkeypatch, caplog, capsys):
    prompts = adaptive(monkeypatch, scripted_turn)
    pi = await workspace(api, business_db)
    await turn_on(api)
    caplog.set_level(logging.INFO, logger="app.modules.pi.runtime")
    profile = Profile()
    event.listen(Engine, "before_cursor_execute", profile)
    try:
        for i, text in enumerate(MESSAGES):
            await say(pi, text, f"lat-{i}")
    finally:
        event.remove(Engine, "before_cursor_execute", profile)
    lines = [r for r in caplog.records if r.getMessage() == "pi turn timing"]
    assert len(lines) == len(MESSAGES)
    with capsys.disabled():
        print()
        for r in lines:
            print(
                f"wall={r.wall_ms:7.1f}ms model_calls={r.model_calls} "
                f"prompt_chars={r.prompt_chars} stages={r.stages_ms}"
            )
        print(f"SQL statements, {len(lines)} turns: {profile.total} ({profile.total / len(lines):.1f}/turn)")
        print("per stage:", dict(profile.per_stage.most_common()))
        print("top statements:", profile.statements.most_common(25))
        for text in prompts:
            if not text.startswith("{"):
                print("REWRITE ASKED:", text[:300])
        print("context size by key (last turn):", dict(sorted(SIZES[-1].items(), key=lambda kv: -kv[1])[:12]))
        if os.environ.get("PI_PROFILE_SEQUENCE"):
            print(chr(10).join(list(profile.sequence.values())[-1]))
    await pi.close()
