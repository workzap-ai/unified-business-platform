# ruff: noqa: E501  (Roman Urdu lines read better unbroken)
"""Live chat 5 (owner, tuition academy, 17:59-18:06 PKT, running 3e76333): the exact customer messages
and the exact replies pi sent. Messages: (1) Hello (2)-(6) below."""

from app.modules.pi import constitution, learning_voice

M2 = "meri academy hai Lahore mein, parents fee late dete hain aur har mahine chase karna parta hai"
M3 = "call se, parents ko bura lagta hai"
M4 = "zyada tar"
M5 = "nahi, bas pehle hafte mein lete hain"

R2 = "Is par kaam banta hai.\nMaine note kar liya: fee late.\nYe har mahine kitni der se hoti hai?"
R3 = "Maine note kar liya: fee late hone par call karni parti hai."
R4 = "Theek hai, zyada tar note kar liya. Aur kuch is mein add karna hai?"
FIRST = "Hi, main pi hoon, Workzap ka AI. Apne business mein jo masla hai woh batayein."


def context(said, earlier, replies, state="S3_NOTED", missing=("where", "impact", "since")):
    history = [{"role": "ai", "text": FIRST}]
    for asked, answered in zip(earlier, replies, strict=False):
        history += [{"role": "customer", "text": asked}, {"role": "ai", "text": answered}]
    return {
        "pi_mode": "brain",
        "flow": {"state": state},
        "reply_language": "roman_ur",
        "history": history,
        "latest_customer_message": said,
        "noted_problems": [{"missing": list(missing)}],
    }


def rules(reply, ctx):
    return {v.rule for v in constitution.lint(reply, ctx)}


def questions(text):
    return [s for s in constitution._sentences(text) if s.endswith("?")]


def test_reply_2_a_hollow_opener_is_caught_and_removed():
    ctx = context(M2, [], [])
    assert "R-TONE-01" in rules(R2, ctx)
    assert (
        constitution.repair(R2, ctx)
        == "Maine note kar liya: fee late.\nYe har mahine kitni der se hoti hai?"
    )


def test_reply_3_a_dead_end_gets_the_next_specific_question():
    ctx = context(M3, [M2], [R2])
    assert "R-PROG-01" in rules(R3, ctx)
    fixed = constitution.repair(R3, ctx)
    assert fixed.startswith("Maine note kar liya: fee late hone par call karni parti hai.")
    [asked] = questions(fixed)
    assert fixed.endswith(asked) and "aur kuch" not in asked.lower()
    assert asked == "Ye har jagah hota hai, ya sirf kuch jagah?"  # the first open slot (scope)
    assert "R-PROG-01" not in rules(fixed, ctx)


def test_reply_3_the_slot_the_person_already_answered_is_not_asked():
    ctx = context("parents roz fee late dete hain", [M2], [R2], missing=("how_often", "where"))
    fixed = constitution.repair(R3, ctx)
    assert "kitni baar" not in fixed and "roz hota hai" not in fixed
    assert fixed.endswith("Ye har jagah hota hai, ya sirf kuch jagah?")


def test_reply_4_noted_on_a_bare_fragment_and_the_comma_filler_are_removed():
    ctx = context(M4, [M2, M3], [R2, R3])
    found = rules(R4, ctx)
    assert "R-HONEST-02" in found
    fixed = constitution.repair(R4, ctx)
    assert "note kar liya" not in fixed.lower() and "theek hai" not in fixed.lower()
    assert "aur kuch" not in fixed.lower()  # a bare answer does not earn the generic closer
    assert len(questions(fixed)) == 1 and fixed.endswith("?")


def test_the_second_generic_closer_in_a_conversation_becomes_a_specific_question():
    earlier = "Note kar liya. Aur kuch is mein add karna hai?"
    ctx = context(M5, [M2, M3, M4], [R2, R3, earlier])
    reply = "Note kar liya, pehle hafte mein lete hain. Aur kuch is mein add karna hai?"
    fixed = constitution.repair(reply, ctx)
    assert fixed.startswith("Note kar liya, pehle hafte mein lete hain.")
    assert "aur kuch" not in fixed.lower() and fixed.endswith("?")


def test_the_first_generic_closer_after_a_real_answer_is_allowed_once():
    ctx = context(M3, [M2], [R2])
    reply = "Note kar liya, parents ko call se bura lagta hai. Aur kuch is mein add karna hai?"
    assert constitution.repair(reply, ctx) == reply


def test_a_reply_that_already_asks_or_answers_or_offers_is_left_alone():
    ctx = context(M3, [M2], [R2])
    asked = "Maine note kar liya: fee late hone par call karni parti hai. Ye kab se ho raha hai?"
    assert constitution.repair(asked, ctx) == asked
    ai = context("kya aap insaan ho?", [M2], [R2])
    answer = "Main AI hoon, insaan nahi. Main pi hoon, Workzap ki taraf se."
    assert "R-PROG-01" not in rules(answer, ai)
    summary = context(M3, [M2], [R2], state="S4_SORTED_SUMMARY")
    assert "R-PROG-01" not in rules(R3, summary)
    offer = (
        "Kya aap in sab ke liye solution document aur quote chahenge? Aap mana bhi kar sakte hain."
    )
    at_the_offer = context(M3, [M2], [R2], state="S5_READINESS")
    assert constitution._ensure_next_step(offer, at_the_offer) == offer


def test_noted_is_fine_when_the_answer_has_content():
    ctx = context(M5, [M2, M3, M4], [R2, R3, R4])
    reply = "Note kar liya, pehle hafte mein lete hain. Ye kab se aise ho raha hai?"
    assert "R-HONEST-02" not in rules(reply, ctx)


def test_no_acknowledgement_variant_is_a_verdict_or_a_hollow_promise():
    for language, texts in learning_voice.SEEDS["acknowledge"].items():
        assert len(texts) >= learning_voice.MIN_LIVE, language
        assert not set(texts) & learning_voice.DROPPED, language
        for text in texts:
            assert not constitution.HOLLOW_OPENER.match(
                text
            ) and not constitution.VERDICT_OPENER.match(text)
