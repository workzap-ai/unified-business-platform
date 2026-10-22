"""Questions about nori are answered from the approved facts only (spec 0.4, 6.9; golden G15)."""

import pytest

from app.modules.pi import safety as s


@pytest.mark.parametrize(
    ("said", "kind"),
    [
        ("I saw nori. Does it work with CCTV?", s.Nori.VISION),
        ("does nori have camera support", s.Nori.VISION),
        ("How much does nori cost?", s.Nori.PRICING),
        ("nori plans please", s.Nori.PRICING),
        ("tell me about nori", s.Nori.ABOUT),
        ("what is nori", s.Nori.ABOUT),
        ("nori kya hai", s.Nori.ABOUT),
    ],
)
def test_nori_questions(said, kind):
    assert s.nori_asked(said) == kind


@pytest.mark.parametrize(
    "said",
    [
        "our CCTV cameras are broken and we cannot see the till",
        "the vision of my business is to grow",
        "stock runs out in two shops",
        "book a nori demo",  # routed to the team as an enquiry, not answered here
    ],
)
def test_other_talk_is_not_a_nori_question(said):
    assert s.nori_asked(said) is None


def test_the_answers_state_only_approved_facts():
    for language in ("en", "roman_ur"):
        vision = s.nori_reply(s.Nori.VISION, language)
        assert ("coming soon" in vision) or ("jald aa raha" in vision)
        assert "available" in vision.lower() or "available nahi" in vision
        pricing = s.nori_reply(s.Nori.PRICING, language)
        assert "workzap.ai/nori/pricing" in pricing
        assert not any(ch.isdigit() for ch in pricing)  # never a price from memory
        for kind in s.Nori:
            text = s.nori_reply(kind, language)
            assert text.count("?") <= 1 and "!" not in text
