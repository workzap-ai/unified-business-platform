# ruff: noqa: E501
"""The thinking checks of spec 3.9, their wiring behind response_rules.brain.thinking, and the
prompt block."""

from typing import Any

from app.modules.pi import constitution, service_conversation, think_lint, think_prompt


def ctx(
    history: list[tuple[str, str]] | None = None, latest: str = "", **extra: Any
) -> dict[str, Any]:
    rows = [{"role": r, "text": t} for r, t in history or []]
    return {"history": rows, "latest_customer_message": latest, **extra}


def rules(reply: str, context: dict[str, Any]) -> set[str]:
    return {f.rule for f in think_lint.think_flags(reply, context)}


RESTAURANT_BAD = [
    ("customer", "Khana kabhi achha kabhi kharab"),
    ("ai", "Kaun si branch?"),
    ("customer", "Tipu Sultan."),
    ("ai", "Kitne cooks hain?"),
    ("customer", "char."),
]
RESTAURANT_GOOD = (
    "“Kabhi achha kabhi kharab” matlab masla khane ka nahi, ek jaisa na hone ka lagta hai. Ye aksar tab hota hai jab "
    "recipe ya maal ek ho magar banane wala ya waqt badal jaye. Kya kharabi kisi khaas din, shift ya dish ke saath aati hai?"
)


def test_q_streak_flags_the_interview_style_of_the_spec() -> None:
    assert "T-QSTREAK-01" in rules("Is mein se kya masla hai?", ctx(RESTAURANT_BAD, "char."))


def test_q_streak_passes_the_thinking_style_reply() -> None:
    assert "T-QSTREAK-01" not in rules(RESTAURANT_GOOD, ctx(RESTAURANT_BAD, "char."))


def test_q_streak_needs_two_question_only_messages_in_the_last_three() -> None:
    history = [
        ("ai", "Kaun si branch?"),
        ("customer", "DHA"),
        ("ai", "Is par maal ka hissa purana ho jata hai, to 3 crore ka dabao banta hai."),
        ("customer", "haan"),
    ]
    # the bare question two messages back is the only one in the last three besides this: that is two
    assert "T-QSTREAK-01" in rules("Kitne cooks hain?", ctx(history, "haan"))
    # a question that gives something is not a bare one
    gives = "Ye 3 crore ka dabao hai, to ruka maal paisa bhi rokta hai. Kya cash ki tangi is se juri hai?"
    assert "T-QSTREAK-01" not in rules(gives, ctx(history, "haan"))
    assert "T-QSTREAK-01" not in rules("Kitne cooks hain?", ctx(history[2:], "haan"))


def test_a_fork_counts_as_giving_something() -> None:
    assert think_lint.adds_something("Pehle maal par baat karein, ya pehle cash ki tangi par?")
    assert not think_lint.adds_something("Kaun si branch?")
    assert think_lint.adds_something("Aadha maal pichle saal ka hai, to 3 crore dabao mein hai.")
    assert think_lint.adds_something("Dekhein https://workzap.ai/x")


def test_no_insight_flags_a_bare_question_and_passes_a_reading() -> None:
    assert "T-INSIGHT-01" in rules("Kaun si branch?", ctx(latest="Khana kabhi achha kabhi kharab"))
    assert "T-INSIGHT-01" not in rules(
        RESTAURANT_GOOD, ctx(latest="Khana kabhi achha kabhi kharab")
    )
    assert "T-INSIGHT-01" not in rules(
        "Theek hai.", ctx(latest="ok")
    )  # the application's own short line


def test_echo_flags_a_first_sentence_that_repeats_the_owner() -> None:
    latest = "mera clothing brand hai mere baby and male cloths hain 6crore ka stock wo bechna hai"
    echoing = "Aap ka clothing brand hai, baby and male cloths hain, 6crore ka stock bechna hai. Ye cost ki raqam hai ya qeemat ki?"
    assert "T-ECHO-01" in rules(echoing, ctx(latest=latest))
    spec = "6 crore ka stock bohat bara hissa hota hai, aur wo jitna pada rehta hai utna hi bhaari hota jata hai. Ye 6 crore cost ki raqam hai ya bechne ki qeemat ki?"
    assert "T-ECHO-01" not in rules(spec, ctx(latest=latest))


def test_filler_questions_are_flagged_outside_a_check_in() -> None:
    for filler in (
        "Kuch aur?",
        "Anything else?",
        "Aur kya masla hai?",
        "Is anything else getting in the way?",
    ):
        assert "T-FILLER-01" in rules(
            f"Maal ruk gaya hai, ye samajh aaya. {filler}", ctx(latest="x")
        ), filler
    assert "T-FILLER-01" not in rules(
        "Maal ruk gaya hai, ye samajh aaya. Kuch aur?", ctx(latest="x", check_in=True)
    )


def test_a_specific_door_is_not_filler() -> None:
    specific = "Is ke saath aur kahan kheench-tan lagti hai: paisa wapas aane mein, staff mein, ya customers mein?"
    assert "T-FILLER-01" not in rules(specific, ctx(latest="x"))


def test_unproved_claim_flags_a_guess_stated_as_fact() -> None:
    history = [("customer", "maal nahi bik raha")]
    assert "T-CLAIM-01" in rules(
        "Maal nahi bik raha ki wajah design ka purana hona hai.", ctx(history, "maal nahi bik raha")
    )
    assert "T-CLAIM-01" in rules(
        "The reason is that your prices are too high.", ctx(history, "stock")
    )


def test_unproved_claim_passes_a_humble_hypothesis_and_a_confirmed_one() -> None:
    history = [("customer", "maal nahi bik raha")]
    humble = "Meri ek soch hai, galat bhi ho sakti hai: wajah design ka purana hona lagta hai."
    assert "T-CLAIM-01" not in rules(humble, ctx(history, "maal nahi bik raha"))
    assert "T-CLAIM-01" in rules("Wajah design ka purana hona hai.", ctx(history, "x"))
    assert "T-CLAIM-01" not in rules(
        "Wajah design ka purana hona hai.", ctx(history, "x", hypothesis_confirmed=True)
    )
    owner_said = "Aap ne kaha qeemat zyada hai isliye nahi bik raha."
    assert "T-CLAIM-01" not in rules(
        owner_said, ctx([("customer", "qeemat zyada hai isliye nahi bik raha")], "x")
    )


def test_forecast_flags_a_future_number_the_owner_did_not_give() -> None:
    history = [("customer", "6crore ka stock hai aur 30% sale lagayi thi")]
    assert "T-FORECAST-01" in rules("Aap ko 40 lakh ka nuqsan hoga.", ctx(history, "x"))
    assert "T-FORECAST-01" in rules("You will lose 25 lakh by next year.", ctx(history, "x"))


def test_forecast_allows_working_their_own_numbers() -> None:
    history = [
        ("customer", "6crore ka stock hai"),
        ("customer", "taqreeban aadha pichle saal ka hai"),
    ]
    assert "T-FORECAST-01" not in rules(
        "Isi raftar par 3 crore aur purana ho jaye ga.", ctx(history, "x")
    )
    assert "T-FORECAST-01" not in rules(
        "Aadha maal pichle saal ka hai, to taqreeban 3 crore sab se zyada dabao mein hai.",
        ctx(history, "x"),
    )
    assert "T-FORECAST-01" not in rules(
        "Agar ye 6 crore ruke rahe to paisa phansa rahe ga.", ctx(history, "x")
    )


def test_move_repeat_flags_three_of_four() -> None:
    rows = [
        {"role": "ai", "text": "x", "move": "M1_reflect"},
        {"role": "ai", "text": "y", "move": "M3_reframe"},
        {"role": "ai", "text": "z", "move": "M1_reflect"},
    ]
    context = {"history": rows, "latest_customer_message": "ok", "plan": {"move": "M1_reflect"}}
    assert "T-REPEAT-01" in rules(
        "Ye sunna aasaan nahi ke maal ruka hai aur paisa phansa hai.", context
    )
    context["plan"] = {"move": "M11_prioritise"}
    assert "T-REPEAT-01" not in rules(
        "Ye sunna aasaan nahi ke maal ruka hai aur paisa phansa hai.", context
    )
    assert "T-REPEAT-01" not in rules(
        "Ye sunna aasaan nahi ke maal ruka hai.", ctx()
    )  # no moves known: nothing to flag


# --- every pi reply in spec 8.1 chat 3 and 3.10 passes all seven checks -------------------------

CHAT3 = [
    (
        "mera clothing brand hai mere baby and male cloths hain 6crore ka stock wo bechna hai",
        "6 crore ka stock bohat bara hissa hota hai, aur wo jitna pada rehta hai utna hi bhaari hota jata hai. Ye 6 crore cost ki raqam hai ya bechne ki qeemat ki?",
    ),
    (
        "warehouse and outlets, dono jagah. poore sets hain. lagbhag aik saal se",
        "Poore sets hain aur saal bhar se pada hai, to size ka masla nahi lagta. Kuch aur cheez maal ko rok rahi hai. Aap ke khayal mein ye kyun nahi bik raha: mausam, qeemat, pasand, ya logon ko pata hi nahi?",
    ),
    (
        "qeemat zyada hai shayad, aur design purane ho gaye",
        "Ye do alag masle hain: qeemat ek cheez hai, aur design ka purana hona doosri. Aap ne ab tak kuch kam qeemat par ya sale mein rakha hai?",
    ),
    (
        "haan taqreeban aadha pichle saal ka hai",
        "To taqreeban 3 crore sab se zyada dabao mein hai. Kya outlets mein se kisi jagah ye maal doosron se behtar bikta hai?",
    ),
    (
        "haan bohat. suppliers ko payment late hoti hai aur kabhi kabhi salary bhi",
        "Ye sunna aasaan nahi ke ruke hue maal ki wajah se baat supplier aur salary tak pohanch jaye. Shukriya ke aap ne ye bataya. Supplier aur salary mein se pehle kis ke saath masla aata hai?",
    ),
]


def test_the_specs_own_replies_pass_the_thinking_checks() -> None:
    history: list[tuple[str, str]] = [("customer", "mera clothing brand hai 6crore ka stock hai")]
    for said, reply in CHAT3:
        flags = rules(reply, ctx(history, said))
        assert flags == set(), (reply, flags)
        history += [("customer", said), ("ai", reply)]


def test_spec_3_10_clinic_and_logistics_replies_pass() -> None:
    clinic = "Ye khali slot sirf paisa nahi, doctor ka waqt bhi zaya karta hai. Aap ne dekha hai kin ka nahi aana zyada hota hai: naye patients ka ya purane ka?"
    logistics = "Late delivery ka asar sirf customer par nahi, agli gaari ki tayyari par bhi parta hai. Ye der kahan se shuru hoti hai: maal lagane mein, raaste mein, ya customer ke paas pohanchne par?"
    assert rules(clinic, ctx(latest="Patients appointment par nahi aate")) == set()
    assert rules(logistics, ctx(latest="Delivery late hoti hai")) == set()


# --- wiring: soft, and only behind response_rules.brain.thinking ---------------------------------


def _violations(reply: str, thinking: bool) -> list[constitution.Violation]:
    context = ctx(RESTAURANT_BAD, "char.")
    if thinking:
        context["thinking"] = True
    return constitution.lint(reply, context)


def test_constitution_runs_the_checks_only_when_thinking_is_on() -> None:
    off = _violations("Is mein se kya masla hai?", False)
    on = _violations("Is mein se kya masla hai?", True)
    assert not [v for v in off if v.rule.startswith("T-")]
    added = [v for v in on if v.rule.startswith("T-")]
    assert {v.rule for v in added} >= {"T-QSTREAK-01", "T-INSIGHT-01"}
    assert not any(v.hard for v in added)  # soft only: never blocks a reply on its own
    assert constitution.hard(on) == constitution.hard(off)
    assert [v for v in on if not v.rule.startswith("T-")] == off


def test_thinking_flag_is_on_only_when_exactly_true() -> None:
    assert think_prompt.enabled({"brain": {"thinking": True}})
    for rules_ in (
        None,
        {},
        {"brain": {}},
        {"brain": {"thinking": False}},
        {"brain": {"thinking": "true"}},
        {"brain": {"thinking": 1}},
    ):
        assert not think_prompt.enabled(rules_)


def test_the_prompt_is_unchanged_unless_thinking_is_on() -> None:
    base = {"pi_mode": "brain"}
    plain = service_conversation.system_for(base)
    on = service_conversation.system_for(
        {**base, "thinking": True, "latest_customer_message": "ok", "history": []}
    )
    assert on.startswith(plain) and len(on) > len(plain)
    assert think_prompt.block(base) == ""
    assert service_conversation.system_for({**base, "thinking": False}) == plain
    assert service_conversation.system_for({}) == service_conversation.SYSTEM  # other workspaces


def test_the_prompt_block_carries_the_loop_the_moves_and_the_variety_rules() -> None:
    text = think_prompt.block(
        {"thinking": True, "latest_customer_message": "kitna lagega", "history": []}
    )
    for needle in (
        "so-what",
        "M1_reflect",
        "M16_hold_space",
        "No move more than twice",
        "Never two question-only",
        "Fatigue wins",
        "only the owner confirms",
        "British spelling",
        "Dials for this conversation",
    ):
        assert needle.lower() in text.lower(), needle
    assert "mode buy" in text
    assert "Workzap" in text and "Artwing" not in text


def test_the_prompt_block_reports_the_dials_and_the_streak_rule() -> None:
    history = [
        ("customer", "Khana kabhi achha kabhi kharab"),
        ("ai", "Kaun si branch?"),
        ("customer", "DHA"),
        ("ai", "Kitne cooks hain?"),
    ]
    text = think_prompt.block(ctx(history, "char", thinking=True))
    assert "ended in a question: this one carries no question" in text
    assert "only a question: this one must give something first" in text
