# ruff: noqa: E501
"""The expert advisor (response_rules.brain.solution_source = "expert"): diagnose, judge, vet.
The model is scripted; nothing here calls a real one."""

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import pytest

from app.modules.pi import constitution, expert_advisor, idea_filter, policy, solution_context
from app.shared.errors import BusinessRuleViolation

pytestmark = pytest.mark.asyncio

SHOWROOM = "I run a car showroom and fewer people walk in than before, footfall is low"
VIDEO_IDEA = (
    "Pin a short video of your best cars on your page, so people stop and look at the showroom."
)
GOOD_ONE = "Ask each recent buyer how they first heard of the showroom, so you see which way people really find you."
GOOD_TWO = "Stand outside the showroom as a passer-by would and note what you see first, so you spot what keeps people walking past."
GOOD_THREE = "Ask the sales staff what walk-in visitors say about the showroom when they leave, so the reasons for low footfall show up."
QUESTION = "Has footfall dropped everywhere, or only since a new showroom opened nearby?"


def diag(ideas: list[str | dict[str, Any]], question: str = QUESTION) -> str:
    return json.dumps(
        {
            "problem": "fewer people walk into the showroom",
            "causes": [
                {
                    "cause": "people do not know the showroom exists",
                    "evidence_for": ["fewer people walk in"],
                    "evidence_against": [],
                },
                {"cause": "competitor nearby", "evidence_for": [], "evidence_against": []},
            ],
            "missing_fact": "whether footfall fell everywhere",
            "question": question,
            "ideas": [
                i
                if isinstance(i, dict)
                else {
                    "idea": i,
                    "addresses": "awareness",
                    "assumes": ["showroom"],
                    "current_practice": "ask buyers how they found you",
                }
                for i in ideas
            ],
        }
    )


class Scripted:
    """complete() answers by purpose and records the calls."""

    def __init__(self, diagnose: str | Exception, judge: str | Exception = "") -> None:
        self.answers = {"pi_expert_diag": diagnose, "pi_expert_judge": judge}
        self.calls: list[str] = []
        self.users: dict[str, str] = {}

    async def complete(self, scope: object, **kwargs: Any) -> SimpleNamespace:
        purpose = kwargs["purpose"]
        self.calls.append(purpose)
        self.users[purpose] = kwargs["messages"][-1].text()
        answer = self.answers[purpose]
        if isinstance(answer, Exception):
            raise answer
        return SimpleNamespace(text=answer)


async def advise(model: Scripted, **extra: Any) -> expert_advisor.Advice | None:
    args: dict[str, Any] = {
        "alias": "pi_brain",
        "conversation_id": None,
        "owner_said": [SHOWROOM, "give me a solution"],
        "problems": ["Few walk-ins at the showroom"],
        "industry": "Car showroom",
        "today": "27 October 2026",
    }
    args.update(extra)
    return await expert_advisor.advise(model, None, **args)  # type: ignore[arg-type]


def judge_of(*rows: tuple[int, int], best: list[int]) -> str:
    """rows: (index, the same score for every quality)."""
    return json.dumps(
        {
            "scores": [{"i": i, **{q: s for q in expert_advisor.QUALITIES}} for i, s in rows],
            "best": [{"i": i, "reason": "fits"} for i in best],
        }
    )


# --- stage 1 -----------------------------------------------------------------------------------


async def test_the_diagnosis_parser_is_tolerant_and_never_raises() -> None:
    fenced = "Here you go:\n```json\n" + diag([GOOD_ONE]) + "\n```"
    parsed = expert_advisor.parse_diagnosis(fenced)
    assert parsed is not None and parsed.candidates[0].idea == GOOD_ONE
    assert [c.cause for c in parsed.causes][0].startswith("people do not know")
    assert expert_advisor.parse_diagnosis("sorry, I cannot") is None
    assert expert_advisor.parse_diagnosis("{}") is None
    assert expert_advisor.parse_diagnosis("[1, 2]") is None


async def test_the_diagnose_call_is_told_the_date_the_industry_and_the_owners_words() -> None:
    model = Scripted(diag([GOOD_ONE, GOOD_TWO]), judge_of((0, 5), (1, 5), best=[0, 1]))
    await advise(model, country="Pakistan", subtype="footfall_low")
    sent = json.loads(model.users["pi_expert_diag"])
    assert sent["today"] == "27 October 2026" and sent["industry"] == "Car showroom"
    assert sent["country"] == "Pakistan" and "footfall" in sent["owner_first_message"]


async def test_bad_json_returns_none_so_the_caller_falls_back() -> None:
    assert await advise(Scripted("not json at all")) is None


async def test_a_model_error_or_a_timeout_returns_none() -> None:
    assert await advise(Scripted(RuntimeError("provider down"))) is None

    class Slow(Scripted):
        async def complete(self, scope: object, **kwargs: Any) -> SimpleNamespace:
            await asyncio.sleep(1)
            return SimpleNamespace(text=diag([GOOD_ONE]))

    assert await advise(Slow(""), time_limit=0.05) is None


# --- stage 2 -----------------------------------------------------------------------------------


async def test_the_judge_picks_the_best_two_and_drops_candidates_that_score_low() -> None:
    low = json.dumps(
        {
            "scores": [
                {
                    "i": 0,
                    "fits": 5,
                    "correct": 5,
                    "current": 1,
                    "grounded": 5,
                    "specific": 5,
                    "safe": 5,
                },
                {
                    "i": 1,
                    "fits": 4,
                    "correct": 4,
                    "current": 4,
                    "grounded": 4,
                    "specific": 4,
                    "safe": 4,
                },
                {
                    "i": 2,
                    "fits": 5,
                    "correct": 5,
                    "current": 5,
                    "grounded": 5,
                    "specific": 5,
                    "safe": 5,
                },
            ],
            "best": [{"i": 2, "reason": "best"}, {"i": 1, "reason": "ok"}],
        }
    )
    model = Scripted(diag([GOOD_ONE, GOOD_TWO, GOOD_THREE]), low)
    advice = await advise(model)
    assert advice is not None and advice.judged
    # candidate 0 is outdated (current 1): out; the judge's picks come first
    assert advice.ideas == [GOOD_THREE, GOOD_TWO]
    assert model.calls == ["pi_expert_diag", "pi_expert_judge"]


async def test_judge_off_skips_the_judge_call_and_keeps_the_order_proposed() -> None:
    model = Scripted(diag([GOOD_ONE, GOOD_TWO, GOOD_THREE]))
    advice = await advise(model, use_judge=False)
    assert advice is not None and not advice.judged
    assert advice.ideas == [GOOD_ONE, GOOD_TWO]
    assert model.calls == ["pi_expert_diag"]


async def test_an_unusable_judge_answer_falls_back_to_the_proposed_order() -> None:
    model = Scripted(diag([GOOD_ONE, GOOD_TWO]), "I think the first one")
    advice = await advise(model)
    assert advice is not None and not advice.judged and advice.ideas == [GOOD_ONE, GOOD_TWO]
    model = Scripted(diag([GOOD_ONE, GOOD_TWO]), RuntimeError("judge down"))
    advice = await advise(model)
    assert advice is not None and advice.ideas == [GOOD_ONE, GOOD_TWO]


async def test_an_unsafe_candidate_never_reaches_the_owner() -> None:
    rows = json.dumps(
        {
            "scores": [
                {
                    "i": 0,
                    "fits": 5,
                    "correct": 5,
                    "current": 5,
                    "grounded": 5,
                    "specific": 5,
                    "safe": 2,
                },
                {
                    "i": 1,
                    "fits": 4,
                    "correct": 4,
                    "current": 4,
                    "grounded": 4,
                    "specific": 4,
                    "safe": 5,
                },
            ],
            "best": [{"i": 0, "reason": "x"}],
        }
    )
    advice = await advise(Scripted(diag([GOOD_ONE, GOOD_TWO]), rows))
    assert advice is not None and advice.ideas == [GOOD_TWO]


# --- stage 3 -----------------------------------------------------------------------------------


async def test_vetting_drops_an_invented_channel_and_takes_the_next_best() -> None:
    """The car showroom owner never said video or page: the video idea goes (G2), the judge's
    favourite or not."""
    scores = judge_of((0, 5), (1, 4), (2, 4), best=[0, 1])
    model = Scripted(diag([VIDEO_IDEA, GOOD_ONE, GOOD_TWO]), scores)
    advice = await advise(model)
    assert advice is not None
    assert VIDEO_IDEA not in advice.ideas
    assert advice.ideas == [GOOD_ONE, GOOD_TWO]
    assert not any("video" in i.lower() or "page" in i.lower() for i in advice.ideas)


async def test_when_the_owner_did_name_videos_a_video_idea_is_allowed() -> None:
    said = [SHOWROOM + ". We post a video of each car on our page", "solution do"]
    advice = await advise(Scripted(diag([VIDEO_IDEA, GOOD_ONE]), ""), owner_said=said)
    assert advice is not None and advice.ideas[0].startswith("Pin a short video")


async def test_the_guards_drop_timelines_digits_questions_and_tool_words() -> None:
    bad = [
        "Ask each recent buyer how they found the showroom, so you see the real reason this week.",
        "Count 20 walk-ins at the showroom door, so you know how many people really come in.",
        "Ask staff why people leave the showroom, so you learn more?",
        "Put the showroom visitors in a spreadsheet, so you see which way people find you.",
        "Optimise the showroom workflow to leverage every touchpoint, so more people stop.",
    ]
    advice = await advise(Scripted(diag([*bad, GOOD_ONE])), use_judge=False)
    assert advice is not None and advice.ideas == [GOOD_ONE]


async def test_fewer_than_two_survivors_returns_them_with_the_missing_fact_question() -> None:
    advice = await advise(Scripted(diag([VIDEO_IDEA, GOOD_ONE])), use_judge=False)
    assert advice is not None and advice.ideas == [GOOD_ONE]
    assert advice.question == QUESTION and expert_advisor.question_ok(advice.question)


async def test_no_survivor_returns_only_the_missing_fact_question() -> None:
    advice = await advise(Scripted(diag([VIDEO_IDEA])), use_judge=False)
    assert advice is not None and advice.ideas == [] and advice.question == QUESTION
    reply = expert_advisor.need_fact_reply(advice.question)
    assert reply.endswith("?") and reply.count("?") == 1
    low = reply.lower()
    assert not any(w in low for w in ("solution", "idea", "quote", "document", "offer", "price"))


async def test_a_bad_question_is_dropped_not_sent() -> None:
    for bad in (
        "Do you want a solution document and a quote?",
        "Tell me more.",
        "What is your revenue, and who follows up? Also what do you pay staff?",
        "x " * 40 + "?",
    ):
        assert not expert_advisor.question_ok(bad)
        advice = await advise(Scripted(diag([VIDEO_IDEA], question=bad)), use_judge=False)
        assert advice is not None and advice.question == ""


async def test_the_cap_is_respected_whatever_the_model_proposes() -> None:
    model = Scripted(diag([GOOD_ONE, GOOD_TWO, GOOD_THREE]))
    one = await advise(model, use_judge=False, want=1)
    assert one is not None and one.ideas == [GOOD_ONE]
    none = await advise(model, use_judge=False, want=0)
    assert none is not None and none.ideas == []


async def test_a_diagnosis_only_call_gives_causes_and_a_question_and_no_judge() -> None:
    model = Scripted(diag([GOOD_ONE, GOOD_TWO]))
    advice = await advise(model, ideas_wanted=False)
    assert advice is not None and advice.ideas == [] and advice.causes[0].startswith("people")
    assert model.calls == ["pi_expert_diag"]


async def test_a_pack_example_that_assumes_a_channel_is_never_shown_to_the_model() -> None:
    packs = [VIDEO_IDEA, "Instagram reels of each car, so buyers see the stock.", GOOD_ONE]
    model = Scripted(diag([GOOD_ONE, GOOD_TWO]))
    await advise(model, entry_ideas=packs, use_judge=False)
    shown = json.loads(model.users["pi_expert_diag"])["examples_of_level_not_to_copy"]
    assert shown == [GOOD_ONE]


# --- the flag, the cache, the question -----------------------------------------------------------


async def test_the_flag_defaults_to_off_and_the_validator_knows_it() -> None:
    assert not expert_advisor.switched_on({"pi_mode": "brain"})
    assert not expert_advisor.switched_on(
        {"pi_mode": "brain", "brain": {"solution_source": "packs_first"}}
    )
    assert not expert_advisor.switched_on(
        {"brain": {"solution_source": "expert"}}
    )  # not brain mode
    assert expert_advisor.switched_on({"pi_mode": "brain", "brain": {"solution_source": "expert"}})
    assert expert_advisor.judge_on({}) and not expert_advisor.judge_on(
        {"brain": {"expert_judge": False}}
    )
    base = {
        "language": "auto",
        "service_mode": "auto",
        "pi_mode": "brain",
        "tone": "friendly",
        "greeting": "",
        "sign_off": "",
    }
    policy.validate_section(
        "response_rules", {**base, "brain": {"solution_source": "expert", "expert_judge": False}}
    )
    for bad in ({"solution_source": "other"}, {"expert_judge": "no"}, {"solution_source": 1}):
        with pytest.raises(BusinessRuleViolation):
            policy.validate_section("response_rules", {**base, "brain": bad})


NOTED = [
    {
        "ref": "p1",
        "title": "Few walk-ins at the showroom",
        "user_words": ["footfall is low"],
        "cause": "",
    },
    {
        "ref": "p2",
        "title": "Sales team tracking is manual",
        "user_words": [],
        "cause": "",
        "score": 2.0,
    },
]


async def test_the_main_problem_is_the_ranked_then_the_most_severe_then_the_latest() -> None:
    assert expert_advisor.main_problem([]) is None
    assert expert_advisor.main_problem([{"title": "a"}, {"title": "b"}])["title"] == "b"  # type: ignore[index]
    assert expert_advisor.main_problem(NOTED)["ref"] == "p2"  # type: ignore[index]
    ranked_first = [{**NOTED[0], "rank": 1}, {**NOTED[1], "rank": 2}]
    assert expert_advisor.main_problem(ranked_first)["ref"] == "p1"  # type: ignore[index]


async def test_the_diagnosis_is_cached_and_refreshed_when_the_problem_or_a_fact_changes() -> None:
    advice = expert_advisor.Advice(causes=["people do not know"], question=QUESTION, problem="p")
    brief = expert_advisor.remember({}, NOTED[0], advice)
    assert expert_advisor.cached(brief, [NOTED[0]]) is not None
    ctx = expert_advisor.question_context(brief, [NOTED[0]])
    assert ctx["main_problem_causes"] == ["people do not know"]
    assert ctx["suggested_next_question"] == QUESTION
    # a new fact on the problem: stale, no stale question is handed to the prompt
    richer = {**NOTED[0], "user_words": ["footfall is low", "a new showroom opened nearby"]}
    assert expert_advisor.cached(brief, [richer]) is None
    assert "suggested_next_question" not in expert_advisor.question_context(brief, [richer])
    # a different main problem: stale too
    assert expert_advisor.cached(brief, NOTED) is None
    assert expert_advisor.remember({"a": 1}, None, advice) == {"a": 1}


async def test_ideas_are_counted_per_problem() -> None:
    brief = expert_advisor.record_given({}, NOTED[0], 2)
    assert expert_advisor.given_for(brief, NOTED[0]) == 2
    assert expert_advisor.given_for(brief, NOTED[1]) == 0
    assert expert_advisor.given_for({}, None) == 0


# --- R-ASK-08 ---------------------------------------------------------------------------------


def ask_context(**extra: Any) -> dict[str, Any]:
    return {
        "pi_mode": "brain",
        "flow": {"state": "S2_CLARIFYING"},
        "reply_language": "en",
        "history": [{"role": "ai", "text": "Hi, I'm pi, an AI from Workzap."}],
        "latest_customer_message": "footfall is low and fewer people walk in",
        "main_problem": "Few walk-ins at the showroom",
        "main_problem_words": "footfall is low",
        "main_problem_causes": ["people do not know the showroom", "competitor nearby"],
        **extra,
    }


def rules_of(reply: str, context: dict[str, Any]) -> set[str]:
    return {v.rule for v in constitution.lint(reply, context)}


async def test_r_ask_08_fires_on_a_question_about_an_adjacent_process_only_with_the_expert_on() -> (
    None
):
    adjacent = "Noted. Who follows up the enquiries once they come in?"
    assert "R-ASK-08" in rules_of(adjacent, ask_context())
    off = ask_context()
    for key in ("main_problem", "main_problem_words", "main_problem_causes"):
        off.pop(key)
    assert "R-ASK-08" not in rules_of(adjacent, off)  # expert off: unchanged


async def test_r_ask_08_is_quiet_when_the_question_is_about_the_problem_or_a_cause() -> None:
    about_problem = "Noted. Has footfall been low for the whole showroom or only on some days?"
    about_cause = "Noted. Do people nearby know the showroom exists?"
    for reply in (about_problem, about_cause):
        assert "R-ASK-08" not in rules_of(reply, ask_context())
    # a short or generic question is not judged here
    assert "R-ASK-08" not in rules_of("Noted. Anything else?", ask_context())


# --- solution_context holds the packs back in expert mode ---------------------------------------


def conversation(state: str = "S5_READINESS", brief: dict[str, Any] | None = None) -> Any:
    return SimpleNamespace(flow_state=state, service_brief=brief or {})


async def test_the_expert_hold_answers_a_request_for_a_fix_without_choosing_pack_ideas() -> None:
    noted = [{"title": "Few walk-ins at the showroom"}]
    held = solution_context._expert_hold(conversation(), "give me a solution", noted, False)
    assert held == {
        "solution_asked_no_ideas": True,
        "solution_noted": ["Few walk-ins at the showroom"],
        "solution_why": "expert",
    }
    # the answer to pi's one question after "what can I do?" is also answered with ideas
    assert solution_context._expert_hold(
        conversation(), "customers mostly find us by driving past", noted, True
    )
    # not a request, outside the askable states, how-to, or the idea budget spent: the usual path
    assert solution_context._expert_hold(conversation(), "footfall is low", noted, False) is None
    assert (
        solution_context._expert_hold(
            conversation("S10_AWAITING_PAYMENT"), "give me a solution", noted, False
        )
        is None
    )
    assert (
        solution_context._expert_hold(conversation(), "how exactly would that work?", noted, False)
        is None
    )
    assert (
        solution_context._expert_hold(
            conversation(brief={"ideas_given": 8}), "give me a solution", noted, False
        )
        is None
    )


async def test_the_idea_filter_is_the_same_one_free_ideas_use() -> None:
    ctx = idea_filter.IdeaContext(
        subtype="footfall_low",
        given=(GOOD_ONE,),
    )
    advice = await advise(
        Scripted(diag([GOOD_ONE, GOOD_TWO, GOOD_THREE])), use_judge=False, idea_ctx=ctx
    )
    assert advice is not None and GOOD_ONE not in advice.ideas  # G7: already given
