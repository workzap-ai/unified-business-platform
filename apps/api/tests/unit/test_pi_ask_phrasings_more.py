# ruff: noqa: E501
"""More very common ways to ask for a fix (Roman Urdu, Hindi, Urdu script, Arabic) and the ordinary
sentences that must not count as an ask."""

import pytest

from app.modules.pi import solution_ask


@pytest.mark.parametrize(
    "said",
    [
        # Roman Urdu
        "ab kya karun",
        "ab kia karun",
        "main kya karoon",
        "kya karoon",
        "mujhe kya karna chahiye",
        "mujhe kia krna chahiye",
        "kya karna hoga ab",
        "kya kiya jaye",
        "kya kia jaye",
        "ye kaise theek hoga",
        "ye kese theek hoga",
        "isko kaise theek karen",
        "koi hal",
        "koi hal batao",
        "koi hal nikalo",
        "hal nikaalo",
        "koi tareeqa",
        "koi tareeqa batao",
        "koi tarika btao",
        "koi rasta",
        "koi raasta dikhao",
        "kuch batao",
        "kuch btao",
        "kuch bataiye",
        "kuch tou bataen",
        "kuch to batao na",
        "is masle ko kaise nipten",
        # Hindi
        "मुझे क्या करना चाहिए",
        "अब क्या करूं",
        "कोई हल",
        "कोई उपाय बताओ",
        "कोई तरीका",
        "क्या किया जाए",
        "इसे कैसे ठीक करें",
        "कुछ बताओ",
        "कुछ करो",
        # Urdu script
        "اب کیا کروں",
        "کوئی حل",
        "مجھے کیا کرنا چاہیے",
        "کیا کیا جائے",
        "یہ کیسے ٹھیک ہوگا",
        "کوئی طریقہ",
        "کچھ بتائیں",
        "کوئی طریقہ بتائیں",
        "کوئی راستہ",
        # Arabic
        "ماذا أفعل",
        "ماذا افعل الآن",
        "ما العمل",
        "ما الحل",
        "كيف أحل هذه المشكلة",
        "كيف اصلح هذا",
        "كيف أتصرف",
        "أي حل",
        "هل من حل",
        "شو اسوي",
        "وش أسوي",
        "أحتاج حل",
        "اعطني نصيحة",
        "أعطني اقتراح",
    ],
)
def test_the_common_ways_of_asking_for_a_fix_are_recognised(said: str) -> None:
    assert solution_ask.asked_for_ideas(said), said


@pytest.mark.parametrize(
    "said",
    [
        # a refusal, "I do not know" or a story that happens to hold the words
        "koi hal nahi mil raha",
        "koi hal nahi",
        "koi tareeqa nahi",
        "koi tareeqa nahi hai humare paas",
        "maine koi hal nahi dekha",
        "wo log kuch batate hi nahi",
        "mera staff kuch batata nahi",
        "wo kuch bata nahi raha",
        "kuch batata nahi hai woh",
        "customer kuch bataye bina chala gaya",
        "kaise theek ho jata hai woh pata nahi",
        "koi tareeqa nahi aata",
        "kya kiya hai unhone",
        "kal kya kiya tha",
        "hal kar diya gaya",
        "ye theek hai",
        "ab fees late aati hai",
        "parents kya karte hain fee nahi dete",
        "mujhe kuch nahi pata",
        # the other scripts
        "کوئی حل نہیں",
        "کوئی طریقہ نہیں ہے",
        "कोई हल नहीं",
        "कोई तरीका नहीं मिला",
        "لا يوجد حل",
        "ما في حل",
        # plain statements and cost questions
        "mera business achha chal raha hai",
        "fee kitni hai",
        "we have a long list of customers who pay late and a few staff to chase them up",
    ],
)
def test_ordinary_sentences_are_not_an_ask(said: str) -> None:
    assert not solution_ask.asked_for_ideas(said), said


def test_a_long_story_with_a_weak_phrase_is_not_an_ask_but_a_strong_one_is() -> None:
    story = "customers keep saying koi hal chahiye but they never tell us what they want exactly"
    assert not solution_ask.asked_in_other_ways(story)
    assert solution_ask.asked_in_other_ways("fees late aati hain, ab kya karun")
