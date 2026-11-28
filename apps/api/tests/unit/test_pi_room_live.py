"""The live view of a call: captions with translation, staff tips and notes."""

import asyncio

import pytest

from app.modules.pi_meetings import room_live as rl
from app.modules.pi_meetings.room_live import Advice, Feed


def fresh():
    return rl.empty()


def test_a_line_is_redacted_numbered_and_trimmed() -> None:
    live = fresh()
    text = "call me on 0300 1234567"
    line = rl.add_line(live, role="customer", name="Ayesha", text=text, lang="en")
    assert line is not None and line["n"] == 1 and "1234567" not in line["text"]
    assert rl.add_line(live, role="customer", name="A", text="   ", lang="en") is None
    for i in range(rl.LINES_KEPT + 10):
        rl.add_line(live, role="staff", name="S", text=f"line number {i}", lang="en")
    assert len(live["lines"]) == rl.LINES_KEPT
    assert len(repr(live)) <= rl.MAX_BYTES


def test_a_translation_moves_the_line_so_a_poller_fetches_it_again() -> None:
    live = fresh()
    one = rl.add_line(live, role="customer", name="A", text="mujhe order chahiye", lang="roman_ur")
    two = rl.add_line(live, role="staff", name="S", text="sure", lang="en")
    seen = live["seq"]
    assert rl.view(live, seen, staff=False)["lines"] == []
    assert rl.set_translation(live, one["n"], "I need an order", "en")
    got = rl.view(live, seen, staff=False)["lines"]
    assert [x["n"] for x in got] == [one["n"]] and got[0]["tr"] == "I need an order"
    assert two["n"] not in [x["n"] for x in got]
    assert not rl.set_translation(live, 999, "x", "en")  # a line already trimmed away


def test_a_guest_never_gets_tips_or_notes_and_an_old_number_resets() -> None:
    live = fresh()
    rl.add_line(live, role="customer", name="A", text="we want a website for our shop", lang="en")
    rl.add_tip(live, "tip", "Ask which products they sell first")
    rl.add_tip(live, "note", "They want a website for their shop", "requirement_explicit")
    guest = rl.view(live, 0, staff=False)
    staff = rl.view(live, 0, staff=True)
    assert "tips" not in guest and len(staff["tips"]) == 2
    assert staff["tips"][1]["note_kind"] == "requirement_explicit"
    assert rl.view(live, live["seq"] + 50, staff=True)["reset"] is True
    assert rl.view(live, 0, staff=True)["reset"] is False


def test_the_same_tip_is_not_added_twice_and_bad_kinds_are_ignored() -> None:
    live = fresh()
    assert rl.add_tip(live, "tip", "Ask which products they sell first") is not None
    assert rl.add_tip(live, "tip", "ask which products they sell first please") is None
    assert rl.add_tip(live, "note", "Ask which products they sell first") is not None
    assert rl.add_tip(live, "other", "something") is None
    assert rl.add_tip(live, "tip", "  ") is None
    assert "note_kind" not in rl.add_tip(live, "note", "Needs delivery", "made_up_kind")


@pytest.mark.parametrize(
    "text",
    [
        "Offer them a 20% discount if they sign today",
        "Quote Rs 50,000 for the site",
        "Tell them to send the card number",
        "Call them on 03001234567",
        "Email ayesha@example.com the plan",
        "Ask for the CNIC number 3520212345671",
    ],
)
def test_a_tip_with_money_or_personal_details_is_dropped_by_code(text: str) -> None:
    assert rl.clean_advice(text) == ""


def test_a_clean_tip_passes_and_languages_choose_their_target() -> None:
    assert rl.clean_advice("Ask how many orders they get on a busy day") != ""
    # words that merely contain "rs" or "inr" are not currencies
    assert rl.clean_advice("Ask which customers order the most and where they live") != ""
    assert rl.target_for("ur") == rl.target_for("roman_ur") == "en"
    assert rl.target_for("en") == "ur"
    assert rl.target_for("fr") == "" and rl.target_for(None) == ""


class Recorder:
    def __init__(self):
        self.saved = []
        self.fail = False

    async def save(self, live):
        if self.fail:
            raise RuntimeError("db down")
        self.saved.append(rl.normal(live)["seq"])


async def names(speaker):
    return ("Ayesha", "customer") if speaker.startswith("g_") else ("Sam", "staff")


def feed_with(rec, translate=None, advise=None, clock=None):
    return Feed(
        None,
        save=rec.save,
        names=names,
        translate=translate,
        advise_with=advise,
        clock=clock or (lambda: 1000.0),
    )


async def test_a_heard_line_is_shown_at_once_and_its_translation_follows() -> None:
    rec = Recorder()

    async def translate(text, target):
        await asyncio.sleep(0)
        return f"[{target}] {text}"

    feed = feed_with(rec, translate=translate)
    await feed.heard("g_1", "mujhe online order system chahiye")
    assert rec.saved and "tr" not in feed.live["lines"][0]  # the original first
    await feed.settle()
    line = feed.live["lines"][0]
    assert line["role"] == "customer" and line["name"] == "Ayesha"
    assert line["tr"].startswith("[en]") and line["tr_lang"] == "en"
    await feed.said("Could you tell me what you sell today")
    await feed.settle()
    assert feed.live["lines"][1]["role"] == "pi" and feed.live["lines"][1]["tr_lang"] == "ur"


async def test_a_failing_translation_or_save_never_stops_the_call() -> None:
    rec = Recorder()

    async def broken(text, target):
        raise RuntimeError("model down")

    feed = feed_with(rec, translate=broken)
    await feed.heard("g_1", "mujhe order chahiye abhi")
    await feed.settle()
    assert feed.live["lines"][0]["text"] and "tr" not in feed.live["lines"][0]
    rec.fail = True
    await feed.heard("s_1", "Sure, tell me more about it")  # the save fails: still no exception
    assert len(feed.live["lines"]) == 2


async def test_translations_are_capped_and_tiny_lines_are_not_translated() -> None:
    rec = Recorder()
    calls = []

    async def translate(text, target):
        calls.append(text)
        return "x" + text

    feed = feed_with(rec, translate=translate)
    await feed.heard("g_1", "haan")  # one word
    for i in range(rl.TRANSLATE_CAP + 20):
        await feed.heard("s_1", f"this is sentence number {i} of the call")
    await feed.settle()
    assert len(calls) == rl.TRANSLATE_CAP


async def test_a_tip_comes_only_after_a_customer_line_and_not_too_often() -> None:
    rec = Recorder()
    now = [1000.0]
    asked = []

    async def advise(lines):
        asked.append(len(lines))
        return Advice(
            tip="Ask what they sell",
            note="They need a website",
            note_kind="requirement_explicit",
        )

    feed = feed_with(rec, advise=advise, clock=lambda: now[0])
    await feed.heard("s_1", "Hello, how can I help you today")  # staff speaking: no tip
    await feed.settle()
    assert asked == []
    await feed.heard("g_1", "We would like a website for our shop")
    await feed.settle()
    assert asked == [2]
    assert [t["kind"] for t in feed.live["tips"]] == ["tip", "note"]
    await feed.heard("g_1", "It should show our products and prices")  # too soon after the last
    await feed.settle()
    assert asked == [2]
    now[0] += rl.ADVISE_GAP_S + 1
    await feed.heard("g_1", "We have about forty products in total")
    await feed.settle()
    assert len(asked) == 2


async def test_unsafe_advice_from_the_model_never_reaches_staff() -> None:
    class FakeManager:
        async def complete_structured(self, scope, schema, **kwargs):
            class Result:
                value = schema(
                    tip="Offer a 20% discount", note="They will pay Rs 5000", note_kind="decision"
                )

            return Result()

    lines = [{"role": "customer", "text": "hello there friend"}]
    out = await rl.advise(FakeManager(), None, lines, {})
    assert out.tip == "" and out.note == "" and out.note_kind == ""


async def test_translate_line_returns_nothing_when_the_model_only_repeats_or_is_down() -> None:
    from app.ai.errors import GatewayUnavailable

    class Reply:
        def __init__(self, text):
            self.text = text

    class Same:
        async def complete(self, scope, **kwargs):
            return Reply("Hello there")

    class Down:
        async def complete(self, scope, **kwargs):
            raise GatewayUnavailable("down")

    assert await rl.translate_line(Same(), None, "hello there", "ur") == ""
    assert await rl.translate_line(Down(), None, "hello there", "ur") == ""
