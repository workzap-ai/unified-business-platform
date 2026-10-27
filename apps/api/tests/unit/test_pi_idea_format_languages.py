# ruff: noqa: E501
"""Ideas read as plain sentences (no dots), other scripts keep their own language, and short
Roman Urdu asks and dislikes are understood."""

import pytest

from app.modules.pi import solution_ask, solution_score
from app.modules.pi.language import in_script, other_script
from app.modules.pi.solution_rules import count_ideas, idea_lines

CHINESE = "Chinese (Simplified)"


def test_idea_lines_are_bullet_lines_of_one_sentence_each() -> None:
    text = idea_lines(
        [
            "Count the till together at shift change, so a gap is placed.",
            "Log each order in one book, so none is missed.",
        ]
    )
    assert text.splitlines()[0].startswith("• Count the till")
    assert text.splitlines()[1].startswith("• Log each order")
    assert count_ideas(text) == 2


def test_one_idea_is_one_sentence() -> None:
    assert (
        idea_lines(["Write the order down, so it is not missed"])
        == "• Write the order down, so it is not missed."
    )


@pytest.mark.parametrize(
    "text",
    [
        "你好，我经营一家小型制造工厂。我们每天生产几百件产品。",
        "我们有三个仓库和五十名员工。我还希望系统能够预测需求",
    ],
)
def test_chinese_is_its_own_language(text: str) -> None:
    assert other_script(text) == CHINESE
    assert in_script(text, CHINESE)


def test_latin_and_arabic_are_not_other_scripts() -> None:
    assert other_script("Hello, I own a shop") is None
    assert other_script("مرحبا، لدي شركة توصيل طلبات") is None
    assert not in_script("I have noted the three points", CHINESE)


@pytest.mark.parametrize(
    "text",
    [
        "Idea psnd NH aiya mujhe",
        "idea pasand nahi aya",
        "ye idea acha nahi hai",
        "I don't like these ideas",
    ],
)
def test_disliked_ideas_ask_for_a_different_kind(text: str) -> None:
    reaction = solution_score.classify(text)
    assert reaction is not None and reaction.signal == "idea_generic"


@pytest.mark.parametrize(
    "text", ["Aur idea dw", "aur idea chahiye", "or idea do", "idea dena", "mazeed suggestions"]
)
def test_more_ideas_in_roman_urdu_is_an_ask(text: str) -> None:
    assert solution_ask.asked_for_ideas(text)


def _turn(reply: str):  # noqa: ANN202
    from types import SimpleNamespace

    return SimpleNamespace(reply=reply, _summary=False, _free=False)


def test_model_bullets_become_prose_for_handed_ideas() -> None:
    from app.modules.pi.service_conversation import asked_without_ideas, brain_prose_ideas

    turn = _turn("Theek hai.\n• Sheets alag rakhein.\n• Roz update karein.\n\nKya main banwa doon?")
    brain_prose_ideas(turn, {"solution_ideas": ["x"], "reply_language": "roman_ur"})
    assert turn.reply.splitlines()[1] == "• Sheets alag rakhein."
    assert turn.reply.splitlines()[2] == "• Roz update karein."
    assert asked_without_ideas(
        {
            "ideas_given": 2,
            "latest_customer_message": "Idea psnd NH aiya",
            "flow": {"state": "S3_NOTED"},
        }
    )


def test_summary_lists_and_other_languages_keep_their_dots() -> None:
    from app.modules.pi.service_conversation import brain_prose_ideas

    summary = _turn("Noted:\n• one\n• two")
    summary._summary = True
    brain_prose_ideas(summary, {"solution_ideas": ["x"], "reply_language": "en"})
    assert "•" in summary.reply
    arabic = _turn("نعم\n• أ\n• ب")
    brain_prose_ideas(arabic, {"solution_ideas": ["x"], "reply_language": "ar"})
    assert "•" in arabic.reply


@pytest.mark.parametrize("text", ["给我一些建议", "有什么办法解决这个问题", "我们该如何解决"])
def test_chinese_ask_for_ideas(text: str) -> None:
    assert solution_ask.asked_for_ideas(text)


def test_a_message_that_tells_the_problem_and_asks_for_a_fix_is_still_extracted() -> None:
    from app.modules.pi import problem_extract

    said = "Orders get missed, staff make mistakes, I cannot track sales. Can you help me fix this?"
    base = {"pi_mode": "brain", "flow": {"state": "S1_LISTENING"}, "latest_customer_message": said}
    assert problem_extract.wants_extraction({**base, "solution_asked_no_ideas": True}, "", [])
    noted = {**base, "solution_asked": True, "noted_problems": [{"ref": "p1"}]}
    assert not problem_extract.wants_extraction(noted, "", [])


def test_covers_is_a_noun_phrase_even_for_are_set_in_the_document() -> None:
    covered = solution_ask.covers(
        {"free_stops": "Recall intervals and message flow are set in the solution document."}
    )
    assert covered == "Recall intervals and message flow"


def test_free_ideas_never_state_a_time() -> None:
    from app.modules.pi import solution_free

    ideas = [
        "Check this week's payouts against the order slips, so you can see which brand is mixed up.",
        "Keep one list per brand with the last promise, so chasing stays tidy and nothing is forgotten.",
    ]
    kept = solution_free.vetted(ideas, "payouts are mixed up", [])
    assert kept == [
        "Keep one list per brand with the last promise, so chasing stays tidy and nothing is forgotten."
    ]


def test_brain_never_leaves_an_empty_reply() -> None:
    from types import SimpleNamespace

    from app.modules.pi.service_conversation import brain_never_empty

    turn = SimpleNamespace(
        reply="", request_human=False, _decision=None, _summary=False, awaiting_customer=False
    )
    context = {
        "reply_language": "en",
        "latest_customer_message": "Ye kaise karna hai?",
        "flow": {"state": "S3_NOTED"},
        "history": [{"role": "ai", "text": "Hi"}],
    }
    brain_never_empty(turn, context)
    assert turn.reply.strip() and "once the problems are noted" not in turn.reply


def test_roman_urdu_idea_lines_lose_their_english_scaffolding() -> None:
    from types import SimpleNamespace

    from app.modules.pi.service_conversation import brain_prose_ideas

    turn = SimpleNamespace(
        reply="Sure.\nFirst, register dekho, so nuksan saaf ho.\nSecond, safha alag likho, so hisaab milay.",
        _summary=False,
        _free=True,
    )
    brain_prose_ideas(turn, {"solution_ideas": ["x"], "reply_language": "roman_ur"})
    assert "• Register dekho, taake nuksan saaf ho." in turn.reply
    assert "• Safha alag likho, taake hisaab milay." in turn.reply


def _promise_turn(reply: str):  # noqa: ANN202
    from types import SimpleNamespace

    return SimpleNamespace(
        reply=reply,
        request_human=False,
        _decision=None,
        _summary=False,
        awaiting_customer=False,
        problem_ops=[],
    )


def test_the_document_is_never_promised_before_the_offer_was_accepted() -> None:
    from app.modules.pi.service_conversation import brain_no_early_promise

    noted = {
        "reply_language": "roman_ur",
        "flow": {"state": "S2_CLARIFYING"},
        "noted_problems": [{"ref": "p1"}],
    }
    box_off = _promise_turn("Theek hai. Workzap solution document aur quote ab tayar kiya jayega.")
    brain_no_early_promise(box_off, noted)
    assert "tayar kiya jayega" not in box_off.reply and box_off._decision is not None  # box off
    ready = {
        **noted,
        "box_offer": True,
        "noted_problems": [{"ref": "a", "since": "x"}, {"ref": "b", "impact": "y"}, {"ref": "c"}],
        "brief": {"map_reviewed": True, "ranked": True, "voluntary_problems": 1},
        "history": [{"role": "ai"}] * 9,
    }
    turn = _promise_turn("Theek hai. Workzap solution document aur quote ab tayar kiya jayega.")
    brain_no_early_promise(turn, ready)
    assert "tayar kiya jayega" not in turn.reply and turn._decision is not None
    assert turn._decision.to.value == "S5_READINESS" if hasattr(turn._decision, "to") else True

    nothing = _promise_turn("The document and quote will be prepared and sent here.")
    brain_no_early_promise(nothing, {"reply_language": "en", "flow": {"state": "S1_LISTENING"}})
    assert "once the problems are noted" not in nothing.reply and nothing._decision is None


def test_the_conditional_line_and_later_states_are_left_alone() -> None:
    from app.modules.pi.service_conversation import brain_no_early_promise

    fine = _promise_turn("Workzap solution document tab banega jab problems note ho jayen.")
    brain_no_early_promise(fine, {"flow": {"state": "S2_CLARIFYING"}})
    assert fine.reply.startswith("Workzap solution document tab banega")
    later = _promise_turn("Maine Workzap se document aur quote tayyar karne ko keh diya hai.")
    brain_no_early_promise(later, {"flow": {"state": "S5_READINESS"}})
    assert later.reply.startswith("Maine Workzap")


def test_the_ideas_opener_answers_a_request_for_a_fix() -> None:
    from app.modules.pi.service_conversation import ideas_opener

    assert (
        ideas_opener({"latest_customer_message": "Ap solution dein"})
        == "Here are two ideas you can try now:\n"
    )
    assert ideas_opener({"latest_customer_message": "Haan, har hafte hota hai"}) == ""
    assert ideas_opener({}) == "Here are two ideas you can try now:\n"


def test_an_idea_already_said_is_not_said_again() -> None:
    from types import SimpleNamespace

    from app.modules.pi.service_conversation import brain_no_repeat

    first = "First, count each branch's unpaid fees by name, so you see who owes the most."
    context = {
        "reply_language": "en",
        "history": [{"role": "ai", "text": "Sure.\n" + first + "\nSecond, write the dates down."}],
    }
    same = SimpleNamespace(
        reply="Sure.\n" + first + "\nSecond, write the dates down.",
        _summary=False,
        _decision=None,
        request_human=False,
        _english=False,
        awaiting_customer=False,
    )
    brain_no_repeat(same, context)
    assert same.reply.startswith("Those are the ideas I have")
    mixed = SimpleNamespace(
        reply="Sure.\n" + first + "\nSecond, ask parents to pay by bank transfer on a fixed day.",
        _summary=False,
        _decision=None,
        request_human=False,
        _english=False,
        awaiting_customer=False,
    )
    brain_no_repeat(mixed, context)
    assert "count each branch" not in mixed.reply and "bank transfer" in mixed.reply


def test_roman_polish_removes_leftover_english_scaffolding() -> None:
    from app.modules.pi.service_conversation import roman_polish

    out = roman_polish(
        "Sure.\nFirst, register dekho, so nuksan saaf ho.\nSecond, safha alag likho."
    )
    assert out.splitlines()[0] == "Theek hai."
    assert "• register dekhein, taake nuksan saaf ho." in out and "• safha alag likhein." in out
    assert roman_polish("Ji bilkul, note kar liya.") == "Ji bilkul, note kar liya."


def test_problem_words_pick_the_trade_when_none_is_stated() -> None:
    from app.modules.pi import industry_overlap, industry_packs

    said = [
        "Lakkar mandi mein do yard hain. Carpenter udhaar pe maal le jaate hain aur mahinon nahi dete."
    ]
    fused = industry_overlap.fuse(industry_packs.detect(said), said)
    assert fused.primary == "forestry_timber_and_wood_traders"


def test_a_stated_trade_is_never_overridden_by_problem_words() -> None:
    from app.modules.pi import industry_overlap, industry_packs

    said = ["I run a private school with 800 students. Fees and attendance are manual."]
    found = industry_packs.detect(said)
    assert found.stated and industry_overlap.fuse(found, said) is found


def test_a_direct_document_request_is_a_yes_but_a_solution_ask_is_not() -> None:
    from app.modules.pi import decisions
    from app.modules.pi.flow import State

    facts = {"problem_count": 2, "group_count": 1, "problem_refs": ["a", "b"], "brief": {}}
    for said in ("dain solution document mujhay", "quote do", "Haan document aur quote bana dein"):
        decided = decisions.decide(State.S3_NOTED, said, "roman_ur", facts)
        assert decided is not None and decided.next_state == State.S6_PREPARING, said
    # "solution dain" asks for ideas, never for the document
    assert decisions.decide(State.S3_NOTED, "Solution dain", "roman_ur", facts) is None
    # a question about cost is not a request
    assert (
        decisions.decide(State.S3_NOTED, "document ka quote kitna hoga", "roman_ur", facts) is None
    )


@pytest.mark.parametrize(
    "text",
    [
        "Solution dain",
        "solution?",
        "Let me know a solution",
        "mujhe solution den",
        "koi solution hai iska?",
        "sub ok hai solution bataye kub say pooch raha hoan?",
    ],
)
def test_live_chat_phrases_ask_for_ideas(text: str) -> None:
    assert solution_ask.asked_for_ideas(text)


def test_a_problem_statement_with_koi_hal_nahi_is_not_an_ask() -> None:
    assert not solution_ask.asked_for_ideas("koi hal nahi hai is masle ka")


@pytest.mark.parametrize(
    ("text", "name"),
    [
        (
            "Halo Pi, tolong pakai bahasa Indonesia ya. Aku punya usaha jualan baju online dan lagi ada masalah di pencatatan pesanan, sering keliru.",
            "Indonesian",
        ),
        ("Pakai bahasa Indonesia", "Indonesian"),
        ("Kamu ada ai yang lain tidak? Aku mau chat mereka", "Indonesian"),
        ("میشه در فارسی صبحت کنم", "Persian"),
        ("کار من خیاطی", "Persian"),
    ],
)
def test_other_languages_are_recognised(text: str, name: str) -> None:
    from app.modules.pi.language import asked_language, latin_other, other_script

    assert (asked_language(text) or latin_other(text) or other_script(text)) == name


def test_english_roman_urdu_and_urdu_script_are_not_other_languages() -> None:
    from app.modules.pi.language import latin_other, other_script

    for text in (
        "Hi, I run a private school with 800 students and the fees are manual",
        "Mera kiryana store hai aur udhaar ka hisaab kitab mein gadbad hai",
        "میرا کام ٹیکسٹائل کا ہے اور مجھے ہاں کی ضرورت ہے",
        "مرحبا، عندي شركة توصيل",
    ):
        assert latin_other(text) is None and other_script(text) is None, text


def test_a_requested_language_is_asked_for_by_name() -> None:
    from app.modules.pi.language import asked_language

    assert asked_language("Please reply in French") == "French"
    assert asked_language("Translate Indonesia") == "Indonesian"
    assert asked_language("Talk to me in English please") is None


def test_the_problem_card_never_draws_script_the_font_cannot_and_never_doubles_quotes() -> None:
    from types import SimpleNamespace

    from app.modules.pi import brain_visuals

    rows = [
        SimpleNamespace(
            user_words=['"Mera kiryana store hai"'], title="Udhaar hisaab", category="x"
        ),
        SimpleNamespace(user_words=["کسٹمر رابطہ"], title="Customer rabta", category="x"),
    ]
    words = brain_visuals._drawable_words(rows)
    assert words == ["Mera kiryana store hai", "Customer rabta"]


def test_roman_urdu_uses_aap_forms_and_no_gendered_samajh_gaya() -> None:
    from app.modules.pi.service_conversation import roman_polish

    out = roman_polish("Notebook mein roz likho aur check karo, samajh gaya.")
    assert "likhein" in out and "karein" in out and "samajh liya" in out
    assert "karo" not in out and "likho" not in out


def test_an_empty_reply_to_a_solution_ask_gets_the_honest_line_and_the_offer_not_the_old_v3_line() -> (
    None
):
    from types import SimpleNamespace

    from app.modules.pi.service_conversation import brain_never_empty

    turn = SimpleNamespace(
        reply="", request_human=False, _decision=None, _summary=False, awaiting_customer=False
    )
    context = {
        "reply_language": "en",
        "latest_customer_message": "Solution dain",
        "noted_problems": [{"ref": "p1"}],
        "flow": {"state": "S3_NOTED"},
        "history": [{"role": "ai", "text": "Hi"}],
    }
    brain_never_empty(turn, context)
    assert "once the problems are noted" not in turn.reply
    assert "quick idea" in turn.reply and turn._decision is not None  # box off: whole-set offer
    ready = SimpleNamespace(
        reply="", request_human=False, _decision=None, _summary=False, awaiting_customer=False
    )
    brain_never_empty(
        ready,
        {
            **context,
            "box_offer": True,
            "noted_problems": [
                {"ref": "a", "since": "x"},
                {"ref": "b", "impact": "y"},
                {"ref": "c"},
            ],
            "brief": {"map_reviewed": True, "ranked": True, "voluntary_problems": 1},
            "history": [{"role": "ai", "text": "Hi"}] * 9,
        },
    )
    assert "quick idea" in ready.reply and ready._decision is not None


@pytest.mark.parametrize(
    "text",
    [
        "seedha batao, time nahi hai",
        "kahin aur jaun",
        "aap log karte kya ho?",
        "mujhe bas batao aap kya bana sakte ho",
        "sub ok hai solution bataye kub say pooch raha hoan?",
    ],
)
def test_the_specs_impatience_and_what_do_you_do_phrases_ask_for_ideas(text: str) -> None:
    assert solution_ask.asked_for_ideas(text)


def test_the_trade_fusion_is_stable_and_leaves_a_confident_detection_alone() -> None:
    from app.modules.pi import industry_overlap, industry_packs

    said = [
        "Carpenter udhaar pe maal le jaate hain aur mahinon nahi dete, lakkar mandi mein yard hain."
    ]
    first = industry_overlap.fuse(industry_packs.detect(said), said)
    again = industry_overlap.fuse(industry_packs.detect(said), said)
    assert first.industries == again.industries and first.scores == again.scores
    strong = ["I run a restaurant. Orders get missed and staff make mistakes."]
    found = industry_packs.detect(strong)
    assert industry_overlap.fuse(found, strong) is found


def test_a_generic_later_reply_does_not_move_the_stored_trade() -> None:
    from types import SimpleNamespace

    from app.modules.pi.service_conversation import industry_context

    customer = SimpleNamespace(industry_primary=None, industry_secondary=[], industry_confidence=0)
    first = "Students book on WhatsApp and cancel an hour before. My instructors sit doing nothing."
    industry_context(customer, [first], latest=first)
    stored = customer.industry_primary
    later = [first, "Yes, it happens every week and I am not sure how much we lose because of it."]
    industry_context(customer, later, latest=later[-1])
    assert customer.industry_primary == stored == "driving_schools"


def test_the_word_real_does_not_name_the_real_estate_trade() -> None:
    from app.modules.pi import industry_packs

    found = industry_packs.detect(["After cleaning, weight drops and I don't know my real cost"])
    assert found.primary != "real_estate_agencies_and_brokers"


def _honest(reply: str, context: dict | None = None) -> list[str]:
    from app.modules.pi import constitution

    ctx = {
        "pi_mode": "brain",
        "flow": {"state": "S5_READINESS"},
        "history": [{"role": "ai", "text": "Hi"}],
    }
    ctx.update(context or {})
    return [v.rule for v in constitution.lint(reply, ctx) if v.rule == "R-HONEST-01"]


def test_a_time_in_advice_to_the_owner_is_not_a_timeline_claim() -> None:
    assert not _honest(
        "Sure.\nFirst, count the unpaid slips from this week, so you see the real size."
    )
    assert not _honest(
        "Doosra, ek hafte tak har ghar ka udhaar alag likhein, taake hisaab saaf ho."
    )
    ideas = {
        "solution_ideas": ["Write every order in one notebook for this week, so none is missed."]
    }
    assert not _honest("Write every order in one notebook for this week, so none is missed.", ideas)


def test_a_time_claim_about_workzap_or_the_document_is_still_refused() -> None:
    assert _honest("Workzap will have the document ready within 3 days.")
    assert _honest("Your quote will be prepared by tomorrow.")
    assert _honest("We can build this in two weeks.")


def test_free_ideas_are_short_and_plain() -> None:
    from app.modules.pi import solution_free

    long_idea = (
        "Walk through the clinic queue and note where people stand longest, so you see the real "
        "bottleneck behind the long waits and the poor reviews your front desk keeps hearing about."
    )
    jargon = "Streamline the way slips are filled in, so staff stop losing time on repeats."
    good = "Note who waits longest at the counter each evening, so you see where the queue builds."
    assert solution_free.vetted([long_idea, jargon, good], "long waits", []) == [good]


@pytest.mark.parametrize(
    "text",
    [
        "tolong kasih solusi",
        "kya aap ye kar sakte ho?",
        "ada ide gak?",
        "راه حل بده",
        "donnez-moi une solution",
        "avez-vous une idée ?",
        "dame una solución",
        "bana bir çözüm ver",
        "gib mir eine Lösung",
        "मुझे समाधान चाहिए",
    ],
)
def test_other_languages_ask_for_ideas(text: str) -> None:
    assert solution_ask.asked_for_ideas(text)


@pytest.mark.parametrize(
    "text",
    [
        "I have no idea why they leave",
        "we sell solar solutions to farms",
        "Nuestra empresa tiene mil clientes en tres ciudades y cada mes perdemos pedidos por una solución",
        "hola",
        "saya punya toko baju online dan pesanan sering keliru",
    ],
)
def test_a_story_or_a_greeting_in_another_language_is_not_an_ask(text: str) -> None:
    assert not solution_ask.asked_for_ideas(text)


@pytest.mark.parametrize(
    "text",
    [
        "sub ok hai solution bataye kub say pooch raha hoan?",
        "kab se pooch raha hoon, jaldi solution dain",
        "I have asked three times, just give me a solution",
        "seedha batao, time nahi hai",
    ],
)
def test_an_impatient_ask_gets_a_short_apology_before_the_ideas(text: str) -> None:
    from app.modules.pi.service_conversation import ideas_opener

    assert solution_ask.impatient(text)
    assert ideas_opener({"latest_customer_message": text}).startswith("Sorry")


def test_a_calm_ask_gets_the_plain_opener_not_an_apology() -> None:
    from app.modules.pi.service_conversation import ideas_opener

    assert (
        ideas_opener({"latest_customer_message": "Solution dain"})
        == "Here are two ideas you can try now:\n"
    )
    assert not solution_ask.impatient("Solution dain")


@pytest.mark.parametrize(
    "text",
    [
        "I want to start a clothing business how to do",
        "how to take first step i am very confuse i'll do first online or onsite",
        "how to start",
        "where do I begin?",
        "what is the first step",
        "kaise shuru karun",
        "kahan se shuru karna chahiye",
        "shuru kaise karein",
        "pehle kya karun",
        "pehla qadam kya hai",
    ],
)
def test_how_do_i_begin_is_an_ask_for_ideas(text: str) -> None:
    assert solution_ask.asked_for_ideas(text)


@pytest.mark.parametrize(
    "text",
    [
        "the first step of our process is the cutting table",
        "we start work at nine and orders begin to pile up",
        "hum subah shuru karte hain aur hisaab gadbad rehta hai",
    ],
)
def test_a_sentence_about_starting_or_a_first_step_is_not_an_ask(text: str) -> None:
    assert not solution_ask.asked_for_ideas(text)


@pytest.mark.parametrize(
    ("said", "thin"),
    [
        ("60 bhainsein", True),
        ("hamari 3 dukaanein hain", True),
        ("restaurant", True),
        ("udhaar", False),
        ("stock khatam ho jata hai", False),
        ("chori ho rahi hai", False),
        ("late delivery", False),
        ("hisaab kitaab copy mein likhta hoon, ghalti ho jati hai", False),
        ("document bhej dein", False),
    ],
)
def test_a_bare_fact_is_not_a_problem_but_a_short_problem_is(said: str, thin: bool) -> None:
    from app.modules.pi import problems

    assert problems.thin_message(said) is thin


def test_a_problem_created_from_a_bare_fact_is_sent_back() -> None:
    from app.modules.pi import problems
    from app.modules.pi.problems import ProblemNote, ProblemOp

    op = ProblemOp(
        op="create",
        note=ProblemNote(
            title="Dairy farm stock management issues",
            user_words=["60 bhainsein"],
            category="stock_inventory",
            confidence=0.9,
        ),
    )
    bad = problems.check_ops([op], set(), True, "60 bhainsein")
    assert bad is not None and "not something they said" in bad
    assert problems.check_ops([op], set(), True, "60 bhainsein hain, doodh kam hai") is None or (
        "not something they said"
        not in (problems.check_ops([op], set(), True, "60 bhainsein hain, doodh kam hai") or "")
    )


def test_a_greeting_keeps_the_chat_language_it_does_not_switch_it() -> None:
    """The owner asked for Roman Urdu; a later plain "hello" must not bring English back."""
    from types import SimpleNamespace

    from app.modules.pi.service_conversation import reply_language

    def msg(body: str) -> SimpleNamespace:
        return SimpleNamespace(body=body, message_type="text", sender_type="customer")

    earlier = [msg("ap kya kr skty hain meir problem mai"), msg("roman urdu ma bt kro")]
    got = reply_language(None, msg("hello"), earlier, None)  # type: ignore[arg-type]
    assert got.get("reply_language") == "roman_ur"
    first = reply_language(None, msg("hello"), [], None)  # type: ignore[arg-type]
    assert first.get("reply_language") == "en"  # nothing earlier: English, the main language


def test_the_returning_greeting_is_in_roman_urdu_for_a_roman_urdu_chat() -> None:
    from app.modules.pi.service_conversation import greeting_reply

    context = {
        "pi_mode": "brain",
        "reply_language": "roman_ur",
        "history": [{"role": "ai", "text": "Hi"}],
        "customer_profile": {"name": "SAW"},
    }
    assert greeting_reply(context) == "Hi SAW. Bataiye, aap ke business mein kya masla hai?"


def test_an_invented_promise_of_an_update_is_replaced_by_the_invitation() -> None:
    from types import SimpleNamespace

    from app.modules.pi.service_conversation import brain_no_early_promise

    turn = SimpleNamespace(
        reply="Ji, yahin chat mein update aayega.",
        request_human=False,
        _decision=None,
        _summary=False,
        awaiting_customer=False,
        problem_ops=[],
    )
    context = {"reply_language": "roman_ur", "flow": {"state": "S1_LISTENING"}}
    brain_no_early_promise(turn, context)
    assert "update aayega" not in turn.reply and "masla" in turn.reply


def test_first_person_verbs_that_carry_a_gender_become_neutral() -> None:
    from app.modules.pi.service_conversation import roman_polish

    out = roman_polish("Main aap ki problem note kar sakta hoon aur bhej dunga.")
    assert "sakta" not in out and "dunga" not in out and "sakte hain" in out and "bhej denge" in out


def test_sol04_a_free_idea_must_use_something_the_person_said_and_generic_ones_are_banned() -> None:
    from app.modules.pi import solution_free

    facts = solution_free.fact_words(
        "Orders get missed on WhatsApp and phone", "Order desk problem"
    )
    specific = "Write each WhatsApp order in one notebook, so none is missed when the phone rings."
    unrelated = "Keep the shelves tidy every morning, so customers find things quickly."
    generic = "Improve your marketing and use social media, so more people hear about orders."
    kept = solution_free.vetted([unrelated, generic, specific], "orders get missed", [], facts)
    assert kept == [specific]
    assert solution_free.vetted([unrelated], "orders get missed", [], set()) == [unrelated]


def test_sol02_the_one_question_is_answered_with_ideas_not_another_question() -> None:
    from types import SimpleNamespace

    from app.modules.pi import solution_context
    from app.modules.pi.service_conversation import asked_without_ideas

    chat = SimpleNamespace(service_brief={}, flow_state="S1_LISTENING")
    solution_context._no_ideas(
        chat, [], None, "nothing_noted", __import__("datetime").datetime.now()
    )
    assert chat.service_brief["open_ask"] is True  # they asked, nothing was noted: one question
    context = {
        "open_ask": True,
        "flow": {"state": "S1_LISTENING"},
        "latest_customer_message": "orders miss hote hain",
    }
    assert asked_without_ideas(context)  # the answer gets ideas
    assert not asked_without_ideas(
        {"flow": {"state": "S1_LISTENING"}, "latest_customer_message": "orders miss hote hain"}
    )


def test_sol03_a_churn_signal_is_logged_on_the_chat() -> None:
    from app.modules.pi import solution_ask

    for said in ("kahin aur jaun?", "rehne do, koi aur dekh leta hoon", "I'll look elsewhere"):
        assert solution_ask.churn_risk(said)


@pytest.mark.parametrize(
    "text",
    [
        "solution ap dw",
        "solution dw",
        "solution dy",
        "ap kya kr skty hain",
        "kya kar skty hain wo btyn",
        "ap kya kr skty hain wo btyn",
        "solution aap dy",
        "idea ap dw",
        "kuch kr skty hain",
        "hal btyn",
    ],
)
def test_heavy_short_roman_urdu_spellings_ask_for_ideas(text: str) -> None:
    assert solution_ask.asked_for_ideas(text)


def test_an_unseen_spelling_with_an_ask_word_goes_to_the_model_check() -> None:
    from app.modules.pi import ask_classifier

    state = "S3_NOTED"
    assert ask_classifier.needed(
        "ap koi hal nikalen is ka", state
    )  # 'hal' with a spelling the banks lack
    assert not ask_classifier.needed("udhaar ka hisaab gadbad hai bhai", state)  # a plain statement


@pytest.mark.parametrize(
    "idea",
    [
        "Pehle, hum dekh sakte hain ke price poochne ke baad reply kahan toot raha hai",
        "Doosra, aap ke Instagram aur WhatsApp flow ko aisa note kiya ja sakta hai ke team ko clear ho jaye",
        "We can review where buyers drop off after the price is asked",
        "Where buyers drop can be analysed, so the team sees it",
    ],
)
def test_an_idea_that_is_not_an_action_for_the_owner_is_refused(idea: str) -> None:
    from app.modules.pi import solution_rules

    assert not solution_rules.is_owner_action(idea)
    assert solution_rules.check_idea(idea).reject


@pytest.mark.parametrize(
    "idea",
    [
        "Price ke saath saaf tasveer aur size chart bhi bhejein, taake dobara poochna na paray.",
        "Send a clear photo and the size chart with the price, so they need not ask again.",
        "Ask staff to message a photo of any shelf running low, so the buyer sees it straight away.",
        "Aap team ko batayein ke kaunsa order pehle jayega, taake koi order na rukay.",
    ],
)
def test_an_action_for_the_owner_is_accepted(idea: str) -> None:
    from app.modules.pi import solution_rules

    assert solution_rules.is_owner_action(idea)


def test_a_reply_whose_idea_lines_are_not_owner_actions_is_dropped_whole() -> None:
    """The live chat: price asked, then silence; pi's two 'ideas' were what Workzap would note."""
    from types import SimpleNamespace

    from app.modules.pi.service_conversation import reject_passive_ideas

    reply = (
        "Haan, is maslay par help ki ja sakti hai.\n"
        "Pehle, hum dekh sakte hain ke price poochne ke baad reply kahan toot raha hai.\n"
        "Doosra, aap ke Instagram aur WhatsApp flow ko aisa note kiya ja sakta hai ke team ko clear ho jaye."
    )
    turn = SimpleNamespace(
        reply=reply, _summary=False, _decision=None, request_human=False, _ideas_rejected=False
    )
    reject_passive_ideas(turn, {})
    assert turn.reply == "" and turn._ideas_rejected is True
    good = SimpleNamespace(
        reply="Ji, ye do ideas abhi aazma sakte hain:\n• Price ke saath saaf tasveer bhi bhejein, taake dobara poochna na paray.",
        _summary=False,
        _decision=None,
        request_human=False,
        _ideas_rejected=False,
    )
    reject_passive_ideas(good, {})
    assert good.reply and good._ideas_rejected is False
