"""Scratch (never commit): one real-model conversation per industry, from that industry's own data.

Needs OPENAI_API_KEY in the process environment (never written to a file), REAL_OUTDIR for the
results, and optionally REAL_INDUSTRIES (comma list of keys) or REAL_SHARD="i/n" to split the 211
industries across parallel runs. Source scripts/pi-test-env.sh in the SAME shell first.

Each industry gets a fresh workspace and the owner says, in the industry's own language: hello,
their problem (the PDF's sample person line), a detail, "give me a solution", the second problem in
their own words, "how exactly?", and "yes, document and quote". Pi is told nothing about the
industry, so detection, matching, ideas, the offer and the rules are all exercised for real.
"""

import json
import os
import re
import time
from pathlib import Path

import pytest
from sqlalchemy import select
from test_pi_brain_problems import problems_of, say, workspace

from app.modules.pi import constitution, learning_solutions, solutions
from app.modules.pi.language import detect_language
from app.modules.pi.models import PiMessage

pytestmark = pytest.mark.integration

TEMPLATES = {
    "en": {
        "detail": "Yes, it happens every week and I am not sure how much we lose because of it.",
        "ask": "Can you give me a solution for this?",
        "howto": "How exactly would that work?",
        "yes": "Yes please, prepare the document and the quote.",
    },
    "roman_ur": {
        "detail": "Haan, har hafte hota hai aur nuksan ka andaza nahi hota.",
        "ask": "Ap solution dein",
        "howto": "Ye kaise karna hai?",
        "yes": "Haan document aur quote bana dein.",
    },
    "ar": {
        "detail": "نعم، يحدث كل أسبوع ولا أعرف حجم الخسارة.",
        "ask": "أعطني حلاً لهذه المشكلة",
        "howto": "كيف بالضبط؟",
        "yes": "نعم، جهزوا المستند وعرض السعر من فضلكم.",
    },
}


def _industries() -> list[str]:
    keys = solutions.industries()
    if wanted := os.environ.get("REAL_INDUSTRIES"):
        return [k for k in wanted.split(",") if k in keys]
    if shard := os.environ.get("REAL_SHARD"):
        i, n = (int(x) for x in shard.split("/"))
        return [k for j, k in enumerate(keys) if j % n == i]
    return keys[:1]


def _clean(text: str) -> str:
    return " ".join(str(text or "").replace("—", "-").split())


def script_for(key: str) -> tuple[str, list[str], dict]:
    seed = solutions.load(key) or {}
    sample = seed.get("sample_reply") or {}
    problems = seed.get("problems") or []
    person = _clean(sample.get("person", "")) or _clean(problems[0].get("words", "") if problems else "")
    # the stored language label is "en" everywhere: read it from the owner's own words
    language = detect_language(person) or "en"
    language = language if language in TEMPLATES else "en"
    t = TEMPLATES[language]
    second = _clean(problems[1].get("words", "")) if len(problems) > 1 else ""
    if len(second.split()) < 3:
        second = ""
    turns = ["Hello", person or "I have a problem in my business", t["detail"], t["ask"]]
    if second:
        turns.append(second)
    turns += [t["howto"], t["yes"]]
    return language, turns, seed


def idea_hits(seed: dict, reply: str) -> int:
    texts = [i for p in seed.get("problems") or [] for i in p.get("quick_ideas") or []]
    return sum(1 for text in texts if learning_solutions.overlap(text, reply) >= 0.5)


@pytest.mark.skipif(not os.environ.get("OPENAI_API_KEY"), reason="no key")
@pytest.mark.parametrize("industry", _industries())
async def test_one_industry(api, business_db, industry):
    import httpx
    from pydantic import SecretStr

    out_dir = Path(os.environ.get("REAL_OUTDIR", "real_industries"))
    out_dir.mkdir(parents=True, exist_ok=True)
    language, turns, seed = script_for(industry)

    pi = await workspace(api, business_db)
    r = await api.patch(
        "/api/v1/pi/settings/response_rules",
        json={"value": {"brain": {"solution_mode": True, "learning_frozen": True}}},
    )
    assert r.status_code == 200, r.text
    r = await api.patch(
        "/api/v1/pi/settings/knowledge_config",
        json={"value": {"industry_packs": True, "top_k": 5, "min_score": "0.30"}},
    )
    assert r.status_code == 200, r.text
    fake = pi.http
    real = httpx.AsyncClient(timeout=120)

    async def route(request: httpx.Request) -> httpx.Response:
        if "graph.facebook.com" in str(request.url):
            return await fake.send(request)
        return await real.send(
            httpx.Request(request.method, request.url, headers=request.headers, content=request.content)
        )

    pi.http = httpx.AsyncClient(transport=httpx.MockTransport(route))
    pi.ctx["http"] = pi.http
    pi.app.state.settings.openai_api_key = SecretStr(os.environ["OPENAI_API_KEY"])
    pi.app.state.settings.ai_use_default_models = True

    rows: list[dict] = []
    seen: set[str] = set()
    said_so_far: list[str] = []
    for i, text in enumerate(turns):
        started = time.perf_counter()
        error = ""
        try:
            await say(pi, text, f"ri-{i}")
        except Exception as exc:  # noqa: BLE001 - a crashed turn is a finding, not a test error
            error = f"{type(exc).__name__}: {exc}"[:300]
        secs = round(time.perf_counter() - started, 1)
        said_so_far.append(text)
        conversation = await pi.conversation()
        await business_db.refresh(conversation)
        replies = list(
            await business_db.scalars(
                select(PiMessage).where(PiMessage.direction == "outbound").order_by(PiMessage.created_at)
            )
        )
        fresh = [m.body for m in replies if m.body not in seen]
        seen.update(m.body for m in replies)
        reply = fresh[-1] if fresh else ""
        lint = constitution.lint(
            reply, {"pi_mode": "brain", "flow": {"state": conversation.flow_state}}
        )
        _, found = await problems_of(business_db, pi)
        from app.modules.customers.models import Customer

        customer = await business_db.get(Customer, conversation.customer_id)
        rows.append(
            {
                "i": i,
                "customer": text,
                "pi": reply,
                "state": conversation.flow_state,
                "lang": conversation.language,
                "secs": secs,
                "error": error,
                "detected_industry": getattr(customer, "industry_primary", None),
                "ideas_in_reply": idea_hits(seed, reply),
                "tool_words": solutions.banned_tool_words(reply, " ".join(said_so_far)),
                "has_digits": bool(re.search(r"\d", reply)),
                "lint": [f"{v.rule}{'!' if v.hard else ''}: {v.message}" for v in lint],
                "problems": [p.title for p in found],
            }
        )
    result = {
        "industry": industry,
        "expected_language": language,
        "turns": rows,
        "final_state": rows[-1]["state"] if rows else None,
        "detected": next((r["detected_industry"] for r in reversed(rows) if r["detected_industry"]), None),
    }
    (out_dir / f"{industry}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    await pi.close()
