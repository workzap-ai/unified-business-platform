"""Platform spec v1.4, 17.5: "what can you do?" is answered with two ideas, one Workzap 'could' line
(no tool words, no price), and the one question."""

from app.modules.pi import service_conversation as sc
from app.modules.pi.service_conversation import ServiceTurn, add_capability_line

B = "•"
REPLY = (
    f"Bilkul.\n\n{B} Count the stock once a week.\n{B} Write each sale down."
    "\n\nWhich shop sells most?"
)


def ctx(said="what can you do?", language="en", **over):
    base = {
        "latest_customer_message": said,
        "reply_language": language,
        "noted_problems": [{"group": "stock_inventory"}],
    }
    return {**base, **over}


def test_the_line_comes_after_the_ideas_and_before_the_question() -> None:
    turn = ServiceTurn(reply=REPLY)
    add_capability_line(turn, ctx())
    lines = turn.reply.split("\n")
    assert lines[-1] == "Which shop sells most?"
    line = next(x for x in lines if x.startswith("Workzap could"))
    assert lines.index(line) > max(i for i, x in enumerate(lines) if x.startswith(B))
    assert "will" not in line.lower() and not any(c.isdigit() for c in line)


def test_roman_urdu_gets_its_own_line() -> None:
    turn = ServiceTurn(reply=REPLY)
    add_capability_line(turn, ctx(said="aap kya kar sakte hain?", language="roman_ur"))
    assert "Workzap ye kar sakta hai:" in turn.reply


def test_an_ordinary_message_gets_no_workzap_line() -> None:
    turn = ServiceTurn(reply=REPLY)
    add_capability_line(turn, ctx(said="stock kam hota hai"))
    assert "Workzap" not in turn.reply


def test_no_ideas_no_line_and_never_twice() -> None:
    plain = ServiceTurn(reply="Which shop sells most?")
    add_capability_line(plain, ctx())
    assert "Workzap" not in plain.reply
    turn = ServiceTurn(reply=REPLY)
    add_capability_line(turn, ctx())
    once = turn.reply
    add_capability_line(turn, ctx())
    assert turn.reply == once


def test_no_noted_problem_no_catalogue_line() -> None:
    turn = ServiceTurn(reply=REPLY)
    add_capability_line(turn, ctx(noted_problems=[]))
    assert "Workzap" not in turn.reply


def test_the_catalogue_lines_have_no_tool_words() -> None:
    from app.modules.pi import solutions

    for key in solutions.CATALOGUE:
        for lang in ("en", "roman_ur"):
            line = sc.COULD_LINE[lang].format(phrase=solutions.build_phrase(key, lang))
            assert not any(c.isdigit() for c in line), (key, lang)
