"""One place for what the offer says in the journey tests, derived from production.

pi has two offer wordings: the legacy one (`decisions.text("offer", lang)`, used while the Solution
Box gate is off) and the Solution Box one (`solution_ask.box_offer_line`, used whenever the
workspace turns `facts["box_offer"]` on, which these journeys do by patching
`box.box_offer_enabled`). The
tests used to pin the legacy text, so they broke when the box wording went in (c41ab202). They now
ask production for the text, and still assert the behaviour that matters: the offer is the last
sentence and the only question, it names no price, and it does not pressure ("You can say no" is
banned as pressure, spec v1.6 Part 18.3 and the banned-phrase table).
"""

import re

from app.modules.pi import decisions, solution_ask

PRICE = re.compile(
    r"(?:[$£€]|\b(?:rs|pkr|usd|aed|gbp)\b\.?\s*\d|\b\d[\d,.]*\s*(?:rupees|dollars)\b)",
    re.I,
)


def expected_offer(language: str = "en", *, box: bool = True, problems: int = 1) -> str:
    """The offer production sends for a chat with `problems` noted problems (fewer than three
    noted, as in these journeys, gives the neutral wording; the A and B wordings need a richer
    map and alternate by message id, so they are not pinned here)."""
    if not box:
        return decisions.text("offer", language)
    return solution_ask.offer_line(
        language,
        {
            "box_offer": True,
            "reply_language": language,
            "noted_problems": [{}] * problems,
            "latest_customer_message": "",
            "brief": {},
        },
    )


def assert_offer_ends(body: str, language: str = "en", *, problems: int = 1) -> None:
    """The reply ends with the offer, which is its one question, with no price and no pressure."""
    offer = expected_offer(language, problems=problems)
    text = body.rstrip()
    assert text.endswith(offer), (offer, body)
    assert text.endswith(("?", "؟")), body
    assert len(re.findall(r"[?؟]", text)) == 1, body  # one question, and it is the last sentence
    assert "you can say no" not in text.lower(), body
    assert not PRICE.search(text), body
