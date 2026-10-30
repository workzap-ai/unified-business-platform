"""The Solution Box document on the database and through the chat (platform spec Book 5, 5.2, 5.6,
5.7): the yes drafts the eight-section box and a quote by phase, the reviewer prices each phase, the
offer is the Solution Box wording, "that's all" is remembered (B1), and a problem after sending
starts Box v2 with the "Naya:" list. Real database; the AI and WhatsApp are mocked."""

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from test_pi_box_lifecycle_flow import ON, READY, chat
from test_pi_brain_documents import DOCS, bank, chat_model, drafted
from test_pi_brain_problems import say, workspace

from app.ai.manager import LLMManager
from app.modules.pi import box, box_lifecycle, solutions
from app.modules.pi.brain_docs import BoxComponent, BoxDraft, Line, WontDo
from app.modules.pi.brain_docs_models import PiBrainDocument
from app.modules.pi.configuration import settings_row
from app.shared.scope import WorkspaceScope

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def the_offer_is_open(monkeypatch):
    """The journeys start at the offer; canOffer itself is covered by the unit tests."""
    monkeypatch.setattr(box, "can_offer", lambda facts: (True, "R2", "held open for this journey"))


@pytest.fixture(autouse=True)
def roomy_limits(monkeypatch):
    from datetime import timedelta

    from app.modules.pi import guard

    for name in ("CONVERSATION_BURST", "AI_REPLY_LOOP"):
        current = getattr(guard, name)
        monkeypatch.setattr(guard, name, guard.Limit(current.code, 500, timedelta(minutes=1)))


def box_for(payload, **changes):
    """What the box drafter returns: a catalogue key per problem, two ideas each."""
    refs = [p["ref"] for p in payload["problems"]]
    keys = ["stock_alerts", "order_capture", "dashboards_reports"]
    base = dict(
        components=[
            BoxComponent(key=keys[i % 3], phase=1 + i, problems=[ref]) for i, ref in enumerate(refs)
        ],
        phases=[Line(text="Fix the first thing"), Line(text="Then the second")],
        hypotheses=[Line(text="Late deliveries may be part of why this happens.", refs=refs[:1])],
        ideas=[
            Line(text=text, refs=[ref])
            for ref in refs
            for text in (
                "Walk the shelves every Monday so you see gaps early.",
                "Ask each person to message you the day something is going wrong.",
            )
        ],
        assumptions=[Line(text="We assume each shop has a phone that takes messages.")],
        covers=["Your shops and the people who run them"],
        wont_do=[WontDo(text="It would not change how you order from your suppliers.")],
        needs=["One contact person in each shop"],
    )
    return BoxDraft(**{**base, **changes})


def install_models(monkeypatch, draft=box_for):
    seen = {"chat": 0, "drafts": [], "prompts": []}

    async def complete(self, scope, output, **kwargs):
        messages = kwargs["messages"]
        if output is BoxDraft:
            payload = json.loads(messages[1].text())
            seen["drafts"].append(payload)
            value = draft(payload)
        else:
            text = messages[-1].text()
            seen["prompts"].append(text)
            if text.startswith("{"):
                seen["chat"] += 1
                seen["last"] = chat_model(json.loads(text), seen["chat"])
            value = seen["last"]
        return SimpleNamespace(value=value, response=SimpleNamespace(attempts=[]))

    monkeypatch.setattr(LLMManager, "complete_structured", complete)
    return seen


async def accepted_box_offer(api, db, monkeypatch, **models):
    seen = install_models(monkeypatch, **models)
    pi = await workspace(api, db)
    await say(pi, "Best-sellers run out and cashiers are late on weekends", "bx-1")
    conversation = await pi.conversation()
    scope = WorkspaceScope.system(
        conversation.tenant_id, conversation.environment_id, frozenset(), "test"
    )
    settings = await settings_row(db, scope)
    settings.response_rules = {**(settings.response_rules or {}), **ON}
    await db.flush()
    await say(pi, "That's all", "bx-2")
    await say(pi, "looks right", "bx-3")
    await say(pi, "yes", "bx-4")
    await say(pi, "all of them", "bx-5")
    conversation = await pi.conversation()
    await db.refresh(conversation)
    return pi, seen, conversation


async def test_the_offer_is_the_solution_box_line_and_no_other_problems_is_remembered(
    api, business_db, monkeypatch
):
    pi, seen, conversation = await accepted_box_offer(api, business_db, monkeypatch)
    assert conversation.service_brief.get("no_other_problems") is True  # B1, kept once said
    offers = [m for m in pi.sent if "Solution Box" in str(m)]
    assert offers, [str(m)[:200] for m in pi.sent]
    assert all("solution document" not in str(m).lower() for m in offers)
    assert any(m.get("type") == "interactive" for m in offers)  # with the three buttons
    await pi.close()


async def test_yes_drafts_the_eight_section_box_and_a_quote_by_phase(api, business_db, monkeypatch):
    pi, seen, conversation = await accepted_box_offer(api, business_db, monkeypatch)
    assert conversation.flow_state == "S6_PREPARING"
    docs = await drafted(pi, business_db, conversation)
    solution, quote = docs["solution"], docs["quote"]
    content = solution.content
    assert content["box"] is True and len(seen["drafts"]) == 1
    assert "catalogue_keys" in seen["drafts"][0]
    # 4: catalogue wording only, in phases
    assert [c["text"] for c in content["components"]] == [
        solutions.build_phrase("stock_alerts"),
        solutions.build_phrase("order_capture"),
    ]
    assert [p["phase"] for p in content["phases"]] == [1, 2]
    # 2, 3, 5, 7
    assert content["clusters"] and all(len(e["ideas"]) == 2 for e in content["ideas"])
    assert len(content["order"]) == 2 and content["assumptions"]
    assert solution.review_notes == ""
    # 8: the quote is by phase and nobody has priced it
    assert [p["price"] for p in quote.content["phases"]] == [None, None]
    assert quote.total is None
    # box lifecycle: drafting went to in_review
    box_row = await box_lifecycle.latest_box(
        business_db, _scope(conversation), conversation.customer_id
    )
    assert box_row.state == "in_review"
    await pi.close()


def _scope(conversation):
    return WorkspaceScope.system(
        conversation.tenant_id, conversation.environment_id, frozenset(), "test"
    )


async def test_the_reviewer_prices_every_phase_and_the_prices_must_add_up(
    api, business_db, monkeypatch
):
    pi, _, conversation = await accepted_box_offer(api, business_db, monkeypatch)
    docs = await drafted(pi, business_db, conversation)
    await bank(api)
    base = {
        "time": {"estimate": "About six weeks from kickoff"},
        "valid_until": "2030-12-31",
        "cost": {"total": "3500", "currency": "PKR"},
    }
    patch = await api.patch(f"{DOCS}/{docs['quote'].id}", json=base)
    assert patch.status_code == 200, patch.text
    blocked = await api.post(f"{DOCS}/{docs['quote'].id}/approve")
    assert blocked.status_code == 409 and "enter the price of" in blocked.text
    mismatch = await api.patch(
        f"{DOCS}/{docs['quote'].id}",
        json={"phases": [{"phase": 1, "price": "1000"}, {"phase": 2, "price": "2000"}]},
    )
    assert mismatch.status_code == 200, mismatch.text
    still = await api.post(f"{DOCS}/{docs['quote'].id}/approve")
    assert still.status_code == 409 and "add up to the total" in still.text
    await api.patch(
        f"{DOCS}/{docs['quote'].id}",
        json={"phases": [{"phase": 1, "price": "1000"}, {"phase": 2, "price": "2500"}]},
    )
    for kind in ("solution", "quote"):
        done = await api.post(f"{DOCS}/{docs[kind].id}/approve")
        assert done.status_code == 200, done.text
    rows = (await business_db.scalars(select(PiBrainDocument))).all()
    assert {r.status for r in rows} == {"approved"}
    await pi.close()


async def test_a_box_that_breaks_the_catalogue_is_flagged_and_cannot_be_approved(
    api, business_db, monkeypatch
):
    def invented(payload):
        return box_for(
            payload,
            components=[
                BoxComponent(key="custom_crm", phase=1, problems=[payload["problems"][0]["ref"]])
            ],
        )

    pi, seen, conversation = await accepted_box_offer(api, business_db, monkeypatch, draft=invented)
    docs = await drafted(pi, business_db, conversation)
    assert len(seen["drafts"]) == 2  # one rewrite, then flagged
    assert "approved catalogue" in docs["solution"].review_notes
    blocked = await api.post(f"{DOCS}/{docs['solution'].id}/approve")
    assert blocked.status_code == 409
    await pi.close()


async def test_a_problem_after_sending_starts_box_v2_with_the_naya_list(api, business_db):
    conversation, scope = await chat(api, business_db)
    customer = conversation.customer_id
    await box_lifecycle.offer(business_db, scope, customer, conversation.id, READY)
    row = await box_lifecycle.latest_box(business_db, scope, customer)
    await box_lifecycle.move(business_db, scope, row, "drafting", "pi", explicit_yes=True)
    await box_lifecycle.move(business_db, scope, row, "in_review", "pi")
    await box_lifecycle.move(
        business_db, scope, row, "sent", "staff", actor_ref="Sara", approved_document=True
    )
    # nothing happens while the box is off
    assert (
        await box_lifecycle.on_new_problems(
            business_db, scope, conversation, ["Rent is due"], box_on=False
        )
        is None
    )
    assert row.state == "sent"
    started = await box_lifecycle.on_new_problems(
        business_db, scope, conversation, ["Rent is due"], box_on=True
    )
    assert started == 2 and row.state == "revised"
    assert conversation.service_brief["box_naya"] == ["Rent is due"]
    newest = await box_lifecycle.latest_box(business_db, scope, customer)
    assert (newest.version, newest.state, newest.parent_box_id) == (2, "collecting", row.id)
    # a further problem while v2 is collecting joins the list; no third version
    assert (
        await box_lifecycle.on_new_problems(
            business_db, scope, conversation, ["Rent is due", "Staff leave"], box_on=True
        )
        is None
    )
    assert conversation.service_brief["box_naya"] == ["Rent is due", "Staff leave"]
    assert (await box_lifecycle.latest_box(business_db, scope, customer)).version == 2
