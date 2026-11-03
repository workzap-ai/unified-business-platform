"""Staff controls for pi's learning (spec 8.10, 8.11.1) and the erase cascade (eval L11)."""

import pytest
from sqlalchemy import func, select
from test_pi_brain_problems import adaptive, say, workspace
from test_pi_experiences import spread
from test_pi_learning_loop import SECOND, deliver_everything, good_chat, learning_on, model
from test_pi_service_conversations import turn

from app.modules.pi import learning_arms
from app.modules.pi.experience_scorer import score_new
from app.modules.pi.learning_models import PiLearningChange, PiLearningExample, PiQuestionArm
from app.modules.pi.problem_models import PiProblem

pytestmark = pytest.mark.integration
L = "/api/v1/pi/brain-learning"


async def count(db, model_):
    return await db.scalar(select(func.count()).select_from(model_))


async def live_examples(db):
    """Examples made from real chats (seeds from packs and golden conversations are not)."""
    return await db.scalar(
        select(func.count())
        .select_from(PiLearningExample)
        .where(PiLearningExample.source == "live")
    )


async def test_the_question_leaderboard_lists_the_seeded_wordings(api, business_db, monkeypatch):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    listed = (await api.get(f"{L}/arms")).json()["items"]
    expected = sum(len(t) for by in learning_arms.SEEDS.values() for t in by.values())
    assert len(listed) == expected
    assert {a["slot"] for a in listed} == set(learning_arms.SEEDS)
    only = (await api.get(f"{L}/arms", params={"slot": "scope"})).json()["items"]
    assert only and all(a["slot"] == "scope" for a in only)
    await pi.close()


@pytest.mark.parametrize(
    "body",
    [
        {
            "slot": "scope",
            "text": "Is it every shop? And how often does it happen?",
        },  # two questions
        {"slot": "scope", "text": "Tell me which shops it hits"},  # not a question
        {"slot": "scope", "text": "Workzap can build an app for that, want one?"},  # a pitch
        {"slot": "nonsense", "text": "Which shop loses the most?"},  # unknown slot
        {"slot": "scope", "text": "What is your card number? Is it every shop?"},  # asks for a card
    ],
)
async def test_a_bad_wording_is_refused_with_the_reasons(api, business_db, monkeypatch, body):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    await api.get(f"{L}/arms")  # creates the starting wordings
    before = await count(business_db, PiQuestionArm)
    refused = await api.post(f"{L}/arms", json=body)
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"]["code"] == "WORDING_REFUSED"
    business_db.expire_all()
    assert await count(business_db, PiQuestionArm) == before  # nothing new was added
    await pi.close()


async def test_a_good_wording_starts_on_a_tenth_of_the_traffic_and_can_be_retired(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    made = await api.post(
        f"{L}/arms", json={"slot": "scope", "text": "Which of your shops loses the most?"}
    )
    assert made.status_code == 201, made.text
    arm = made.json()
    assert arm["status"] == "testing" and arm["traffic_cap"] == 0.1 and arm["created_by"] == "staff"
    changes = (await api.get(f"{L}/changes")).json()["items"]
    assert any(c["kind"] == "question_arm_added" for c in changes)
    retired = await api.post(f"{L}/arms/{arm['id']}/retire")
    assert retired.status_code == 200 and retired.json()["status"] == "retired"
    await pi.close()


async def test_staff_can_mark_a_real_reply_as_great_and_retire_an_example(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    await good_chat(pi, business_db)
    first = await pi.reply_to("ll-1")
    made = await api.post(f"{L}/examples/from-message/{first.id}")
    assert made.status_code == 201, made.text
    example = made.json()
    assert example["status"] == "candidate" and "Is it every shop" in example["reply"]
    assert not example["reply"].startswith("Hi, I'm pi")  # the fixed introduction is not learned
    again = await api.post(f"{L}/examples/from-message/{first.id}")
    assert again.status_code == 409 and again.json()["error"]["code"] == "ALREADY_AN_EXAMPLE"
    listed = (await api.get(f"{L}/examples", params={"status": "candidate"})).json()["items"]
    assert [e["id"] for e in listed] == [example["id"]]
    retired = await api.post(f"{L}/examples/{example['id']}/retire", json={"reason": "off tone"})
    assert retired.status_code == 200 and retired.json()["status"] == "retired"
    kinds = [c.kind for c in await business_db.scalars(select(PiLearningChange))]
    assert "example_added_by_staff" in kinds and "example_retired" in kinds
    await pi.close()


async def test_a_reply_with_a_name_in_the_exchange_cannot_be_marked_great(
    api, business_db, monkeypatch
):
    def named(context, n):
        return turn(reply="Thanks. I've noted it. Is it every shop, or only some?", language="en")

    adaptive(monkeypatch, named)
    pi = await workspace(api, business_db)
    await say(pi, "stock runs out at the Johar Town branch", "lr-1")
    await spread(business_db, pi, ["lr-1"])
    reply = await pi.reply_to("lr-1")
    refused = await api.post(f"{L}/examples/from-message/{reply.id}")
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"]["code"] == "EXAMPLE_REFUSED"
    assert "personal details" in refused.json()["error"]["message"]
    await pi.close()


async def test_run_now_does_nothing_while_frozen_and_works_once_switched_on(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    frozen = (await api.post(f"{L}/run")).json()
    assert frozen["frozen"] is True and frozen["digest"] == {"frozen": True}
    await learning_on(api)
    await good_chat(pi, business_db)
    await score_new(business_db)
    await business_db.commit()
    live = (await api.post(f"{L}/run")).json()
    assert live["frozen"] is False and live["digest"]["examples"]["added"] == 1
    runs = (await api.get(f"{L}/runs")).json()["items"]
    assert [r["frozen"] for r in runs] == [False, True]
    await pi.close()


async def test_erasing_a_customer_removes_the_examples_made_from_their_chats(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    await learning_on(api)
    await good_chat(pi, business_db)
    await score_new(business_db)
    await business_db.commit()
    assert (await api.post(f"{L}/run")).json()["digest"]["examples"]["added"] == 1
    first_chat = await pi.conversation()  # the customer the example came from
    await pi.process("stock runs out at my branch", "lr-9", sender=SECOND)
    await deliver_everything(pi, business_db)
    assert await live_examples(business_db) == 1
    assert await count(business_db, PiProblem) == 2
    erased = await api.post(
        f"/api/v1/pi/brain-erasure/{first_chat.customer_id}", json={"confirm": True}
    )
    assert erased.status_code == 200, erased.text
    assert erased.json()["removed"]["learning_examples"] == 1
    business_db.expire_all()
    assert await live_examples(business_db) == 0
    assert await count(business_db, PiProblem) == 1  # the other customer's note is untouched
    await pi.close()


async def test_staff_can_correct_a_problem_and_it_is_kept_as_a_staff_revision(
    api, business_db, monkeypatch
):
    from app.modules.pi.problem_models import PiProblemRevision

    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    await good_chat(pi, business_db)
    problem = (await business_db.scalars(select(PiProblem))).first()
    assert problem is not None
    pid = problem.id
    bad = await api.post(f"{L}/problems/{pid}/correct", json={"category": "nonsense"})
    assert bad.status_code == 422, bad.text
    done = await api.post(
        f"{L}/problems/{pid}/correct",
        json={"category": "cash_collections", "title": "Customers pay late"},
    )
    assert done.status_code == 200, done.text
    assert done.json()["fields"] == ["category", "title"] or "category" in done.json()["fields"]
    business_db.expire_all()
    revision = await business_db.scalar(
        select(PiProblemRevision).where(
            PiProblemRevision.problem_id == pid, PiProblemRevision.by == "staff"
        )
    )
    assert revision is not None and revision.reason == "staff_correction"
    again = await api.post(f"{L}/problems/{pid}/correct", json={"category": "cash_collections"})
    assert again.json()["changed"] is False
    await pi.close()


async def test_staff_see_the_noted_problems_with_the_categories_to_correct_them_to(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    await good_chat(pi, business_db)
    listed = (await api.get(f"{L}/problems")).json()
    assert listed["items"] and listed["items"][0]["title"]
    keys = {c["key"] for c in listed["categories"]}
    assert {"cash_collections", "stock_inventory", "people_staff"} <= keys
    await pi.close()
