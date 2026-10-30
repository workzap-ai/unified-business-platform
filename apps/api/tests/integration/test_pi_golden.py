# ruff: noqa: E501  (Arabic and Urdu lines read better unbroken)
"""Golden conversations from spec Part 10.1 that no other test covers (G4, G9, G14).

The simulated person sends the "Person" lines; the model is scripted with the spec's own replies,
so these tests check that the code lets the spec's wording through and keeps the state right."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from test_pi_brain_problems import adaptive, create, problems_of, say, workspace
from test_pi_service_conversations import turn

from app.modules.pi.models import PiMessage

pytestmark = pytest.mark.integration

OPENING = "Hi, I'm pi, an AI from Workzap."


def listening(context, n):
    said = context["latest_customer_message"]
    if "app" in said:  # G4
        return turn(
            reply=(
                "Once I've noted what's going wrong, Workzap can prepare a solution document "
                "for it, if you want one. For now, what would the app need to fix first?"
            ),
            language="en",
        )
    if "kharcha" in said:  # G9
        return turn(
            reply=(
                "Kharcha is par depend karta hai ke kya banaya jaye. Woh quote par likha hota "
                "hai, aap ke faisle se pehle, aur quote muft hai, koi charge nahi."
            ),
            language="roman_ur",
        )
    if "Best-sellers" in said:
        return turn(
            reply=f"{OPENING} Noted both. Anything else getting in the way?",
            language="en",
            problem_ops=[
                create("Best-sellers run out in two shops", "Best-sellers run out."),
                create("Cashiers late on weekends", "Cashiers come late.", "people_staff"),
            ],
        )
    return turn(reply="Noted. Anything else getting in the way?", language="en")


async def test_g4_a_request_for_an_app_while_describing_returns_to_listening(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, listening)
    pi = await workspace(api, business_db)
    await say(pi, "Best-sellers run out and cashiers are late on weekends", "g4-1")
    await say(pi, "can you make an app for this?", "g4-2")
    reply = (await pi.reply_to("g4-2")).body
    assert reply.startswith("Once I've noted what's going wrong")
    assert reply.count("?") == 1 and reply.endswith("?")
    conversation = await pi.conversation()
    await business_db.refresh(conversation)
    assert conversation.flow_state in ("S1_LISTENING", "S2_CLARIFYING", "S3_NOTED")
    await pi.close()


async def test_g9_a_switch_to_roman_urdu_gets_the_cost_answer_without_a_price(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, listening)
    pi = await workspace(api, business_db)
    await say(pi, "Best-sellers run out and cashiers are late on weekends", "g9-1")
    await say(pi, "also the delivery is late", "g9-2")
    await say(pi, "that is a lot", "g9-3")
    await say(pi, "bhai ye batao kitna kharcha hoga?", "g9-4")
    reply = (await pi.reply_to("g9-4")).body
    answer = reply.split("\n\n")[0]
    assert answer.startswith("Kharcha is par depend karta hai")
    assert "muft hai" in answer and not any(c.isdigit() for c in answer)  # R-OFFER-05: no range
    assert "Cashiers late on weekends" in reply  # then the sorted summary (spec 3.7)
    await pi.close()


async def test_g14_returning_after_forty_days_says_who_it_is_and_remembers(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, listening)
    pi = await workspace(api, business_db)
    await say(pi, "Best-sellers run out and cashiers are late on weekends", "g14-1")
    long_ago = datetime.now(UTC) - timedelta(days=40)
    for message in (await business_db.scalars(select(PiMessage))).all():
        message.created_at = long_ago
    await business_db.flush()
    await say(pi, "hi again", "g14-2")
    reply = (await pi.reply_to("g14-2")).body
    assert reply.startswith("Hi, it's pi, the AI from Workzap. Welcome back.")
    assert "2 problems" in reply and reply.endswith("is something new going on?")
    assert reply.count("?") == 1
    await pi.close()


def noting(context, n):
    said = context["latest_customer_message"]
    if "best-selling" in said:  # G1
        first = n == 1
        return turn(
            reply=(
                f"{OPENING} That's a real problem. Is it happening in every shop, or only some?"
                if first
                else "Thanks. I've noted it: best-sellers running out, in two of four shops. "
                "Anything else getting in the way?"
            ),
            language="en",
            problem_ops=[]
            if first
            else [
                create(
                    "Best-sellers run out in two shops",
                    "We keep running out of our best-selling items.",
                    "stock_inventory",
                    subtype="stockout",
                    of_total="2 of 4 shops",
                )
            ],
        )
    if "Two of the four" in said:
        return turn(
            reply="Thanks. I've noted it: best-sellers running out, in two of four shops. "
            "Anything else getting in the way?",
            language="en",
            problem_ops=[
                create(
                    "Best-sellers run out in two shops",
                    "We keep running out of our best-selling items.",
                    "stock_inventory",
                    subtype="stockout",
                    of_total="2 of 4 shops",
                )
            ],
        )
    if "Johar Town" in said:  # G2
        return turn(
            reply=(
                "Thanks. I've noted three things:\n• Stock running out\n"
                "• Cashiers late on weekends\n• Cash not matching at one branch\n"
                "Which of these costs you the most?"
            ),
            language="en",
            problem_ops=[
                create("Stock runs out", "stock runs out"),
                create(
                    "Cashiers late on weekends", "my cashiers come late on weekends", "people_staff"
                ),
                create("Cash does not match", "the cash never matches", "cash_collections"),
            ],
        )
    if "udhaar" in said:  # G6
        return turn(
            reply=(
                "Wa alaikum assalam. Ye waqai masla hai. Udhaar ka hisaab abhi kaise rakhte "
                "hain, register mein?"
            ),
            language="roman_ur",
        )
    if "haan register" in said:
        return turn(
            reply="Shukriya. Note kar liya: udhaar ke paise wapas nahi aate, hisaab register mein. "
            "Aur kya cheez mushkil kar rahi hai?",
            language="roman_ur",
            problem_ops=[
                create(
                    "Credit customers do not pay back",
                    "udhaar wale paise wapas nahi dete",
                    "cash_collections",
                    subtype="credit_customers",
                    systems=["register"],
                    title_local="udhaar ke paise wapas nahi aate",
                )
            ],
        )
    return turn(reply="Noted. Anything else getting in the way?", language="en")


async def test_g1_the_website_example_notes_one_stock_problem_in_their_words(
    api, business_db, monkeypatch
):
    prompts = adaptive(monkeypatch, noting)
    pi = await workspace(api, business_db)
    await say(pi, "We keep running out of our best-selling items.", "g1-1")
    first = (await pi.reply_to("g1-1")).body
    assert first.startswith(OPENING) and first.count("?") == 1 and first.endswith("?")
    await say(pi, "Two of the four.", "g1-2")
    second = (await pi.reply_to("g1-2")).body
    # spec v1.4, 17.6: the problem is recorded, but pi no longer announces "noted"
    assert "noted" not in second.lower()
    assert second.count("?") == 1 and "solution" not in second.lower()
    _, rows = await problems_of(business_db, pi)
    [problem] = rows
    assert problem.category == "stock_inventory" and problem.subtype == "stockout"
    assert problem.scope.get("of_total") == "2 of 4 shops"
    assert prompts  # the model was asked
    await pi.close()


async def test_g2_three_problems_in_one_message_are_noted_separately_with_one_question(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, noting)
    pi = await workspace(api, business_db)
    await say(
        pi,
        "stock runs out, my cashiers come late on weekends and the cash never matches "
        "at the Johar Town branch",
        "g2-1",
    )
    reply = (await pi.reply_to("g2-1")).body
    assert reply.count("•") == 3 and reply.count("?") == 1 and reply.endswith("?")
    _, rows = await problems_of(business_db, pi)
    assert len(rows) == 3
    assert {r.category for r in rows} == {"stock_inventory", "people_staff", "cash_collections"}
    assert not any("Johar" in (r.title + str(r.user_words)) for r in rows)  # no names stored
    await pi.close()


async def test_g6_roman_urdu_small_shop_is_noted_in_roman_urdu_with_the_system_named(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, noting)
    pi = await workspace(api, business_db)
    await say(
        pi,
        "assalam o alaikum. meri kiryana ki dukan hai, udhaar wale paise wapas nahi dete",
        "g6-1",
    )
    await say(pi, "haan register", "g6-2")
    reply = (await pi.reply_to("g6-2")).body
    assert "note kar liya" not in reply.lower() and reply.count("?") == 1
    _, rows = await problems_of(business_db, pi)
    [problem] = rows
    assert problem.category == "cash_collections" and problem.subtype == "credit_customers"
    assert problem.systems_mentioned == ["register"]
    assert problem.title.isascii() and problem.title_local  # English title kept internally
    await pi.close()


def more(context, n):
    said = context["latest_customer_message"]
    if "everything is a mess" in said:  # G3
        return turn(
            reply=f"{OPENING} That's a lot to carry. Where do you notice it most: sales, stock, "
            "staff or cash?",
            language="en",
        )
    if said.startswith("staff."):
        return turn(
            reply="What's one thing they don't follow that causes the most trouble?",
            language="en",
        )
    if "opening checklist" in said:
        return turn(
            reply="Thanks. I've noted it: shops open late and not cleaned, opening checklist not "
            "followed. Is it every shop, or some?",
            language="en",
            problem_ops=[
                create(
                    "Opening checklist not followed",
                    "shops open late and dirty",
                    "people_staff",
                )
            ],
        )
    if "گودام" in said:  # G7: Urdu script
        return turn(reply="شکریہ۔ یہ کتنی بار ہوتا ہے، روزانہ یا کبھی کبھی؟", language="roman_ur")
    if "مطعم" in said:  # G8: Arabic
        return turn(
            reply="مرحباً، أنا pi، ذكاء اصطناعي من Workzap. هذه مشكلة حقيقية. من أي تطبيقات تأتي الطلبات؟",
            language="ar",
        )
    return turn(reply="Noted. Anything else getting in the way?", language="en")


async def test_g3_a_vague_opener_is_not_noted_until_there_is_a_concrete_symptom(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, more)
    pi = await workspace(api, business_db)
    await say(pi, "everything is a mess honestly", "g3-1")
    assert (await problems_of(business_db, pi))[1] == []  # nothing noted yet
    await say(pi, "staff. nobody follows anything", "g3-2")
    assert (await problems_of(business_db, pi))[1] == []
    await say(pi, "opening checklist. shops open late and dirty", "g3-3")
    reply = (await pi.reply_to("g3-3")).body
    assert "noted" not in reply.lower() and reply.count("?") == 1
    _, rows = await problems_of(business_db, pi)
    assert len(rows) == 1 and rows[0].category == "people_staff"
    for key in ("g3-1", "g3-2", "g3-3"):  # one question each, and it is the last sentence
        body = (await pi.reply_to(key)).body
        assert body.count("?") == 1 and body.rstrip().endswith("?")
    await pi.close()


async def test_g7_urdu_script_gets_an_urdu_script_reply_with_one_question(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, more)
    pi = await workspace(api, business_db)
    await say(pi, "میرا گودام میں مال کی گنتی کبھی پوری نہیں ہوتی", "g7-1")
    reply = (await pi.reply_to("g7-1")).body
    assert "کتنی بار" in reply and reply.count("؟") == 1  # RTL text intact, one question
    # v1.5 18.2: the opening is written for the owner (no fixed Roman Urdu line), so an Urdu-script
    # chat is greeted in Urdu script and says pi is an AI from Workzap in sentence one
    assert reply.startswith("ہیلو، میں pi ہوں") and "Workzap" in reply.split("۔")[0]
    await pi.close()


async def test_g8_arabic_first_message_discloses_the_ai_in_arabic(api, business_db, monkeypatch):
    prompts = adaptive(monkeypatch, more)
    pi = await workspace(api, business_db)
    on = await api.patch(
        "/api/v1/pi/settings/knowledge_config", json={"value": {"industry_packs": True}}
    )
    assert on.status_code == 200, on.text
    await say(pi, "مرحباً، عندنا مطعم في دبي والطلبات من التطبيقات تضيع", "g8-1")
    reply = (await pi.reply_to("g8-1")).body
    assert "ذكاء اصطناعي" in reply and reply.count("؟") == 1
    # The restaurant pack is loaded for a message in Arabic script (G8 "Must").
    seen = [json.loads(p) for p in prompts if p.startswith("{")]
    names = [c.get("industry") or [] for c in seen]
    assert any(n and n[0].startswith("Restaurants") for n in names), names
    assert any("Restaurants" in str(c.get("industry_knowledge")) for c in seen)
    await pi.close()


@pytest.mark.parametrize(
    ("said", "expected"),
    [
        ("I saw nori. Does it work with CCTV?", "coming soon"),  # G15
        ("What are nori's prices?", "workzap.ai/nori/pricing"),
        ("tell me about nori", "daily read for the shop"),
    ],
)
async def test_g15_nori_questions_get_honest_facts_and_no_prices(
    api, business_db, monkeypatch, said, expected
):
    prompts = adaptive(monkeypatch, more)
    pi = await workspace(api, business_db)
    await say(pi, said, "g15-1")
    reply = (await pi.reply_to("g15-1")).body
    assert expected in reply and prompts == []
    assert not any(ch.isdigit() for ch in reply)  # never a price from memory
    assert reply.count("?") <= 1
    await pi.close()
