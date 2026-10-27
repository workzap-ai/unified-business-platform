# ruff: noqa: E501
"""Platform spec v1.4, Part 16: the opening warm-up (OT1, OT2, OT3, OT8, OT12) and its quick look."""

from dataclasses import asdict

from app.modules.pi import business_profile as bp
from app.modules.pi import public_page, warmup


def ctx(said="Hi", brief=None, language="en", greeting=None, **over):
    base = {
        "warmup": {"enabled": True},
        "latest_customer_message": said,
        "greeting_only": said.strip().lower() in {"hi", "hello", "salam", "hi pi"}
        if greeting is None
        else greeting,
        "brief": brief or {},
        "reply_language": language,
    }
    return {**base, **over}


def test_it_is_off_unless_the_flag_is_true() -> None:
    assert warmup.enabled({"brain": {"warmup": True}})
    assert not warmup.enabled({"brain": {}}) and not warmup.enabled(None)
    assert warmup.plan({"latest_customer_message": "Hi"}) is None


def test_hi_gets_the_ai_line_and_one_identity_question() -> None:  # OT1, OT2
    plan = warmup.plan(ctx("Hi"))
    assert plan is not None and "an AI from Workzap" in plan.reply
    assert "English" not in plan.reply and "Urdu" not in plan.reply  # no language offer (owner)
    assert plan.reply.count("?") == 1
    assert plan.state["step"] == warmup.IDENTITY_ASKED
    roman = warmup.plan(ctx("Hi", language="roman_ur"))
    assert roman is not None and "Workzap ka AI" in roman.reply and roman.reply.count("?") == 1


def test_a_second_hi_is_not_the_answer_the_identity_question_is_asked_again() -> None:
    brief = {"warmup": {"step": warmup.IDENTITY_ASKED, "asked": 1}}
    plan = warmup.plan(ctx("Hi", brief))
    assert plan is not None and plan.reply == warmup.IDENTITY["en"]
    assert plan.state["step"] == warmup.IDENTITY_ASKED
    assert bp.grounded(plan.profile) == {}  # "Hi" is not kept as what the business does


def test_a_hurried_owner_gets_no_warmup_and_it_is_remembered() -> None:  # OT3
    plan = warmup.plan(ctx("bas mera masla ye hai ke stock kam hota hai"))
    assert plan is not None and plan.reply == "" and plan.state["step"] == warmup.SKIPPED
    plan = warmup.plan(ctx("what can you do for my shop?", greeting=False))
    assert plan is not None and plan.reply == "" and plan.state["step"] == warmup.SKIPPED
    assert warmup.plan(ctx("thanks", {"warmup": {"step": warmup.SKIPPED}})) is None


def test_the_identity_answer_gets_the_one_page_ask() -> None:
    brief = {"warmup": {"step": warmup.IDENTITY_ASKED, "asked": 1}}
    plan = warmup.plan(ctx("mera clothing brand hai, baby aur male clothes", brief))
    assert plan is not None and "link" in plan.reply.lower() and "public" in plan.reply.lower()
    assert plan.state["step"] == warmup.PAGE_ASKED
    assert bp.grounded(plan.profile)["what_they_do"].startswith("mera clothing brand")


def test_an_identity_answer_that_states_a_problem_ends_the_warmup() -> None:
    brief = {"warmup": {"step": warmup.IDENTITY_ASKED}}
    plan = warmup.plan(ctx("kapre ka kaam hai, stock bohat pada hai", brief))
    assert plan is not None and plan.reply == "" and plan.state["step"] == warmup.SKIPPED


def test_a_link_in_the_identity_answer_asks_for_the_quick_look() -> None:
    brief = {"warmup": {"step": warmup.IDENTITY_ASKED}}
    plan = warmup.plan(ctx("Ata Clothing, baby clothes https://ata.example", brief))
    assert plan is not None and plan.ask_page == "https://ata.example" and plan.reply == ""


def test_no_website_continues_and_never_asks_again() -> None:  # OT8, OT12
    brief = {"warmup": {"step": warmup.PAGE_ASKED}}
    plan = warmup.plan(ctx("website nahi hai", brief, language="roman_ur"))
    assert plan is not None and plan.reply.startswith("Theek hai.") and "bhaari" in plan.reply
    assert plan.state["step"] == warmup.DONE
    assert bp.grounded(plan.profile)["website"] == "none"
    assert (
        "website" not in plan.reply.lower()
        or "nahi" not in plan.reply.lower().split("theek hai.")[1]
    )
    assert warmup.plan(ctx("kuch bhi", {"warmup": plan.state})) is None


def test_declining_the_link_is_fine() -> None:  # OT12
    brief = {"warmup": {"step": warmup.PAGE_ASKED}}
    plan = warmup.plan(ctx("rehne dein", brief))
    assert plan is not None and plan.state["step"] == warmup.DONE and "?" in plan.reply
    assert plan.reply.count("?") == 1


def look(**fields):
    result = public_page.PageResult(
        "ok",
        "https://ata.example/",
        title="Ata Clothing | Baby and Men",
        site_name="Ata Clothing",
        description="Baby and men's clothes, outlets in Lahore",
        orders_online=True,
        **fields,
    )
    return {k: v for k, v in asdict(result).items() if k != "text"}


def test_a_good_page_is_said_back_once_labelled_then_the_door() -> None:
    brief = {"warmup": {"step": warmup.PAGE_ASKED}}
    plan = warmup.plan(ctx("https://ata.example", brief, page_look=look()))
    assert plan is not None and plan.reply.startswith("From your page I understood:")
    assert plan.reply.endswith("what feels heaviest in your business these days?")
    assert plan.reply.count("?") == 1 and plan.state["step"] == warmup.DONE
    assert bp.grounded(plan.profile).get("business_name") is None  # provisional until confirmed


def test_a_page_that_cannot_be_read_is_said_calmly() -> None:  # OT7, OT9, OT10
    brief = {"warmup": {"step": warmup.PAGE_ASKED}}
    for status, expect in (
        ("failed", "won't open"),
        ("needs_screenshot", "screenshot"),
        ("refused", "business pages"),
    ):
        bad = {"status": status, "url": "https://x.example", "reason": "x"}
        plan = warmup.plan(ctx("https://x.example", brief, page_look=bad))
        assert plan is not None and expect in plan.reply and plan.reply.count("?") == 1
