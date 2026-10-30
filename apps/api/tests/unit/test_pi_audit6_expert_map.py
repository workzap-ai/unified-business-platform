# ruff: noqa: E501
"""Live Audit 6 (R5, R6, R7): the expert prompt never names an unconfirmed trade (TS7, TS8, NG1, IL1,
IL2), the problem ops reject an umbrella title (MD2), labels are not cut into the opposite meaning, and
the map picture is compact (MD1, MD3 to MD7). No model, no database."""

import io
import json
from types import SimpleNamespace
from typing import Any

import pytest
from PIL import Image

from app.modules.pi import expert_advisor, map_builder, map_render, problems
from app.modules.pi.problems import ProblemNote, ProblemOp
from app.modules.pi.service_conversation import trade_name

OWNER = (
    "Sales: we currently use QB. Stock: have around 10 crore stock written on paper. "
    "Staff: no track of it who comes and goes at what time. Cash: cash in and out dont match"
)
ASK = "What can you do about it?"


class Capture:
    def __init__(self) -> None:
        self.system = ""
        self.user: dict[str, Any] = {}

    async def complete(self, scope: object, **kwargs: Any) -> SimpleNamespace:
        self.system = kwargs["messages"][0].text()
        self.user = json.loads(kwargs["messages"][-1].text())
        return SimpleNamespace(text="{}")


async def _sent(industry: str | None, answered: list[str]) -> Capture:
    model = Capture()
    await expert_advisor.diagnose(
        model,  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        alias="pi_brain",
        conversation_id=None,
        owner_said=[OWNER, ASK],
        problems=["Sales records kept on QB"],
        industry=industry,
        subtype="",
        country="",
        never_say=[],
        already_said=[],
        examples=[],
        today="28 October 2026",
        steer=expert_advisor.Steer(answered=answered),
    )
    return model


@pytest.mark.asyncio
async def test_ts7_the_expert_prompt_bans_trade_nouns_until_the_business_is_confirmed() -> None:
    model = await _sent(None, [])
    assert "HAS NOT SAID WHAT TRADE" in model.system
    assert "machine" in model.system and "customer type" in model.system
    assert model.user["industry"] == "not known yet"


@pytest.mark.asyncio
async def test_ts8_a_confirmed_trade_is_used_and_carries_no_ban() -> None:
    model = await _sent("garment export", [])
    assert "HAS NOT SAID WHAT TRADE" not in model.system
    assert "garment export" in model.system


def test_ts8_a_guessed_business_type_is_not_the_persona_until_confirmed() -> None:
    guess = {"customer_profile": {"business_type": "packaging factory"}}
    assert trade_name(SimpleNamespace(service_brief=dict(guess)), []) is None
    said = {**guess, "industry_confirmed": True}
    assert trade_name(SimpleNamespace(service_brief=said), []) == "packaging factory"


@pytest.mark.asyncio
async def test_ng1_the_owners_question_is_not_sent_as_a_fact_they_answered() -> None:
    model = await _sent(None, [ASK, "10 crore of stock", "Is that right?"])
    assert model.user["facts_owner_already_answered"] == ["10 crore of stock"]
    only_question = await _sent(None, [ASK])
    assert "facts_owner_already_answered" not in only_question.user


def _candidates(*rows: tuple[str, str]) -> list[expert_advisor.Candidate]:
    return [expert_advisor.Candidate(idea=i, addresses=a) for i, a in rows]


def _vet(cands: list[expert_advisor.Candidate], multi: bool) -> list[str]:
    return expert_advisor.vet(
        cands,
        owner_words=OWNER,
        never_say=[],
        facts=set(),
        ctx=None,
        want=3,
        multi_problem=multi,
    )


def test_il1_an_idea_with_no_problem_is_dropped_when_there_are_several() -> None:
    good = "Count the cash in the drawer with a second person at closing and write the total on one sheet."
    cands = _candidates((good, "cash"), ("Write the stock on paper at closing each day.", ""))
    assert _vet(cands, True) == [good]
    assert len(_vet(cands, False)) == 2


def test_il2_with_four_problems_no_idea_names_a_channel_the_owner_never_raised() -> None:
    off = "Post a short video on Instagram showing the stock count so staff see it is checked."
    on = "Write each person's in and out time on one sheet at the door."
    out = _vet(_candidates((off, "stock"), (on, "staff")), True)
    assert out == [on]


# --- map -------------------------------------------------------------------------------------


def _note(title: str, words: list[str]) -> ProblemNote:
    return ProblemNote(title=title, user_words=words, category="finance", confidence=0.9)


def test_md2_an_umbrella_title_is_rejected_and_one_per_line_is_required() -> None:
    umbrella = ProblemOp(
        op="create",
        note=_note("Internal business problems across several areas", [OWNER]),
    )
    assert "umbrella" in (problems.check_ops([umbrella], set(), True, OWNER) or "")
    lines = OWNER.replace(". ", ".\n")
    one = ProblemOp(op="create", note=_note("Records spread over lines", lines.splitlines()[:2]))
    assert "one create per line" in (problems.check_ops([one], set(), True, lines) or "")


def test_md2_four_own_word_creates_pass_with_the_figures_kept() -> None:
    lines = OWNER.replace(". ", ".\n")
    rows = lines.splitlines()
    titles = [
        "Sales kept on QB",
        "10 crore stock on paper",
        "No staff in-out time record",
        "Cash in and out do not match",
    ]
    ops = [ProblemOp(op="create", note=_note(t, [r])) for t, r in zip(titles, rows, strict=True)]
    assert problems.check_ops(ops, set(), True, lines) is None


def test_a_label_is_not_cut_so_that_its_meaning_flips() -> None:
    prob = SimpleNamespace(title_local="", user_words=[], title="Cash in and out do not match")
    assert map_builder.label_of(prob) == "Cash in and out do not match"
    assert map_render._clean("Cash in and out do not match", None, map_render.MAX_LABEL_WORDS) == (
        "Cash in and out do not match"
    )


def _map(n: int) -> dict[str, Any]:
    labels = [
        "Sales kept on QB",
        "10 crore stock on paper",
        "No staff in-out time record",
        "Cash in and out do not match",
        "Customers wait too long",
        "Late deliveries from suppliers",
        "Returns are not tracked",
        "Rent and bills eat profit",
        "Orders get lost on chat",
    ]
    cats = [
        "sales",
        "inventory",
        "staff",
        "finance",
        "customers",
        "suppliers",
        "ops",
        "money",
        "comms",
    ]
    nodes = [
        {"id": f"n{i}", "label": labels[i], "facts": [], "category": cats[i]} for i in range(n)
    ]
    return {"version": 1, "nodes": nodes, "links": [], "clusters": []}


def _blank(png: bytes) -> float:
    image = Image.open(io.BytesIO(png)).convert("RGB")
    pixels = list(image.getdata())
    return sum(1 for p in pixels if p == map_render.BG) / len(pixels)


def test_md1_a_one_node_map_is_not_shared() -> None:
    assert map_builder.share_due(map_builder.ShareFacts(nodes=1)) == (False, "not_enough")


def test_md3_md7_titles_and_marks_stay_inside_and_text_is_at_least_24px() -> None:
    render = map_render.render_map(_map(3), "en")
    image = render.images[0]
    assert not image.overflow and image.smallest_text >= 24


@pytest.mark.parametrize("n", [2, 3, 4])
def test_md4_a_small_map_is_under_20_percent_blank(n: int) -> None:
    render = map_render.render_map(_map(n), "en")
    assert _blank(render.images[0].png) < 0.20


def test_md5_the_legend_has_no_ellipsis_and_leaves_no_category_out() -> None:
    drawn: list[str] = []
    original = map_render.Canvas.text

    def spy(self: Any, xy: Any, text: str, *args: Any, **kw: Any) -> Any:
        drawn.append(text)
        return original(self, xy, text, *args, **kw)

    map_render.Canvas.text = spy  # type: ignore[method-assign]
    try:
        render = map_render.render_map(_map(9), "en")
    finally:
        map_render.Canvas.text = original  # type: ignore[method-assign]
    assert render.images and not any("…" in t or "..." in t for t in drawn)
    text = " ".join(drawn)
    for category in (
        "sales",
        "inventory",
        "staff",
        "finance",
        "customers",
        "suppliers",
        "ops",
        "money",
        "comms",
    ):
        assert category in text
