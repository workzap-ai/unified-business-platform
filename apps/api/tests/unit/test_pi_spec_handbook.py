"""pi is given the specification's own words, chosen for the moment (spec Appendix A)."""

from app.modules.pi import spec_handbook as h


def test_every_section_the_selector_names_exists_in_the_handbook():
    book = h.sections()
    assert len(book) >= 70
    wanted = set(h.CORE)
    for ids in h.BY_STATE.values():
        wanted |= set(ids)
    for _, ids in h.TOPICS:
        wanted |= set(ids)
    for ids in h.GOLDEN_BY_STATE.values():
        wanted |= set(ids)
    assert not wanted - set(book), sorted(wanted - set(book))


def test_the_constitution_and_the_voice_are_always_there():
    text = h.guidance("S1_LISTENING", "hello")
    for rule in ("R-DISC-01", "R-SELL-01", "R-PAY-01", "R-PRIV-01", "R-ADV-01", "R-EMER-01"):
        assert rule in text
    assert "talk like a human" in text.lower()


def test_the_guidance_follows_the_stage_and_the_topic():
    listening = h.guidance("S1_LISTENING", "stock runs out")
    assert "3.3 The listening loop" in listening and "5.6 Payment and kickoff" not in listening
    paying = h.guidance("S10_AWAITING_PAYMENT", "I paid, here is the screenshot")
    assert "5.6 Payment and kickoff" in paying and "6.2 Money and fraud" in paying
    assert "6.4 Advice boundaries" in h.guidance("S1_LISTENING", "which tax should I pay")


def test_golden_conversations_are_chosen_by_situation_and_capped():
    rules, golden = h.chosen_ids("S1_LISTENING", "assalam o alaikum", "roman_ur")
    assert golden[0] == "G6" and len(golden) <= h.MAX_GOLDEN
    _, team = h.chosen_ids("S5_READINESS", "ok", can_approve=False)
    assert team[0] == "G13"
    _, back = h.chosen_ids("S1_LISTENING", "hi again", days_away=40)
    assert back[0] == "G14"


def test_the_prompt_part_stays_within_budget_and_reads_cleanly():
    for state in h.BY_STATE:
        text = h.guidance(state, "payment refund card tax complaint demo photo human")
        assert len(text) <= h.MAX_CHARS + 6000  # rules are capped, the golden examples are small
        assert "\ufe8d" not in text and "\u0600" not in text  # no reversed Arabic fragments
