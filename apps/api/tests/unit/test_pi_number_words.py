"""Amounts written as number words must be refused in every price mode, and counts of things
(two ideas, ten minutes, Step three, hundred percent sure) must keep passing."""

import itertools

import pytest

from app.modules.pi import number_words, price_policy
from app.modules.pi.guard import ReplyRejected
from app.modules.pi.service_conversation import validate_service_reply

MODES = ["quote", "hidden", "ask_team", "starting", "exact"]

AMOUNTS = [
    "five hundred",
    "panch sau",
    "quinientos euros",
    "a grand",
    "half a grand",
    "just five hundred",
    "five hundred and fifty",
    "five-hundred",
    "fivehundred",
    "pāñch sau",
    "tenner",
    "fiver",
    "a hundred",
    "¹⁰⁰",
    "①⓪⓪",
    "five hundred rupees",
    "pachaas rupay",
    "do sau rupay",
    "the price is two hundred",
    "it costs just five hundred",
    "fifty euros",
    "ten bucks",
    "cinq cents euros",
    "cinquante euros",
    "پانچ سو روپے",
    "خمسمائة ريال",
    "पाँच सौ रुपये",
    "monthly five hundred",
    "five hundred per month",
    "sasta hai, teen sau",
    "kitne ka hai, do sau",
]


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("amount", AMOUNTS)
def test_written_amounts_are_refused_in_every_mode(amount: str, mode: str) -> None:
    with pytest.raises(ReplyRejected):
        validate_service_reply(f"Sure. {amount} for you.", 4000, mode)


NEGATIVES = [
    "I'm an AI. Which of these two costs you the most?",
    "One question: what is the biggest problem?",
    "I have two ideas for you.",
    "Three problems so far: stock, cash and staff.",
    "ek sawal: aap ka kaam kab shuru hota hai?",
    "do ideas hain mere paas.",
    "teen masail note kiye hain.",
    "What was the first thing you tried?",
    "Are you sure? Hundred percent sure?",
    "I am a hundred percent sure this helps.",
    "Thanks, a thousand thanks for explaining.",
    "That takes ten minutes.",
    "Five days is enough to try it.",
    "You said you run two shops.",
    "Part five is about stock.",
    "Step three is checking the register.",
    "مسئلہ نمبر دو کیا ہے؟",
    "دو دکانیں ہیں آپ کیں؟",
    "تین مسائل نوٹ کیے گئے ہیں۔",
    "Nine out of ten days the shop opens late.",
    "Can you tell me about your two busiest days?",
    "Which one of the three hurts most?",
    "I noted four things and will ask about one.",
    "We talked for twenty minutes yesterday.",
    "You have six staff and two cashiers.",
    "Is it the second one or the third?",
    "Tell me about the last ten customers who left.",
    "Seven of them came back, right?",
    "How long have you had the shop, three years or more?",
    "Do you open six days a week?",
    "aap ke paas kitne log hain, paanch ya chhe?",
    "Mere do dost yehi kaam karte hain.",
    "Hum teen log hain.",
    "Sau fisad yaqeen hai ke yeh chalega.",
    "Chaar din mein wapas ayen.",
    "Ek minute, main dekhta hoon.",
    "Aap ke do bhai kaam karte hain?",
    "Tres problemas anotados. ¿Cuál es el primero?",
    "Dos tiendas, ¿verdad?",
    "J'ai deux idées pour vous.",
    "Trois problèmes notés. Lequel est le premier ?",
    "Cent pour cent sûr que ça aide.",
    "Zwei Ideen habe ich.",
    "I will ask one thing at a time.",
    "A grand idea, tell me more.",
    "A grand opening is a big day for a shop.",
    "Fifty people visit the shop each day, is that right?",
    "Five hundred customers is a lot of people to remember.",
    "You have a hundred items on the shelf, which sells slowest?",
    "Two apps cost you time, which is worse?",
    "Eight hours of work, how many are spent on paperwork?",
    "Take ten deep breaths first.",
    "Section two covers the register.",
    "Question three: who closes the shop?",
    "Chapter nine, page ten.",
    "Number two on your list was stock, right?",
    "I understand. Seventy percent of the day goes on that?",
    "Thirty seconds to explain: what does a normal day look like?",
    "Both of the two shops share one stockroom?",
    "Do you want me to look at one of them first?",
    "Is that one cost for the whole shop?",
    "Do the price list first, then the stock.",
    "Option two is the cheaper one.",
    "That sounds grand.",
    "We have five hundred and fifty customers.",
    "A hundred and fifty items sit on the shelf.",
    "Sure, a hundred percent.",
    "Sau fisad, per cent sure.",
]

THINGS = [
    "ideas",
    "problems",
    "shops",
    "customers",
    "minutes",
    "days",
    "staff",
    "questions",
    "branches",
    "people",
    "weeks",
    "tables",
]
WORDS = [
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "twelve",
    "twenty",
    "fifty",
]
GENERATED = [
    f"We talked about {w} {noun} today, which one matters most?"
    for w, noun in itertools.product(WORDS, THINGS[:10])
] + [f"Panch {noun} hain, pehla kaun sa hai?" for noun in ("masail", "dukanen", "log", "din")]
ROMAN = [
    "ek",
    "do",
    "teen",
    "char",
    "panch",
    "chhe",
    "saat",
    "aath",
    "das",
    "bees",
]
GENERATED += [
    f"{w} {noun} ke baare mein batayein."
    for w, noun in itertools.product(ROMAN, ("masail", "log", "din"))
]
ALL_NEGATIVES = NEGATIVES + GENERATED


def test_negative_set_is_large_enough() -> None:
    assert len(ALL_NEGATIVES) >= 150


@pytest.mark.parametrize("text", ALL_NEGATIVES)
def test_counts_and_labels_are_not_amounts(text: str) -> None:
    assert not number_words.has_amount(text), text
    assert not number_words.variant_digits(text), text


@pytest.mark.parametrize("text", ALL_NEGATIVES)
def test_number_words_add_no_false_block(text: str) -> None:
    """The number-word hook alone must not block any of these."""
    assert "number_words" not in price_policy.disclosures(text)


def test_fixed_lines_stay_exempt() -> None:
    reply = "Your quote Q-12 total five hundred rupees is with the team."
    validate_service_reply(reply, 4000, "quote", [reply])


def test_slang_and_variants() -> None:
    assert number_words.has_amount("a tenner")
    assert number_words.has_amount("fivehundred")
    assert number_words.has_amount("five-hundred")
    assert number_words.variant_digits("¹⁰⁰")
    assert not number_words.variant_digits("1 ² note")
    assert not number_words.has_amount("a grand idea")
    assert number_words.fold("pāñch") == "panch"
