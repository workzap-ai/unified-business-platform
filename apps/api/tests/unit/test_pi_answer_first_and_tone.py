"""Book 2 3.1 and 10.2: R-ANS-01 (the first sentence answers a direct question), R-ANS-02 (a
yes/no question gets yes or no first), R-ECHO-01 (the noted line is 12 words or fewer), R-TONE-03
(no defensiveness or 'please be patient'), R-VOICE-02 not flagging the fixed offer's tail."""

from app.modules.pi import constitution


def rules(said: str, reply: str, state: str = "S3_NOTED") -> list[str]:
    context = {
        "latest_customer_message": said,
        "history": [{"role": "ai", "text": "Hi, I'm pi, an AI from Workzap."}],
        "flow": {"state": state},
    }
    return [v.rule for v in constitution.lint(reply, context)]


def test_a_question_back_is_not_an_answer_to_a_direct_question():
    assert "R-ANS-01" in rules(
        "kya aap mere liye kuch kar sakte hain?", "Aap kis cheez ka kaam karte hain?"
    )
    ok = "Haan, is par kaam ho sakta hai. Aap kis cheez ka kaam karte hain?"
    assert "R-ANS-01" not in rules("kya aap mere liye kuch kar sakte hain?", ok)
    assert "R-ANS-01" not in rules(
        "stock khatam ho jata hai", "Kaunsi dukaan mein?"
    )  # no question asked


def test_a_yes_no_question_is_not_answered_with_thanks_noted():
    said = "Can you help with my stock problem?"
    assert "R-ANS-02" in rules(said, "Thanks. I've noted it: stock problem. Which shop is worst?")
    assert "R-ANS-02" not in rules(said, "Yes, that can be worked on. Which shop is worst?")
    assert "R-ANS-02" not in rules("stock khatam ho jata hai", "Thanks. Noted. Which shop?")


def test_the_noted_line_names_the_problem_in_at_most_twelve_words():
    long = "I've noted it: " + " ".join(["word"] * 14) + ". What else?"
    assert "R-ECHO-01" in rules("some message here", long)
    short = "Thanks. I've noted it: best-sellers run out in two shops. What else?"
    assert "R-ECHO-01" not in rules("best-sellers run out", short)
    assert "R-ECHO-01" in rules("x y z", "Note kar liya: " + " ".join(["lafz"] * 15) + ". Aur kya?")


def test_a_frustrated_person_gets_no_please_be_patient_and_no_lecture():
    for reply in (
        "Please be patient, I need to ask a few things. Which shop?",
        "The reason I ask is so I can note it. Which shop?",
        "Sabar karein, main isliye poochta hoon. Kaunsi dukaan?",
    ):
        assert "R-TONE-03" in rules("jaldi karo, sawal hi poochte rahoge?", reply), reply
    assert "R-TONE-03" not in rules(
        "jaldi", "Maazrat. Pehle do kaam karein, phir dekhte hain. Kaunsi dukaan?"
    )


def test_the_fixed_offer_tail_after_the_question_is_not_flagged_as_a_second_sentence():
    offers = (
        "Shall I get a solution document and a quote made for you? You can say no.",
        "Kya main aap ke liye solution document aur quote banwa doon? Mana bhi kar sakte hain.",
    )
    for offer in offers:
        assert "R-VOICE-02" not in rules("solution dain", "Sure. " + offer), offer
    assert "R-VOICE-02" in rules("x", "Which shop? Noted, thanks.")  # a real trailing statement
