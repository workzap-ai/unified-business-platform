"""G52, G53 and G56 (platform spec v1.6, Part 17.10 and Live Audit 6 Part 6): replays of three live
chats, turn by turn through the real pipeline. G54 and G55 live in test_pi_g54_replay_wiring.py and
test_pi_g55_burst_replay.py.

The model is SCRIPTED (it plays what a good model should say, or, where noted, a bad draft the
application must catch), so these tests prove what the application does around the model: which
messages are read, which gates fire, which state the chat is in. They do not prove a real model
would write these replies. Real database/webhook/worker; the model and WhatsApp are mocked."""

import json
import re
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from test_pi_brain_decisions import state_of
from test_pi_brain_documents import (
    roomy_limits,  # noqa: F401  (autouse fixture)
    the_offer_is_open,  # noqa: F401  (autouse: holds the offer gate open)
)
from test_pi_brain_problems import adaptive, create, problems_of, say, workspace
from test_pi_service_conversations import turn

from app.ai.manager import LLMManager
from app.modules.pi.models import PiMessage
from app.modules.pi.runtime import process_pi_event
from app.modules.pi_saas.models import PiStaffRequest

pytestmark = pytest.mark.integration

OPENING = "Hi, I'm pi, an AI from Workzap."


async def burst(pi, db, texts, ids):
    """`texts` arrive while a newer message is already waiting: each is kept, none is answered."""
    conversation = await pi.conversation()
    jobs = []
    for mid, text in zip(ids, texts, strict=True):
        assert (await pi.inbound(text, mid)).status_code == 200
        jobs.append(pi.app.state.queue.jobs[-1][1])
    newer = PiMessage(
        tenant_id=conversation.tenant_id,
        environment_id=conversation.environment_id,
        conversation_id=conversation.id,
        direction="inbound",
        sender_type="customer",
        message_type="text",
        body="placeholder for the newer message",
        provider_message_id=f"newer-{ids[0]}",
        status="received",
        created_at=datetime.now(UTC) + timedelta(seconds=30),
    )
    db.add(newer)
    await db.commit()
    for job in jobs:
        await process_pi_event(pi.ctx, *job)
    newer.status = "processed"
    rows = (await db.scalars(select(PiMessage).where(PiMessage.provider_message_id.in_(ids)))).all()
    assert {r.status for r in rows} == {"skipped"}
    now = datetime.now(UTC)
    for outbound in await pi.outbound():
        outbound.created_at = now - timedelta(hours=1)
    for offset, mid in zip(range(len(ids) * 2, 0, -2), ids, strict=True):
        next(r for r in rows if r.provider_message_id == mid).created_at = now - timedelta(
            minutes=offset
        )
    await db.commit()


def rewriting(monkeypatch, make, fix):
    """Like `adaptive`, but a rewrite prompt ("Don't send that draft...") gets `fix(context)`, the
    reply a good model writes once told what broke. Returns (all prompts, the rewrite prompts)."""
    prompts: list[str] = []
    rewrites: list[str] = []
    last: dict = {}

    async def complete(self, scope, output, **kwargs):
        if kwargs.get("purpose") == "pi_problem_extract":
            return SimpleNamespace(value=output(), response=SimpleNamespace(attempts=[]))
        text = kwargs["messages"][-1].text()
        prompts.append(text)
        if text.startswith("{"):
            last["context"] = json.loads(text)
            last["value"] = make(last["context"], sum(p.startswith("{") for p in prompts))
        else:
            rewrites.append(text)
            last["value"] = fix(last["context"])
        return SimpleNamespace(value=last["value"], response=SimpleNamespace(attempts=[]))

    monkeypatch.setattr(LLMManager, "complete_structured", complete)
    return prompts, rewrites


async def texts_only(pi):
    """pi's messages without the pictures (the map and the board go as their own message)."""
    return [m for m in await pi.outbound() if not (m.media or {}).get("visual")]


# --- G52: Chat A, an owner who never said what business they run ---

CHAT_A_BURST = [
    "Sale mai hai. Mera sales staff bohat tang kar raha hai mujhay. Subah say gaib rehta hai. "
    "Dophir ko phone uthatay hain toh pata chalta hai beemar hain sub. Yeh bhi nahi pata kai "
    "dokaanay visit ki, stock check kia. Naya order laye ya nahi",
    "Uskay baad koi inventory ka hisaab nahi. Shayd 6 say 10 crore ki inventory hai",
    "Sub alag alag dept kaam kar rahay hain",
]
CHAT_A_LAST = "Koi joor nahi hai"
MENU = re.compile(r"sale, stock, staff", re.IGNORECASE)
TRADE = re.compile(r"\b(?:ac units?|spare parts|gas)\b", re.IGNORECASE)


def chat_a_model(context, n):
    said = context["latest_customer_message"]
    if said == CHAT_A_LAST:
        return turn(
            reply=(
                "Subah se gaib, dopahar ko beemar, aur ye bhi pata nahi ke dukaan par gaye ya "
                "nahi: ye thaka dene wali baat hai. Jab field ka kuch aap tak pohanchta hi nahi, "
                "to stock ka hisaab bhi andhere mein rehta hai, shayad isi liye 6 se 10 crore ka "
                "itna bara farq hai. Jorr sahi hain?"
            ),
            language="roman_ur",
            problem_ops=[
                create(
                    "Sales team: no way to know where they are", "sales staff gaib", "people_staff"
                ),
                create("Stock count unknown, 6 to 10 crore", "koi hisaab nahi", "stock_inventory"),
                create("Departments work separately", "alag alag dept", "systems_tools"),
            ],
        )
    if said == "Maslay bohat hain":
        return turn(
            reply=(
                "Koi baat nahi, bohat hon to sab ek ek karke likhte hain, aap ko jaldi nahi. "
                "Aap ka karobar kis naam se hai, aur kis cheez ka?"
            ),
            language="roman_ur",
        )
    return turn(
        reply="Wapas aaye, achha laga. Pehle thora jaan lete hain: aap ka karobar kis naam se hai?",
        language="roman_ur",
    )


async def chat_a(api, db, monkeypatch, make=chat_a_model):
    prompts = adaptive(monkeypatch, make)
    pi = await workspace(api, db)
    await say(pi, "Hello again", "ga-1")
    await say(pi, "Kia haal hain?", "ga-2")
    await say(pi, "Maslay bohat hain", "ga-3")
    return pi, prompts


async def test_g52_the_burst_is_one_reply_that_reads_all_four_messages(
    api, business_db, monkeypatch
):
    pi, prompts = await chat_a(api, business_db, monkeypatch)
    before = len(await texts_only(pi))
    ids = ["ga-4", "ga-5", "ga-6"]
    await burst(pi, business_db, CHAT_A_BURST, ids)
    await say(pi, CHAT_A_LAST, "ga-7")
    assert len(await texts_only(pi)) == before + 1  # four messages, one text reply
    model_input = json.loads([p for p in prompts if p.startswith("{")][-1])
    assert model_input["burst_texts"] == CHAT_A_BURST  # the heartfelt first one is read
    assert model_input["latest_customer_message"] == CHAT_A_LAST
    reply = (await pi.reply_to("ga-7")).body
    assert re.search(
        r"gaib|thaka|Sales team", reply
    )  # the sales team (the first message) is covered
    assert reply.count("?") == 1 and reply.rstrip().endswith("?")
    assert not TRADE.search(reply)  # no business the owner never named
    await pi.close()


async def test_g52_three_problems_are_stored_and_the_map_is_due(api, business_db, monkeypatch):
    pi, _ = await chat_a(api, business_db, monkeypatch)
    await burst(pi, business_db, CHAT_A_BURST, ["ga-4", "ga-5", "ga-6"])
    await say(pi, CHAT_A_LAST, "ga-7")
    _, rows = await problems_of(business_db, pi)
    assert len(rows) == 3  # spec 4.4: the first map at three problems
    assert not any(r.title.rstrip().endswith("?") for r in rows)
    shown = [
        m
        for m in await business_db.scalars(select(PiMessage))
        if (m.media or {}).get("visual") in ("map", "board")
    ]
    assert shown, "the first map was due at three problems and none was sent"
    await pi.close()


async def test_g52_the_return_and_the_menu_are_not_cold(api, business_db, monkeypatch):
    pi, _ = await chat_a(api, business_db, monkeypatch)
    for key in ("ga-1", "ga-2", "ga-3"):
        assert not MENU.search((await pi.reply_to(key)).body)  # no category menu
    await pi.close()


def invented_trade_model(context, n):
    if context["latest_customer_message"] == CHAT_A_LAST:
        return turn(
            reply=(
                "Inventory ka koi hisaab nahi aur departments alag chal rahe hain. "
                "Ye stock zyada tar AC units ka hai ya spare parts aur gas ka?"
            ),
            language="roman_ur",
        )
    return chat_a_model(context, n)


async def test_g52_a_business_the_owner_never_named_is_not_spoken_as_fact(
    api, business_db, monkeypatch
):
    _, rewrites = rewriting(monkeypatch, invented_trade_model, lambda c: chat_a_model(c, 0))
    pi = await workspace(api, business_db)
    for key, text in (
        ("ga-1", "Hello again"),
        ("ga-2", "Kia haal hain?"),
        ("ga-3", "Maslay bohat hain"),
    ):
        await say(pi, text, key)
    await burst(pi, business_db, CHAT_A_BURST, ["ga-4", "ga-5", "ga-6"])
    await say(pi, CHAT_A_LAST, "ga-7")
    # G11 noAssumedIndustry: the draft with "AC units, spare parts, gas" is sent back, never sent
    assert any("industry word" in r for r in rewrites), rewrites
    for outbound in await pi.outbound():
        assert not TRADE.search(outbound.body or ""), outbound.body
    await pi.close()


# --- G53: Chat B, the locksmith who adds a second business ----------------------------------------

LOCKSMITH = (
    "I run a locksmith business in Sharjah, one van and two technicians. Calls come at night and "
    "we miss many because both phones are busy or switched off."
)
FARM = (
    "Ajman mein chhota hydroponic lettuce farm hai, do restaurants ko dete hain. Harvest ek saath "
    "aata hai, kuch patte zaya hote hain aur phir kai din maal hota hi nahi."
)


def chat_b_model(context, n):
    said = context["latest_customer_message"]
    if said == LOCKSMITH:
        return turn(
            reply=(
                f"{OPENING} If both phones are busy, the caller gets nothing and tries the next "
                "number. Roughly what is one missed call worth to you?"
            ),
            language="en",
            problem_ops=[
                create(
                    "Missed night calls, both phones busy",
                    "we miss many because both phones are busy",
                    "sales_revenue",
                )
            ],
        )
    if said.startswith("mostly busy"):
        return turn(
            reply=(
                "Sure. Two things you can start now: after each job, ring back the missed numbers "
                "first. Put a short spoken greeting on each phone saying you are on a job and will "
                "ring back. Workzap could set it up so every missed call gets an instant message "
                "back saying a technician will ring soon. What does one missed call usually cost "
                "you?"
            ),
            language="en",
        )
    if said == FARM:
        return turn(
            reply=(
                "Ye do alag masle hain: ek saath bahut maal aane se patte zaya hote hain, aur "
                "phir kai din restaurants ko dene ke liye kuch nahi hota. Dono karobar ke naqshe "
                "alag rakhte hain. Restaurants ko aap kitne din pehle batate hain?"
            ),
            language="roman_ur",
            problem_ops=[
                create(
                    "Farm harvest comes in lumps, waste then no stock",
                    "Harvest ek saath aata hai",
                    "stock_inventory",
                )
            ],
        )
    return turn(reply="Noted. Anything else getting in the way?", language="en")


async def test_g53_the_locksmith_replay(api, business_db, monkeypatch):
    adaptive(monkeypatch, chat_b_model)
    pi = await workspace(api, business_db)
    await say(pi, LOCKSMITH, "gb-1")
    first = (await pi.reply_to("gb-1")).body
    assert "I'm pi" in first or "AI" in first.split(".")[0]  # discloses it is an AI
    assert "noted" not in first.lower()  # no filler echo ("I've noted it")
    assert first.count("?") == 1 and first.rstrip().endswith("?")

    await say(pi, "mostly busy, we are both on jobs. what can you do?", "gb-2")
    answer = (await pi.reply_to("gb-2")).body
    assert "Workzap" in answer  # one line on what Workzap would build
    assert not re.search(r"solution document|quote made|shall i get", answer, re.IGNORECASE)
    assert answer.count("?") == 1 and answer.rstrip().endswith("?")
    assert (await state_of(business_db, pi)).flow_state != "S5_READINESS"  # no early offer
    assert (await business_db.scalars(select(PiStaffRequest))).all() == []

    await say(pi, FARM, "gb-3")
    farm = (await pi.reply_to("gb-3")).body
    assert not re.search(r"breakdown|rota|on-call|alag note kar li", farm, re.IGNORECASE)
    assert not re.search(r"missed night|locksmith|van", farm, re.IGNORECASE)  # engages the farm
    assert farm.count("?") == 1 and farm.rstrip().endswith("?")
    assert (await state_of(business_db, pi)).flow_state != "S5_READINESS"
    _, rows = await problems_of(business_db, pi)
    assert len(rows) == 2 and any("harvest" in r.title.lower() for r in rows)
    await pi.close()


def foreign_vocabulary_model(context, n):
    if context["latest_customer_message"] == FARM:
        return turn(
            reply=(
                "Haan, ho sakta hai. Lettuce farm wali baat bhi alag note kar li hai. Har "
                "breakdown call ka waqt likh lein. Raat ko kis waqt sab se zyada calls miss hoti "
                "hain?"
            ),
            language="roman_ur",
        )
    return chat_b_model(context, n)


async def test_g53_a_reply_does_not_announce_a_separate_note(api, business_db, monkeypatch):
    adaptive(monkeypatch, foreign_vocabulary_model)
    pi = await workspace(api, business_db)
    await say(pi, LOCKSMITH, "gb-1")
    await say(pi, "mostly busy, we are both on jobs. what can you do?", "gb-2")
    await say(pi, FARM, "gb-3")
    farm = (await pi.reply_to("gb-3")).body
    assert not re.search(r"alag note kar li", farm, re.IGNORECASE), farm  # A4-4, A4-11
    await pi.close()


@pytest.mark.xfail(
    reason="G53 'breakdown call' (spec 17.4 G9, a term from another industry) is only checked "
    "against the packs' vocabulary when knowledge_config.industry_packs is on; this replay "
    "runs with packs off, so nothing knows 'breakdown call' is not a locksmith term",
    strict=True,
)
async def test_g53_a_term_from_another_industry_does_not_reach_the_owner(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, foreign_vocabulary_model)
    pi = await workspace(api, business_db)
    await say(pi, LOCKSMITH, "gb-1")
    await say(pi, "mostly busy, we are both on jobs. what can you do?", "gb-2")
    await say(pi, FARM, "gb-3")
    farm = (await pi.reply_to("gb-3")).body
    try:
        assert not re.search(r"breakdown call", farm, re.IGNORECASE), farm
    finally:
        await pi.close()


# --- G56: the 30 October chat (Live Audit 6) ---
# Voice notes arrive as their transcription (the transcriber is not part of this replay).

VOICE_1 = (
    "Mujhe sales barhani hain aur customer pipeline banani hai. Ads chahiye jis se customers "
    "aayen, online payment chahiye aur website chahiye. To aap ye sab kaam kar denge hamein? "
    "Aur main khud sales barhane ke liye kya kar sakta hoon"
)
VOICE_2 = (
    "Nahi, ye hum already karte hain lekin isse koi faida nahi ho raha. Mujhe aisa system chahiye "
    "jis se sales fouran start hon. Hum budget lagane ke liye ready hain. Poora platform chahiye: "
    "sales kahan se aati hain, kaise aati hain, kahan jati hain, sales manager un se call ya "
    "WhatsApp par kaise baat karta hai, aur customer ko kaise laya jata hai"
)
COMPLAINT = "bhai kitni baar bataon mai ik he baat"
ASK_QUOTE = "bhai mujhay quote do abhi wohi pooch raha hoan"


def g56_model(context, n):
    said = context.get("latest_customer_message", "")
    if said == "Hello":
        return turn(
            reply="Hi, I'm pi, an AI from Workzap. What is your business called?", language="en"
        )
    if said.startswith("Its artwing"):
        return turn(
            reply="Abhi mujhe iske baare mein kuch nahi pata. Website ka link bhej dein?",
            language="roman_ur",
        )
    if said == "Abhi kuch nahi hai":
        return turn(
            reply="Theek hai. In dino sab se zyada kya bhaari lag raha hai?", language="roman_ur"
        )
    if said == VOICE_1:
        return turn(
            reply=(
                "Haan, ye Workzap kar sakta hai: ads, sales follow-up, online payment, website. "
                "Pichle teen mahine mein kitni enquiries aayin?"
            ),
            language="roman_ur",
        )
    if said == VOICE_2:
        return turn(
            reply=(
                "Ideas pehle ho chuke, budget ready hai: masla poore system ka hai, ideas ka nahi. "
                "Naye customers abhi kahan se aate hain?"
            ),
            language="roman_ur",
            problem_ops=[
                create(
                    "No system from enquiry to the sales manager",
                    "ye hum already karte hain lekin isse koi faida nahi ho raha",
                    "sales_revenue",
                )
            ],
        )
    if said == "Zero":
        return turn(
            reply=(
                "Zero ka matlab referral hi ek source hai aur paid kaam nahi bana. "
                "Enquiries kam aati hain, ya aati hain par band nahi hoti?"
            ),
            language="roman_ur",
        )
    return turn(reply="Theek hai. Is par thora aur batayein?", language="roman_ur")


async def g56_chat(api, db, monkeypatch, make=g56_model, install=True):
    if install:
        adaptive(monkeypatch, make)
    pi = await workspace(api, db)
    await say(pi, "Hello", "g6-1")
    await say(pi, "Its artwing studios. Aap ko iskay baray mai kuch pata hai?", "g6-2")
    await say(pi, "Abhi kuch nahi hai", "g6-3")
    await say(pi, VOICE_1, "g6-4")
    await say(pi, VOICE_2, "g6-5")
    return pi


async def test_g56_every_voice_note_gets_a_reply_that_uses_the_budget_and_the_brief(
    api, business_db, monkeypatch
):
    pi = await g56_chat(api, business_db, monkeypatch)
    for key in ("g6-4", "g6-5"):
        assert (await pi.reply_to(key)).body  # the 11:21 voice note is not left without a reply
    second = (await pi.reply_to("g6-5")).body.lower()
    assert "budget" in second and "system" in second, second
    assert not re.search(r"itne hi ideas|koi naya sawal nahi", second)  # no dead end
    await say(pi, "Zero", "g6-6")
    assert "zero" in (await pi.reply_to("g6-6")).body.lower()  # the number is used
    await pi.close()


async def test_g56_no_board_item_is_a_question_or_a_complaint(api, business_db, monkeypatch):
    def noisy(context, n):
        if context.get("latest_customer_message") == COMPLAINT:
            return turn(
                reply="Aap sahi hain, aap ne ye sab bataya. Ab kaun sa masla sab se bhaari hai?",
                language="roman_ur",
                problem_ops=[
                    create("kitni baar bataon?", COMPLAINT),
                    create("Aap ye sab kaam kar denge hamein?", "to aap ye sab kaam kar denge?"),
                ],
            )
        return g56_model(context, n)

    def fixed(context):
        if context.get("latest_customer_message") != COMPLAINT:
            return g56_model(context, 0)
        return turn(
            reply="Aap sahi hain, aap ne ye sab bataya. Ab kaun sa masla sab se bhaari hai?",
            language="roman_ur",
        )

    _, rewrites = rewriting(monkeypatch, noisy, fixed)
    pi = await g56_chat(api, business_db, monkeypatch, install=False)
    await say(pi, COMPLAINT, "g6-7")
    _, rows = await problems_of(business_db, pi)
    titles = [r.title for r in rows]
    assert titles  # the real problem is there
    assert rewrites, "the notes 'kitni baar bataon?' and 'Aap ye sab kaam kar denge?' were accepted"
    assert not any("?" in t or "kitni baar" in t.lower() for t in titles), titles
    await pi.close()


async def test_g56_quote_do_starts_the_quote(api, business_db, monkeypatch):
    pi = await g56_chat(api, business_db, monkeypatch)
    await say(pi, ASK_QUOTE, "g6-9")
    body = (await pi.reply_to("g6-9")).body
    assert (await state_of(business_db, pi)).flow_state == "S6_PREPARING", body
    assert not re.search(r"ab tak jo maine note|aap ke masle", body, re.IGNORECASE)  # no summary
    await pi.close()


@pytest.mark.xfail(
    reason="spec v1.6 G56 says 'kitna kharcha' also starts the quote; the owner approved decision "
    "D-1 (2026-10-31): a price question is answered first and does not start the quote, only an "
    "explicit quote ask does (see test_a_roman_urdu_cost_question_at_the_offer_does_not_start_the_"
    "quote). Left failing on purpose until the spec and D-1 are reconciled.",
    strict=True,
)
async def test_g56_kitna_kharcha_starts_the_quote(api, business_db, monkeypatch):
    pi = await g56_chat(api, business_db, monkeypatch)
    await say(pi, "kitna kharcha hoga yeh sab karnay ka?", "g6-8")
    await pi.reply_to("g6-8")
    try:
        assert (await state_of(business_db, pi)).flow_state == "S6_PREPARING"
    finally:
        await pi.close()
