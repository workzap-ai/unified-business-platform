"""Stop is final: the follow-up senders ask optout_guard, which reads the owner's own messages."""

import asyncio
from types import SimpleNamespace

import pytest

from app.modules.pi import optout_guard as og


@pytest.mark.parametrize(
    "text",
    ["Stop", "stop reminders", "Stop reminders", "STOP", "please stop messaging me", "band karo"],
)
def test_the_words_that_mean_stop(text):
    assert og.said_stop(text)


@pytest.mark.parametrize(
    "text",
    [
        "please don't stop the order",
        "I want to stop the stock loss in my shop, can you help with that today",
        "ok",
        "",
        None,
        "x" * 200,
    ],
)
def test_other_words_do_not(text):
    assert not og.said_stop(text)


class _Session:
    def __init__(self, bodies):
        self.bodies = bodies

    async def scalars(self, _query):
        return iter(self.bodies)


def _conv(consent=None):
    brief = {} if consent is None else {"reminder_consent": consent}
    return SimpleNamespace(id=1, service_brief=brief, followup_due_at="soon")


def test_a_stop_in_the_history_repairs_the_consent_and_clears_the_due_time():
    conv = _conv("unknown")
    assert asyncio.run(og.opted_out(_Session(["hello", "Stop reminders"]), conv))
    assert conv.service_brief["reminder_consent"] == "declined"
    assert conv.followup_due_at is None


def test_declined_is_true_without_reading_messages():
    assert asyncio.run(og.opted_out(_Session([]), _conv("declined")))


def test_no_stop_means_not_opted_out_and_nothing_changes():
    conv = _conv("granted")
    assert not asyncio.run(og.opted_out(_Session(["hi", "ok thanks"]), conv))
    assert conv.service_brief["reminder_consent"] == "granted"
    assert conv.followup_due_at == "soon"
