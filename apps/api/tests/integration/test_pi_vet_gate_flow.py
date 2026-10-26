# ruff: noqa: E501  (Roman Urdu lines read better unbroken)
"""Live chat 4: "meri bhens beemar hai kya dawai doon?" in a restaurant chat got "Is masle ke liye
yahan itne hi ideas hain ... Kya main aap ke liye solution document aur quote banwa doon?". The
veterinary advice gate runs before the model: the answer is the refusal line, whatever the model
would have said, and nothing is offered."""

import pytest
from sqlalchemy import select
from test_pi_brain_problems import adaptive, say, workspace
from test_pi_service_conversations import turn

from app.modules.pi.models import PiMessage

pytestmark = pytest.mark.integration


def model(context, n):  # what the model would have said: ideas and the offer
    return turn(
        reply="Ji, ye do ideas hain:\n\n• Chhoti video banayein.\n• Message karein.\n\nKya aap in sab ke liye solution document aur quote chahenge? Aap mana bhi kar sakte hain.",
        language="roman_ur",
    )


async def test_a_sick_animal_and_a_medicine_gets_the_refusal_and_no_offer(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    await say(pi, "mera restaurant hai, customers kam hain", "vg-1")
    await say(pi, "meri bhens beemar hai kya dawai doon?", "vg-2")
    replies = [
        m.body
        for m in await business_db.scalars(
            select(PiMessage)
            .where(PiMessage.direction == "outbound")
            .order_by(PiMessage.created_at)
        )
    ]
    last = replies[-1]
    assert "veterinary doctor" in last and "mumkin nahi" in last, last
    assert "solution document" not in last and "quote" not in last.lower(), last
    await pi.close()
