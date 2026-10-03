"""pi Assistant: role-scoped business answers in the pi app and operator-managed guides."""

from uuid import UUID

import pytest
from pi_saas_support import FakeProvider, configure, pi_client, pi_register
from test_pi_saas import _member_client
from test_service_lifecycle import register

from app.ai.types import LLMResponse, ToolCall
from app.modules.pi_saas import help_kb
from app.modules.pi_saas.models import PiOperatorMember

pytestmark = pytest.mark.integration
CHAT = "/api/v1/pi-app/assistant/chat"


@pytest.fixture
def app(api):
    app = api._transport.app  # type: ignore[attr-defined]
    configure(app, FakeProvider())
    return app


def test_guide_search_understands_roman_urdu():
    found = help_kb.search(list(help_kb.BUILTIN), "WhatsApp number kaise connect karun?")
    assert found[0].id == "connect-whatsapp"
    team = help_kb.search(list(help_kb.BUILTIN), "team mein banda kaise add karun")
    assert team[0].id == "team-roles"
    assert help_kb.search(list(help_kb.BUILTIN), "??") == []
    assert all(not a.hidden for a in help_kb.BUILTIN)


async def test_owner_gets_guides_and_figures_without_ai(app, api, business_db):
    owner = pi_client(app)
    await pi_register(owner, "Noor Tailors")
    context = (await owner.get("/api/v1/pi-app/assistant/context")).json()
    assert context["can"]["reports"] and context["can"]["billing"]
    assert any(g["id"] == "connect-whatsapp" for g in context["guides"])
    how = (await owner.post(CHAT, json={"message": "How do I connect my WhatsApp number?"})).json()
    assert how["guides"][0]["id"] == "connect-whatsapp"
    assert how["message"].startswith("pi answers your customers on WhatsApp")
    assert how["mode"] == "tools" and "AI answers" in how["notice"]
    week = (await owner.post(CHAT, json={"message": "Is hafte ka summary do"})).json()
    titles = [c["title"] for c in week["cards"]]
    assert titles and titles[0].startswith(("This week", "Report"))
    plan = (await owner.post(CHAT, json={"message": "Mera plan aur usage?"})).json()
    assert any(
        c["title"] == "Plan and usage" and c["href"] == "/settings/billing" for c in plan["cards"]
    )
    assert plan["guides"] == []  # a figures question doesn't drag in setup guides
    report = (await owner.post(CHAT, json={"message": "Report for the last 30 days"})).json()
    metrics = next(c for c in report["cards"] if c["title"].startswith("Report"))["metrics"]
    assert set(metrics) == {"Conversations", "Messages", "Answered by pi", "Handed to your team"}
    await owner.aclose()


async def test_member_role_limits_what_the_assistant_can_reach(app, api, business_db, monkeypatch):
    import app.modules.pi_saas.assistant_routes as routes

    seen: list[list[str]] = []

    class FakeManager:
        def __init__(self):
            self.turn = 0

        async def complete(self, scope, **kwargs):
            self.turn += 1
            seen.append([t.name for t in kwargs["tools"]])
            if self.turn == 1:
                return LLMResponse(
                    "",
                    "test",
                    "test",
                    tool_calls=[
                        ToolCall("1", "billing", {}),
                        ToolCall("2", "report", {"days": 30}),
                        ToolCall("3", "overview", {}),
                    ],
                )
            outputs = [m.text() for m in kwargs["messages"] if m.role == "tool"]
            seen.append(outputs)
            return LLMResponse("Here is your week.", "test", "test")

    owner = pi_client(app)
    await pi_register(owner, "Delta Studio")
    member, _, _ = await _member_client(app, owner, "member")
    monkeypatch.setattr(routes, "ai_enabled", lambda request: True)
    monkeypatch.setattr(routes, "build_llm_manager", lambda *a, **k: FakeManager())
    answer = (await member.post(CHAT, json={"message": "How are we doing?"})).json()
    tools = seen[0]
    assert "billing" not in tools and "report" not in tools and "overview" in tools
    outputs = seen[2]  # [tools turn 1, tools turn 2, tool outputs]
    assert "isn't available for your role" in outputs[0] and "isn't available" in outputs[1]
    assert answer["mode"] == "ai" and [c["title"] for c in answer["cards"]] == ["This week"]
    context = (await member.get("/api/v1/pi-app/assistant/context")).json()
    assert context["can"]["billing"] is False and context["can"]["all_conversations"] is False
    await owner.aclose()
    await member.aclose()


async def test_operator_edits_guides_every_business_sees(app, api, business_db):
    identity = await register(api)
    base = "/api/v1/operator/pi/help"
    assert (await api.get(base)).status_code == 403
    business_db.add(PiOperatorMember(user_id=UUID(identity["user"]["id"]), role="owner"))
    await business_db.flush()
    listing = (await api.get(base)).json()
    assert "/settings/whatsapp" in listing["pages"] and len(listing["items"]) >= 10
    edited = await api.put(
        f"{base}/connect-whatsapp",
        json={
            "title": "Connect your WhatsApp number",
            "body": "Open Settings → WhatsApp and choose Connect. Our team checks it within a day.",
            "tags": ["whatsapp", "connect"],
            "page": "/settings/whatsapp",
        },
    )
    assert edited.status_code == 200 and edited.json()["builtin"] is True
    custom = await api.post(
        base,
        json={
            "title": "Ramadan opening hours",
            "body": "Update your hours in My pi → Behaviour so pi tells customers the new times.",
            "tags": ["ramadan", "hours"],
            "page": "/my-pi/behaviour",
        },
    )
    assert custom.status_code == 201 and custom.json()["id"] == "ramadan-opening-hours"
    bad = await api.post(
        base, json={"title": "Bad link", "body": "Points outside the app.", "page": "https://x.y"}
    )
    assert bad.status_code in {409, 422}
    assert (await api.post(f"{base}/campaigns/hide")).status_code == 200

    business = pi_client(app)
    await pi_register(business, "Gulshan Bakery")
    guides = (await business.get("/api/v1/pi-app/assistant/context")).json()["guides"]
    ids = {g["id"] for g in guides}
    assert "ramadan-opening-hours" in ids and "campaigns" not in ids
    how = (await business.post(CHAT, json={"message": "WhatsApp kaise connect karun"})).json()
    assert how["message"].startswith("Open Settings → WhatsApp and choose Connect")

    assert (await api.delete(f"{base}/connect-whatsapp")).status_code == 200
    reset = (await business.get("/api/v1/pi-app/assistant/guides/connect-whatsapp")).json()
    assert reset["body"].startswith("pi answers your customers")
    assert (await api.delete(f"{base}/ramadan-opening-hours")).status_code == 200
    gone = await business.get("/api/v1/pi-app/assistant/guides/ramadan-opening-hours")
    assert gone.status_code == 404
    await business.aclose()
