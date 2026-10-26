"""Scratch: a real-model conversation (needs OPENAI_API_KEY in the process environment). Never commit."""

import json
import os
import time

import pytest
from sqlalchemy import select
from test_pi_brain_problems import problems_of, say, workspace

from app.modules.pi import constitution
from app.modules.pi.models import PiMessage

pytestmark = pytest.mark.integration

TURNS = [
    "Hello",
    "mera kiryana store hai Lahore mein, udhaar ka hisaab kitaab mein gadbad hai",
    "kareeb 100 ghar ka udhaar hai, total ka pata nahi chalta",
    "haan staff bhi kabhi entry bhool jata hai",
    "ap solution dein",
    "ye kaise karna hai?",
    "haan document aur quote bana dein",
]
TURNS = json.loads(os.environ["REAL_TURNS"]) if os.environ.get("REAL_TURNS") else TURNS
OUT = os.environ.get("REAL_OUT", "real_model_run.json")


@pytest.mark.skipif(not os.environ.get("OPENAI_API_KEY"), reason="no key")
async def test_real_conversation(api, business_db):
    pi = await workspace(api, business_db)
    r = await api.patch(
        "/api/v1/pi/settings/response_rules",
        json={"value": {"brain": {"solution_mode": True, "learning_frozen": False}}},
    )
    assert r.status_code == 200, r.text
    r = await api.patch(
        "/api/v1/pi/settings/knowledge_config",
        json={"value": {"industry_packs": True, "top_k": 5, "min_score": "0.30"}},
    )
    assert r.status_code == 200, r.text
    import httpx
    from pydantic import SecretStr

    fake = pi.http  # answers the WhatsApp send; everything else goes to the real network
    real = httpx.AsyncClient(timeout=90)

    async def route(request: httpx.Request) -> httpx.Response:
        if "graph.facebook.com" in str(request.url):
            return await fake.send(request)
        forwarded = await real.send(
            httpx.Request(request.method, request.url, headers=request.headers, content=request.content)
        )
        return forwarded

    pi.http = httpx.AsyncClient(transport=httpx.MockTransport(route))
    pi.ctx["http"] = pi.http
    pi.app.state.settings.openai_api_key = SecretStr(os.environ["OPENAI_API_KEY"])
    pi.app.state.settings.ai_use_default_models = True
    from app.modules.pi import solution_context

    original = solution_context.build

    async def traced(*a, **k):
        out = await original(*a, **k)
        print("SOLCTX", json.dumps({k2: v for k2, v in out.items() if k2 != "solution_never_say"}, ensure_ascii=False)[:600])
        return out

    solution_context.build = traced
    from app.modules.pi import problem_extract as _pe
    _orig_extract = _pe.extract

    async def _traced_extract(*a, **k):
        out = await _orig_extract(*a, **k)
        print("EXTRACT", [getattr(o, "note", None) and o.note.title for o in out])
        return out

    _pe.extract = _traced_extract
    _orig_wants = _pe.wants_extraction

    def _traced_wants(ctx, reply, ops):
        r = _orig_wants(ctx, reply, ops)
        print("WANTS", r, ctx.get("flow"), ctx.get("solution_asked"), ctx.get("solution_asked_no_ideas"), len(ctx.get("noted_problems") or []))
        return r

    _pe.wants_extraction = _traced_wants
    from app.modules.pi import solution_free as _sf
    _orig_vetted = _sf.vetted

    def _traced_vetted(ideas, said, never):
        out = _orig_vetted(ideas, said, never)
        from app.modules.pi import solution_rules as _sr
        print("FREE raw=", ideas, "kept=", out)
        for i in ideas:
            v = _sr.check_idea(i, said)
            print("   verdict", v.reject, v.review, i[:60])
        return out

    _sf.vetted = _traced_vetted
    from app.modules.pi import service_conversation as _sc
    _orig_compose = _sc.compose_service_turn

    async def _traced_compose(*a, **k):
        t = await _orig_compose(*a, **k)
        print("COMPOSE ops=", [(o.op, getattr(getattr(o, "note", None), "title", None)) for o in t.problem_ops], "action=", t.action, "reply=", t.reply[:80].replace(chr(10), " / "))
        return t

    _sc.compose_service_turn = _traced_compose
    from app.modules.pi import runtime as _rt
    _orig_loc = _rt._localized

    def _traced_loc(notices, typed, lang):
        import traceback
        print("NOTICE", list(notices.values())[0][:50], "| stack:", [f.name for f in traceback.extract_stack()[-4:-1]])
        return _orig_loc(notices, typed, lang)

    _rt._localized = _traced_loc
    from app.modules.pi import service_conversation as _sc2
    _orig_rw = _sc2.rejected_with

    def _traced_rw(turn, code):
        print("REJECTED", code, "reply=", turn.reply[:100].replace(chr(10), " / "))
        return _orig_rw(turn, code)

    _sc2.rejected_with = _traced_rw
    _rt.compose_service_turn = _traced_compose
    rows = []
    seen: set[str] = set()
    for i, text in enumerate(TURNS):
        t0 = time.perf_counter()
        await say(pi, text, f"rm-{i}")
        secs = round(time.perf_counter() - t0, 1)
        conversation = await pi.conversation()
        await business_db.refresh(conversation)
        replies = list(
            await business_db.scalars(
                select(PiMessage)
                .where(PiMessage.direction == "outbound")
                .order_by(PiMessage.created_at)
            )
        )
        fresh = [r.body for r in replies if r.body not in seen]
        seen.update(r.body for r in replies)
        last = fresh[-1] if fresh else "(no new reply)"
        found = constitution.lint(
            last, {"pi_mode": "brain", "flow": {"state": conversation.flow_state}}
        )
        from app.modules.pi.models import PiAgentRun
        runs = list(await business_db.scalars(select(PiAgentRun).order_by(PiAgentRun.created_at)))
        _, problems = await problems_of(business_db, pi)
        rows.append(
            {
                "customer": text,
                "pi": last,
                "state": conversation.flow_state,
                "lang": conversation.language,
                "secs": secs,
                "n_out": len(replies),
                "runs": [(r.error_code, list(r.agent_path)) for r in runs[-1:]],
                "all_out": [r.body[:140] for r in replies],
                "lint": [f"{v.rule}{'!' if v.hard else ''}: {v.message}" for v in found],
                "problems": [p.title for p in problems],
            }
        )
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=1)
    await pi.close()
