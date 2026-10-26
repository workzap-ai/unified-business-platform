# ruff: noqa: E501  (Roman Urdu replies read better unbroken)
"""The golden replies of docs/pi-saas/pi-golden-replies.md pass the reply linter in brain mode.

They are the target voice (owner-approved, 2026-10-26): if the linter rejects one, either the
linter is too strict for pi's real voice or the golden reply broke a rule. Fix whichever is wrong."""

import pytest

from app.modules.pi import constitution

HISTORY = [{"role": "ai", "text": "Hi, I'm pi, an AI from Workzap."}]
OFFER = "Kya aap in sab ke liye solution document aur quote chahenge? Aap mana bhi kar sakte hain."

# (state, language, reply)
GOLDEN = [
    (
        "S1_LISTENING",
        "en",
        "I help with problems that get in the way of a business, and I note them for the Workzap team. "
        "I can't give you a full plan for starting one here. What is the first thing you're stuck on?",
    ),
    (
        "S3_NOTED",
        "en",
        "That choice is yours, so I won't pick one for you. I've noted that you're unsure whether to "
        "start online or in a shop. What do you have ready right now: stock, a shop space, or neither?",
    ),
    (
        "S1_LISTENING",
        "roman_ur",
        "Ji, ab Roman Urdu mein baat karte hain. Sales shuru karne mein abhi sab se bari rukawat kya hai?",
    ),
    (
        "S3_NOTED",
        "roman_ur",
        "Note kar liya, client nahi hain aur stock bohat para hai. Kya pehle kabhi aap ke paas koi "
        "customer aaye hain?",
    ),
    (
        "S3_NOTED",
        "roman_ur",
        "Note kar liya, purane customers se rabta nahi raha. Naye customers dhoondne ke liye ab tak "
        "kuch aazmaya hai?",
    ),
    ("S3_NOTED", "roman_ur", "Main AI hoon, insaan nahi. Main pi hoon, Workzap ki taraf se."),
    (
        "S5_READINESS",
        "roman_ur",
        "Ji, ye do ideas abhi aazma sakte hain:\n\n"
        "• Kuch behtareen joron ki saaf roshni mein chhoti video banayein, taake dekhne wale kapra aur "
        "rang pehchan sakein.\n"
        "• Jaan pehchan walon se kahein ke pasandeeda joron ki tasveer apne chat mein dikhayein, taake "
        "pehle customer wahin se aa jayein.\n\n" + OFFER,
    ),
    (
        "S5_READINESS",
        "roman_ur",
        "Kharcha is baat par depend karta hai ke kya build hoga, aur woh quote mein likha hoga. Quote "
        "free hota hai, aur yeh charge nahi hota.",
    ),
    (
        "S3_NOTED",
        "roman_ur",
        "Is ka dawai wala mashwara main nahi de sakta. Ye aap ke vet ka kaam hai. Agar halat serious "
        "hai to vet ko abhi bula lein.",
    ),
    (
        "S4_SORTED_SUMMARY",
        "roman_ur",
        "Main payment receive hone ki tasdeeq yahan nahi kar sakta. Team transfer aate hi yahin "
        "confirm karegi.",
    ),
]


@pytest.mark.parametrize(("state", "language", "reply"), GOLDEN)
def test_a_golden_reply_breaks_no_rule(state, language, reply):
    context = {
        "pi_mode": "brain",
        "flow": {"state": state},
        "reply_language": language,
        "history": HISTORY,
        "solution_asked": "ideas" in reply,
    }
    found = [v.rule for v in constitution.lint(reply, context)]
    assert not found, found
