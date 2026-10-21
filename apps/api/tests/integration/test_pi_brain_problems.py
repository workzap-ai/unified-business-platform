"""Brain mode notes, sorts and summarises problems. Real database/webhook/worker; the AI and
WhatsApp are mocked."""

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from test_pi_brain_flow import brain_on
from test_pi_industry_context import contexts, scripted
from test_pi_pipeline import pi_workspace
from test_pi_service_conversations import turn

from app.ai.manager import LLMManager
from app.modules.pi.problem_models import (
    PiProblem,
    PiProblemGroup,
    PiProblemLink,
    PiProblemRevision,
)
from app.modules.pi.problems import ProblemNote, ProblemOp

pytestmark = pytest.mark.integration

OPENING = "Hi, I'm pi, an AI from Workzap."


def create(title, words, category="stock_inventory", **extra):
    return ProblemOp(
        op="create",
        note=ProblemNote(title=title, user_words=[words], category=category, **extra),
    )


def adaptive(monkeypatch, make):
    """The model's answer is made from the context pi sent; a rewrite prompt repeats the last."""
    prompts: list[str] = []
    last: dict = {}

    async def complete(self, scope, output, **kwargs):
        text = kwargs["messages"][-1].text()
        prompts.append(text)
        if text.startswith("{"):
            last["value"] = make(json.loads(text), sum(p.startswith("{") for p in prompts))
        return SimpleNamespace(value=last["value"], response=SimpleNamespace(attempts=[]))

    monkeypatch.setattr(LLMManager, "complete_structured", complete)
    return prompts


async def problems_of(db, pi):
    conversation = await pi.conversation()
    await db.refresh(conversation)
    result = await db.scalars(
        select(PiProblem)
        .where(PiProblem.customer_id == conversation.customer_id)
        .order_by(PiProblem.number)
    )
    rows = list(result)
    for row in rows:
        await db.refresh(row)
    return conversation, rows


async def workspace(api, db):
    pi = await pi_workspace(api, db, business_type="service_business")
    await brain_on(api)
    return pi


async def say(pi, text, key):
    await pi.process(text, key)
    await pi.deliver_all()


async def test_a_noted_problem_is_saved_grouped_scored_and_moves_the_chat_to_noted(
    api, business_db, monkeypatch
):
    scripted(
        monkeypatch,
        turn(
            reply=f"{OPENING} Thanks. I've noted it: best-sellers running out. Anything else?",
            language="en",
            problem_ops=[
                create(
                    "Best-sellers run out in two shops",
                    "We keep running out of our best-selling items.",
                    subtype="stockout",
                    where=["Shop B", "Shop D"],
                    of_total="2 of 4 shops",
                    frequency="weekly",
                    impact_types=["lost_sales"],
                    severity_stated="high",
                    confidence=0.9,
                )
            ],
        ),
    )
    pi = await workspace(api, business_db)
    await say(pi, "Our best-selling items keep running out in two of the four shops", "pb-1")
    conversation, [problem] = await problems_of(business_db, pi)
    assert (problem.number, problem.title, problem.category, problem.subtype) == (
        1,
        "Best-sellers run out in two shops",
        "stock_inventory",
        "stockout",
    )
    assert problem.status == "draft" and problem.revision == 1
    assert problem.user_words == ["We keep running out of our best-selling items."]
    assert problem.scope == {"where": ["Shop B", "Shop D"], "of_total": "2 of 4 shops"}
    assert problem.frequency["normalised"] == "weekly"
    assert float(problem.severity_score) == 19.5  # 3 x 2.5 x 2 x 1.3
    assert problem.severity_inferred == "high"
    group = await business_db.get(PiProblemGroup, problem.group_id)
    assert group.category == "stock_inventory" and group.name == "Stock"
    [revision] = (await business_db.scalars(select(PiProblemRevision))).all()
    assert (revision.revision, revision.reason, revision.by) == (1, "created", "pi")
    assert conversation.flow_state == "S3_NOTED"
    await pi.close()


async def test_a_noted_line_the_person_does_not_object_to_becomes_confirmed(
    api, business_db, monkeypatch
):
    scripted(
        monkeypatch,
        turn(
            reply=f"{OPENING} Noted: the cash does not match. Anything else?",
            language="en",
            problem_ops=[
                create(
                    "Daily cash doesn't match the till", "Cash never matches.", "cash_collections"
                )
            ],
        ),
        turn(reply="Noted. Anything else getting in the way?", language="en"),
    )
    pi = await workspace(api, business_db)
    await say(pi, "Cash never matches at the end of the day", "pb-2a")
    assert (await problems_of(business_db, pi))[1][0].status == "draft"
    await say(pi, "The cashiers are also late", "pb-2b")
    assert (await problems_of(business_db, pi))[1][0].status == "confirmed"
    await pi.close()


async def test_a_correction_is_a_revision_and_the_latest_wording_wins(
    api, business_db, monkeypatch
):
    def make(context, n):
        if n == 1:
            ops = [create("Stock runs out in two shops", "Stock runs out.", of_total="2 of 4")]
            reply = f"{OPENING} Noted: stock runs out in two shops. Anything else?"
        else:
            ref = context["noted_problems"][0]["ref"]
            note = ProblemNote(title="Stock runs out in three shops", of_total="3 of 4")
            ops = [ProblemOp(op="update", ref=ref, reason="correction", note=note)]
            reply = "You're right. Noted: stock runs out in three shops. Anything else?"
        return turn(reply=reply, language="en", problem_ops=ops)

    prompts = adaptive(monkeypatch, make)
    pi = await workspace(api, business_db)
    await say(pi, "Stock runs out in two shops", "pb-3a")
    await say(pi, "No, it is three shops", "pb-3b")
    seen = contexts(prompts)[1]["noted_problems"]
    assert seen[0]["title"] == "Stock runs out in two shops"
    _, [problem] = await problems_of(business_db, pi)
    assert problem.title == "Stock runs out in three shops" and problem.status == "corrected"
    assert problem.scope["of_total"] == "3 of 4" and problem.revision == 2
    revisions = (
        await business_db.scalars(
            select(PiProblemRevision)
            .where(PiProblemRevision.problem_id == problem.id)
            .order_by(PiProblemRevision.revision)
        )
    ).all()
    assert [r.reason for r in revisions] == ["created", "correction"]
    assert revisions[1].by == "person"
    assert revisions[1].diff["title"] == [
        "Stock runs out in two shops",
        "Stock runs out in three shops",
    ]
    await pi.close()


async def test_merge_split_link_withdraw_and_rename_a_group(api, business_db, monkeypatch):
    def make(context, n):
        refs = {p["title"]: p["ref"] for p in context["noted_problems"]}
        if n == 1:
            ops = [
                create("Stock runs out in Shop B", "Shop B runs out."),
                create("Shop B keeps running out of stock", "It happens again in B."),
                create("Cashiers late on weekends", "Cashiers come late.", "people_staff"),
                create(
                    "Cash and staff are both a mess", "Cash is wrong and people are late.", "other"
                ),
            ]
            reply = f"{OPENING} Noted all four. Anything else?"
        elif n == 2:
            a, b = refs["Stock runs out in Shop B"], refs["Shop B keeps running out of stock"]
            ops = [
                ProblemOp(op="merge", ref=a, refs=[b]),
                ProblemOp(
                    op="link", ref=refs["Cashiers late on weekends"], to=a, link_type="same_area"
                ),
                ProblemOp(
                    op="split",
                    ref=refs["Cash and staff are both a mess"],
                    notes=[
                        ProblemNote(
                            title="Daily cash does not match",
                            user_words=["Cash is wrong"],
                            category="cash_collections",
                        ),
                        ProblemNote(
                            title="Staff are often late",
                            user_words=["people are late"],
                            category="people_staff",
                        ),
                    ],
                ),
                ProblemOp(op="rename_group", ref="stock_inventory", name="Warehouse"),
            ]
            reply = "Done. I've merged the two stock ones and split the last one. Anything else?"
        else:
            ops = [ProblemOp(op="withdraw", ref=refs["Cashiers late on weekends"])]
            reply = "Fine, I've taken that one off. Anything else?"
        return turn(reply=reply, language="en", problem_ops=ops)

    adaptive(monkeypatch, make)
    pi = await workspace(api, business_db)
    await say(
        pi, "Shop B runs out, again in B, cashiers late, and cash plus staff are a mess", "pb-4a"
    )
    await say(pi, "The first two are the same thing, and the last one is two problems", "pb-4b")
    await say(pi, "Forget the cashiers", "pb-4c")
    _, rows = await problems_of(business_db, pi)
    by_title = {r.title: r for r in rows}
    a = by_title["Stock runs out in Shop B"]
    b = by_title["Shop B keeps running out of stock"]
    assert b.status == "merged" and b.merged_into == a.id
    assert set(a.user_words) == {"Shop B runs out.", "It happens again in B."}
    assert by_title["Cash and staff are both a mess"].status == "split"
    assert by_title["Daily cash does not match"].category == "cash_collections"
    assert by_title["Staff are often late"].status == "confirmed"  # not objected to
    assert by_title["Cashiers late on weekends"].status == "withdrawn"
    [link] = (await business_db.scalars(select(PiProblemLink))).all()
    assert (link.type, link.status, link.created_by) == ("same_area", "suggested", "pi")
    assert link.to_id == a.id
    group = (
        await business_db.scalars(
            select(PiProblemGroup).where(PiProblemGroup.category == "stock_inventory")
        )
    ).one()
    assert (group.name, group.created_by) == ("Warehouse", "person")
    assert {r.number for r in rows} == set(range(1, 7))
    await pi.close()


async def test_that_is_all_shows_the_sorted_summary_and_moves_to_sorted(
    api, business_db, monkeypatch
):
    def make(context, n):
        if n == 1:
            ops = [
                create("Best-sellers run out in two shops", "Best-sellers run out."),
                create("Cashiers late on weekends", "Cashiers come late.", "people_staff"),
            ]
            return turn(
                reply=f"{OPENING} Noted both. Anything else getting in the way?",
                language="en",
                problem_ops=ops,
            )
        return turn(reply="Thanks, noted.", language="en")

    adaptive(monkeypatch, make)
    pi = await workspace(api, business_db)
    await say(pi, "Best-sellers run out and cashiers are late on weekends", "pb-5a")
    await say(pi, "That's all", "pb-5b")
    body = (await pi.reply_to("pb-5b")).body
    assert body.startswith("Here's what I've noted and sorted so far. None of it is solved yet.")
    assert "*Stock* (1)" in body and "*Staff* (1)" in body
    assert body.endswith("Is anything wrong or missing?")
    conversation, _ = await problems_of(business_db, pi)
    assert conversation.flow_state == "S4_SORTED_SUMMARY"
    assert conversation.service_brief["summary_count"] == 2
    await pi.close()


async def test_personal_details_never_reach_a_problem_record(api, business_db, monkeypatch):
    scripted(
        monkeypatch,
        turn(
            reply=f"{OPENING} Noted. Please don't send card numbers here. Anything else?",
            language="en",
            problem_ops=[
                create(
                    "Supplier payments go wrong",
                    "I paid with card 4111 1111 1111 1111 and called +92 300 1234567",
                    "cash_collections",
                )
            ],
        ),
    )
    pi = await workspace(api, business_db)
    await say(pi, "Supplier payments go wrong", "pb-6")
    _, [problem] = await problems_of(business_db, pi)
    stored = " ".join(problem.user_words)
    assert "4111" not in stored and "1234567" not in stored
    assert "[card number removed]" in stored and "[phone removed]" in stored
    assert problem.pii_redacted is True
    await pi.close()


async def test_a_title_that_blames_someone_goes_back_to_the_model_once(
    api, business_db, monkeypatch
):
    prompts = scripted(
        monkeypatch,
        turn(
            reply=f"{OPENING} Noted. Anything else?",
            language="en",
            problem_ops=[create("Lazy manager never counts stock", "He never counts.")],
        ),
        turn(
            reply=f"{OPENING} Noted. Anything else?",
            language="en",
            problem_ops=[create("Stock is never counted", "He never counts.")],
        ),
    )
    pi = await workspace(api, business_db)
    await say(pi, "My manager never counts stock", "pb-7")
    assert "the problem notes are wrong" in prompts[1] and "blames someone" in prompts[1]
    _, rows = await problems_of(business_db, pi)
    assert [r.title for r in rows] == ["Stock is never counted"]
    await pi.close()


async def test_standard_mode_ignores_problem_ops(api, business_db, monkeypatch):
    scripted(
        monkeypatch,
        turn(
            reply="Noted. Which shop is it?",
            language="en",
            problem_ops=[create("Stock runs out", "It runs out.")],
        ),
    )
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await say(pi, "Stock runs out", "pb-8")
    conversation = await pi.conversation()
    assert (await business_db.scalars(select(PiProblem))).all() == []
    assert conversation.flow_state is None
    await pi.close()


async def test_the_trade_question_comes_once_after_two_problems(api, business_db, monkeypatch):
    def make(context, n):
        ops = []
        reply = "Noted. Anything else getting in the way?"
        if n == 1:
            ops = [
                create(
                    "The monthly numbers never add up",
                    "Numbers never add up.",
                    "reporting_visibility",
                )
            ]
            reply = f"{OPENING} Noted. Anything else getting in the way?"
        elif n == 2:
            ops = [create("Our people are often late", "People are late.", "people_staff")]
        elif context.get("shape_question_due"):
            reply = "What kind of business is it?"
        return turn(reply=reply, language="en", problem_ops=ops)

    prompts = adaptive(monkeypatch, make)
    pi = await workspace(api, business_db)
    await say(pi, "The monthly numbers never add up", "pb-9a")
    await say(pi, "Our people are often late", "pb-9b")
    await say(pi, "Not sure what else", "pb-9c")
    await say(pi, "It is a small company", "pb-9d")
    seen = contexts(prompts)
    assert "shape_question_due" not in seen[0] and "shape_question_due" not in seen[1]
    assert seen[2]["shape_question_due"] is True
    assert "shape_question_due" not in seen[3]
    assert (await pi.reply_to("pb-9c")).body == "What kind of business is it?"
    conversation, _ = await problems_of(business_db, pi)
    assert conversation.service_brief["industry_asked"] is True
    await pi.close()
