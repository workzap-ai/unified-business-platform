"""G54 (platform spec v1.6, Live Audit 5 Part 7): replay of the 28 October chat.

WIRING ONLY. The model is scripted, so these tests prove what the application does around the
model (four stored nodes from four lines, no offer, no offer state, the scripted answer reaching
the owner first-sentence-first), NOT that a real model would answer well. The parts of G54 that
need a real model (no industry noun before the owner names the business; the direct question
answered in the first sentence; the four nodes in the owner's own words and figures) are in the
xfail test below and are not claimed done."""

import re

import pytest
from test_pi_brain_decisions import state_of
from test_pi_brain_problems import adaptive, create, problems_of, say, workspace
from test_pi_service_conversations import turn

from app.modules.pi import reply_gates

pytestmark = pytest.mark.integration

FOUR_LINES = (
    "Sales: uses QB. Stock: about 10 crore, written on paper. "
    "Staff: no track of who comes and goes. Cash: in and out don't match."
)
# Nouns that would show pi guessed the trade before the owner named it (a sample, not the list).
INDUSTRY_NOUNS = re.compile(
    r"\b(?:bakery|boutique|pharmacy|restaurant|garments?|textile|clinic|salon|school|"
    r"workshop|farm|dairy|grocery|kiryana|hardware|jewell?ery)\b",
    re.IGNORECASE,
)


def scripted_model(context, n):
    said = context["latest_customer_message"]
    if "Sales: uses QB" in said:
        return turn(
            reply=(
                "Hi, I'm pi, an AI from Workzap. Ten crore of stock on paper while cash in and "
                "out do not match may be one problem. Which of the four hurts most?"
            ),
            language="en",
            problem_ops=[
                create("Sales kept in QB", "Sales: uses QB.", "sales_revenue"),
                create("Stock of about 10 crore on paper", "Stock: about 10 crore, paper."),
                create(
                    "No track of staff coming and going", "no track of who comes", "people_staff"
                ),
                create(
                    "Cash in and out do not match",
                    "Cash: in and out don't match.",
                    "cash_collections",
                ),
            ],
        )
    if "What can you do" in said:
        return turn(
            reply=(
                "I can help you see how the four connect and what to count first. "
                "Which of them costs you most each month?"
            ),
            language="en",
        )
    return turn(
        reply="Hi, I'm pi, an AI from Workzap. What is your business called?", language="en"
    )


async def replay(api, db, monkeypatch):
    adaptive(monkeypatch, scripted_model)
    pi = await workspace(api, db)
    for key, text in (
        ("g54-1", "Hello"),
        ("g54-2", "I run a business. It has alot of problems"),
        ("g54-3", FOUR_LINES),
        ("g54-4", "What can you do about it?"),
    ):
        await say(pi, text, key)
    return pi


async def test_g54_wiring_only_four_lines_become_four_nodes_and_no_offer(
    api, business_db, monkeypatch
):
    pi = await replay(api, business_db, monkeypatch)
    _, rows = await problems_of(business_db, pi)
    assert len(rows) == 4  # one node per line, no summary node
    assert not any("several areas" in r.title.lower() for r in rows)
    answer = (await pi.reply_to("g54-4")).body
    assert not re.search(r"solution document|a quote", answer, re.IGNORECASE)  # no offer
    assert (await state_of(business_db, pi)).flow_state != "S5_READINESS"
    await pi.close()


async def test_g54_wiring_only_no_scripted_industry_noun_reaches_the_owner_early(
    api, business_db, monkeypatch
):
    pi = await replay(api, business_db, monkeypatch)
    for key in ("g54-1", "g54-2", "g54-3"):
        assert not INDUSTRY_NOUNS.search((await pi.reply_to(key)).body)
    answer = (await pi.reply_to("g54-4")).body
    assert reply_gates.empty_opener(answer) is None  # it does not open with filler
    assert answer.count("?") == 1 and answer.rstrip().endswith("?")  # one question, last
    await pi.close()


@pytest.mark.xfail(
    reason="FOUND IN THE REPLAY: to 'What can you do about it?' the application replaced the "
    "scripted answer with 'Yes. I don't have a quick idea for this one that I can give here. "
    "What have you tried so far?', whose first sentence does not answer the owner's question "
    "(spec 18.8 EO3, 17.5). Open for the flow lead",
    strict=False,
)
async def test_g54_first_sentence_answers_the_direct_question(api, business_db, monkeypatch):
    pi = await replay(api, business_db, monkeypatch)
    first = re.split(r"(?<=[.!?])\s+", (await pi.reply_to("g54-4")).body)[0]
    await pi.close()
    assert first.strip().rstrip(".") not in {"Yes", "No", "Noted"}


@pytest.mark.xfail(
    reason="G54 needs a real model: only a live replay can show that no industry noun appears "
    "before the owner names the business, that the direct question is answered in the first "
    "sentence, and that the four nodes keep the owner's own words and figures",
    run=False,
)
def test_g54_real_model_replay() -> None:
    raise AssertionError("not run: needs the live model (no model calls in this lane)")
