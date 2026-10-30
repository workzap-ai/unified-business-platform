# ruff: noqa: E501  (the owner's words are kept whole)
"""Regression: Artwing Studios, 2026-10-30. The owner asked, in two voice notes, for a whole sales
system (ads, pipeline and CRM, lead-source tracking, sales-manager calls and WhatsApp, online payment
linked to the website, onboarding, service delivery), said the referral, outreach and enquiry log do
not work, and said the budget is ready. pi gave two generic ideas and closed with "those are all the
ideas": no offer. The owner's "aap ye sab kaam kar denge hamein?" is R3 (can Workzap do it) and was not
read; the ask was also forgotten on the next turn.

The transcript is kept whole below, with the requirements it carries, so a later fix can be judged
against all of them.
"""

import pytest

from app.modules.pi import box, box_signals, expert_advisor, service_conversation, system_ask

VOICE_1 = (
    "Jee assalam walaikum. Aap mujhe yeh bata sakte hain ke mujhe apna jo hai business grow karna hai, "
    "apni sales badhani hai aur apne customers ki ek pipeline banana hai. Hamein ads chalani hai aur "
    "customer aaye us ads ke through aur pura peechhe ek pipeline bana hua ho. Customer ki payment mujhe "
    "online karvani hai. Mere-- mujhe a, aur wo jo hai website ke saath link bhi ho aur, aur bhi bahut "
    "sare kaam karvane hain hamein. To aap ye sab kaam kar denge hamein aur doosra mujhe batayein ke "
    "agar mujhe sales increase karni hai to main kya kar sakta hoon apne business ke liye?"
)
VOICE_2 = (
    "Nahi, ye hum already karte hain lekin isse koi faida nahi ho raha humey sales ka. Main chah raha "
    "hun ki humara koi aisa system bane ki humey sales milna shuru ho fouran se. Hum budget lagane ke "
    "liye ready hain, aisa masla nahi hai, paise lagayenge. But humey pura uska ek platform banana hai "
    "na ki sales kahan ayengi, kaise ayengi, kahan se ayengi aur phir kidhir jayegi sale. Phir hamare jo "
    "sale manager hai vo unke saath kaise baat karengy, call karengy, WhatsApp karengy aur uske baad jo "
    "hai pura ek system kaise bnega. Phir customer ko kaise lekar aya jayega aur phir customer ko hum "
    "service kya dengy?"
)
FIRST_ANSWER = "Referring say sirf"
WEBSITE = "https://artwingstudios.co/ yeh humari website hai"
IDEAS_GIVEN = [
    "Jin logon ne pehle aap ke saath kaam kiya hai, unhein message karein",
    "Jo bhi shakhs aap ke kaam ke bare mein poochhe, uska naam likh lein",
]

# The requirements the owner stated, one per module of the system.
REQUIREMENTS = {
    "lead_generation": "ads",
    "pipeline_crm": "pipeline",
    "lead_source_tracking": "kahan se ayengi",
    "sales_manager": "sale manager",
    "outreach": "WhatsApp karengy",
    "online_payment": "payment mujhe online",
    "website_link": "website ke saath link",
    "onboarding": "customer ko kaise lekar aya jayega",
    "service_delivery": "customer ko hum service kya dengy",
    "budget_ready": "budget lagane ke liye ready",
}


def context(said="", brief=None, **extra):
    return {
        "latest_customer_message": said,
        "noted_problems": [{"ref": "p1", "title": "Sales are not coming in", "cause": "x"}],
        "brief": brief or {},
        "history": [],
        "box_offer": True,
        "reply_language": "roman_ur",
        "flow": {"state": "S3_NOTED"},
        **extra,
    }


def test_the_transcript_carries_every_requirement():
    said = f"{VOICE_1} {VOICE_2}"
    missing = [name for name, words in REQUIREMENTS.items() if words.lower() not in said.lower()]
    assert not missing


def test_can_you_do_all_this_is_read_in_the_owners_words():
    assert box_signals.asks_who_or_how_long(VOICE_1)
    assert system_ask.asks_can_you_do("To aap ye sab kaam kar denge hamein")
    assert system_ask.asks_can_you_do("Will you build the whole thing for us?")
    assert system_ask.asks_can_you_do("کیا آپ یہ سب کام کر دیں گے")


@pytest.mark.parametrize(
    "said",
    [
        VOICE_2,  # asks how, never whether Workzap will do it
        "Aap kya kya karte hain?",
        "main kya kar sakta hoon",
        "the cashiers come late",
        "Referring say sirf",
        "",
    ],
)
def test_other_words_are_not_the_ask(said):
    assert not system_ask.asks_can_you_do(said)


def test_the_ask_survives_the_next_turn_and_opens_r3():
    brief = system_ask.note({}, VOICE_1)
    assert brief["asked_can_you_do"] is True
    later = context(VOICE_2, brief=brief)
    assert not box_signals.asks_who_or_how_long(VOICE_2)  # the new message does not ask again
    allowed, rule, _ = box.can_offer(box.offer_facts(later))
    assert allowed and rule == "R3"


def test_without_the_ask_nothing_opens_early():
    later = context(VOICE_2, brief={})
    allowed, rule, why = box.can_offer(box.offer_facts(later))
    assert not allowed and rule == "B", why


def test_the_ask_closes_once_the_offer_is_made_or_declined():
    base = system_ask.note({}, VOICE_1)
    assert system_ask.open_ask(base)
    assert not system_ask.open_ask({**base, "offer": {"at": "x"}})
    assert not system_ask.open_ask({**base, "box_declined_at": "2026-10-30 11:00"})
    assert not system_ask.open_ask({**base, "declined_recently": True})


def test_a_chat_that_never_asked_is_not_given_the_ask():
    assert system_ask.note({}, "the cashiers come late") == {}


def test_tried_and_failed_collects_what_the_owner_already_does():
    found = system_ask.tried_and_failed([VOICE_1, VOICE_2, FIRST_ANSWER, WEBSITE])
    assert found == [VOICE_2[:240]]


def test_the_expert_is_told_what_failed():
    payload = expert_advisor.Steer(tried_and_failed=[VOICE_2[:240]]).payload()
    (told,) = payload["owner_already_does_or_says_did_not_help_never_suggest_these"]
    assert "already karte" in told
    assert "owner_already_does_or_says_did_not_help_never_suggest_these" not in (
        expert_advisor.Steer().payload()
    )


def capped_turn():
    turn = service_conversation.ServiceTurn(reply="-")
    turn.reply = ""  # the expert settled the turn without a reply of its own
    turn._problem_capped = True
    return turn


def test_a_capped_chat_does_not_close_on_an_owner_who_asked_for_the_whole_system():
    ctx = context(
        VOICE_2,
        brief=system_ask.note({}, VOICE_1),
        expert_on=True,
        solution_asked_no_ideas=True,
        history=[{"role": "ai", "text": "\n".join(IDEAS_GIVEN)}],
    )
    turn = capped_turn()
    service_conversation.brain_no_ideas(turn, ctx)
    assert "itne hi ideas" not in turn.reply
    assert (
        turn.reply.strip().endswith(".") and "?" not in turn.reply
    )  # the offer is the one question
    service_conversation.brain_offer(turn, ctx)
    assert turn.reply.strip().endswith("?")
    assert turn._decision is not None and turn._decision.why == "R-OFFER-01"
    for banned in ("price", "qeemat", "$", "Rs", "bank", "account", "payment"):
        assert banned not in turn.reply  # the offer names the document and quote, never a price


def test_a_capped_chat_without_the_ask_still_says_so_and_asks_one_question():
    ctx = context(
        VOICE_2,
        brief={},
        expert_on=True,
        solution_asked_no_ideas=True,
        history=[{"role": "ai", "text": "\n".join(IDEAS_GIVEN)}],
    )
    turn = capped_turn()
    service_conversation.brain_no_ideas(turn, ctx)
    assert turn.reply.count("?") == 1 and turn.reply.strip().endswith("?")
    service_conversation.brain_offer(turn, ctx)
    assert turn._decision is None  # B1 to B7 do not hold yet: no offer


@pytest.mark.parametrize("said", ["ok", "hmm", "maybe", "let me think"])
def test_a_filler_after_the_offer_is_still_not_a_yes(said):
    from app.modules.pi import decisions

    answer, sure = decisions.classify(said)
    assert not (answer == decisions.Answer.YES and sure >= decisions.YES_AT)
