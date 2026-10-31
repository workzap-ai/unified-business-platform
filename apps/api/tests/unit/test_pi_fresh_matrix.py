"""L1 re-audit: my own fresh probe matrix (en / roman_ur / ur / ar / hi), built from other speakers,
other attribution verbs, hedges, denials, sarcasm, echoes, conditionals and attempt variants than
the auditor's list. A cause is the owner's only for a plain own claim; the default is pi_inferred.
An attempt is stored only with the owner as its subject."""

import itertools

import pytest

from app.modules.pi import problem_fields as pf
from app.modules.pi.problems import ProblemBook, ProblemNote


def status(word, text):
    cause, _ = pf.merge_cause(None, word, True, [word], "m1", text)
    return cause["status"]


def tried(what, text):
    note = ProblemNote(title="Sales fell", tried=[{"what": what, "outcome": ""}])
    got, _ = ProblemBook.requirement_values(note, None, "m", text)
    return got.get("tried") or []


# ------------------------------------------------------------------ causes that are NOT the owner's
ATTRIBUTED: list[tuple[str, str]] = []
for s, v in itertools.product(
    [
        "my brother",
        "the manager",
        "our landlord",
        "the delivery guy",
        "a friend",
        "my mother",
        "the bank",
        "the neighbour",
        "an expert",
        "the vendor",
        "clients",
        "staff",
        "investors",
        "the auditor",
    ],
    ["says", "said", "thinks", "believes", "told me", "claims"],
):
    ATTRIBUTED.append(("rent", f"{s} {v} the rent is the reason"))
for s, v in itertools.product(
    ["bhai", "manager", "landlord", "padosi", "dost", "ammi", "bank"],
    [
        "ne kaha ke",
        "keh raha hai ke",
        "kehte hain ke",
        "ka khayal hai ke",
        "ne bataya ke",
    ],
):
    ATTRIBUTED.append(("kiraya", f"{s} {v} kiraya wajah hai"))
for s, v in itertools.product(
    ["بھائی", "مینیجر", "مالک مکان", "پڑوسی", "دوست"],
    ["نے کہا کہ", "کہتا ہے کہ", "کہتے ہیں کہ", "کا خیال ہے کہ"],
):
    ATTRIBUTED.append(("کرایہ", f"{s} {v} کرایہ وجہ ہے"))
for s, v in itertools.product(
    ["أخي", "المدير", "جاري", "صديقي", "المورد"],
    ["قال إن", "يقول إن", "يعتقد أن", "قالوا إن"],
):
    ATTRIBUTED.append(("الإيجار", f"{s} {v} الإيجار هو السبب"))
for s, v in itertools.product(
    ["भाई", "मैनेजर", "पड़ोसी", "दोस्त"],
    ["ने कहा कि", "कहता है कि", "का मानना है कि"],
):
    ATTRIBUTED.append(("किराया", f"{s} {v} किराया वजह है"))

HEDGED: list[tuple[str, str]] = [
    ("rent", f"{p} the rent is the reason")
    for p in [
        "I don't think",
        "I'm not sure",
        "I doubt",
        "maybe",
        "perhaps",
        "probably not",
        "hmm,",
        "not certain",
        "who knows if",
        "I guess",
        "kind of",
        "possibly",
        "it seems like",
        "apparently",
    ]
]
HEDGED += [
    ("kiraya", f"{p} kiraya wajah hai")
    for p in [
        "mujhe nahi lagta ke",
        "shayad",
        "pata nahi ke",
        "yaqeen nahi hai ke",
        "ho sakta hai ke",
    ]
]
HEDGED += [
    ("کرایہ", f"{p} کرایہ وجہ ہے")
    for p in ["مجھے نہیں لگتا کہ", "شاید", "پتہ نہیں کہ", "یقین نہیں ہے کہ", "ہو سکتا ہے کہ"]
]
HEDGED += [
    ("الإيجار", f"{p} الإيجار هو السبب")
    for p in ["لا أعتقد أن", "ربما", "لست متأكد أن", "قد يكون", "لا أظن أن"]
]
HEDGED += [
    ("किराया", f"{p} किराया वजह है")
    for p in ["मुझे नहीं लगता कि", "शायद", "पता नहीं", "यकीन नहीं है कि", "हो सकता है कि"]
]
SARCASTIC = [
    ("rent", f"{p} it's the rent")
    for p in ["oh sure,", "yeah right,", "as if", "wow brilliant,", "haha"]
] + [("kiraya", f"{p} kiraya hi wajah hai") for p in ["haan haan,", "wah wah,", "kya baat hai,"]]
ECHOED = [
    ("rent", f"{p} the rent is the cause")
    for p in [
        "you asked whether",
        "you mentioned that",
        "you said maybe",
        "you suggested that",
        "your question was whether",
    ]
] + [
    ("kiraya", f"{p} kiraya wajah hai")
    for p in ["aap ne poocha ke", "aap ne kaha ke", "aapne bataya ke"]
]
CONDITIONAL = (
    [("rent", f"{p} the rent were the reason") for p in ["if", "what if", "suppose", "in case"]]
    + [("kiraya", f"{p} kiraya wajah ho") for p in ["agar", "kya"]]
    + [("کرایہ", f"{p} کرایہ وجہ ہو") for p in ["اگر", "کیا"]]
    + [("الإيجار", f"{p} الإيجار هو السبب") for p in ["إذا كان", "هل"]]
    + [("किराया", f"{p} किराया वजह हो") for p in ["अगर", "क्या"]]
    + [
        ("rent", "is the rent the reason?"),
        ("rent", "could it be the rent?"),
        ("rent", "do you think the rent is it?"),
        ("rent", "will the rent matter?"),
        ("rent", "why is the rent so high?"),
    ]
)
NEGATED = [
    ("rent", "the rent is not the reason"),
    ("rent", "it's not the rent"),
    ("rent", "not the rent"),
    ("rent", "no, the rent is not it"),
    ("kiraya", "kiraya wajah nahi hai"),
    ("کرایہ", "کرایہ وجہ نہیں ہے"),
    ("الإيجار", "ليس الإيجار هو السبب"),
    ("किराया", "किराया वजह नहीं है"),
]
NOT_OWNERS = ATTRIBUTED + HEDGED + SARCASTIC + ECHOED + CONDITIONAL + NEGATED

OWNERS = []
for p, (w, c) in itertools.product(
    ["I think", "I believe", "I feel", "in my view", "I'd say", "I reckon"],
    [
        ("rent", "the rent is the reason"),
        ("prices", "prices are too high"),
        ("staff", "the staff is slow"),
    ],
):
    OWNERS.append((w, f"{p} {c}"))
OWNERS += [
    ("rent", "I think the rent is too high"),
    ("prices", "I think our prices are too high"),
    ("staff", "I think my staff is slow"),
    ("stock", "I think we run out of stock"),
    ("location", "I think the location is bad"),
    ("delivery", "I think delivery takes too long"),
    ("ads", "I think our ads bring nobody"),
    ("app", "I think the app is broken"),
    ("quality", "I think the quality dropped"),
    ("competitor", "I think a competitor opened next door"),
    ("rent", "I think rent went up this year"),
    ("billing", "I think billing is manual"),
]
OWNERS += [
    ("kiraya", f"{p} kiraya zyada hai")
    for p in [
        "mera khayal hai ke",
        "mujhe lagta hai ke",
        "main samajhta hun ke",
        "humein lagta hai ke",
    ]
]
OWNERS += [
    ("staff", f"{p} staff slow hai")
    for p in [
        "mera khayal hai ke",
        "mujhe lagta hai ke",
        "main samajhta hun ke",
        "humein lagta hai ke",
    ]
]
OWNERS += [
    ("کرایہ", f"{p} کرایہ زیادہ ہے")
    for p in ["میرا خیال ہے کہ", "مجھے لگتا ہے کہ", "میں سمجھتا ہوں کہ"]
]
OWNERS += [("الإيجار", f"{p} الإيجار مرتفع") for p in ["أعتقد أن", "أظن أن", "في رأيي"]]
OWNERS += [("किराया", f"{p} किराया ज़्यादा है") for p in ["मुझे लगता है कि", "मेरा मानना है कि"]]


@pytest.mark.parametrize("word,text", NOT_OWNERS)
def test_matrix_not_the_owners_cause(word, text):
    assert status(word, text) == "pi_inferred", text


@pytest.mark.parametrize("word,text", OWNERS)
def test_matrix_the_owners_plain_claim(word, text):
    assert status(word, text) == "owner_said", text


# ------------------------------------------------------------------ attempts
OTHERS = [
    (w, f"{s} tried {w} and {o}")
    for s in [
        "my staff",
        "the supplier",
        "customers",
        "my partner",
        "the competitor",
        "my brother",
        "everyone",
        "nobody",
        "our agency",
        "the consultant",
    ]
    for w, o in [("flyers", "it did not work"), ("flyers", "it failed")]
]
NOT_DONE = [
    ("flyers", t)
    for t in [
        "I never tried flyers",
        "we haven't tried flyers yet",
        "I plan to try flyers",
        "we might try flyers",
        "I will try flyers soon",
        "we are going to try flyers",
        "I want to try flyers",
        "we have not tried flyers",
        "I hope to try flyers",
        "I've never tried flyers",
        "humne flyers try nahi kiye",
        "maine flyers kabhi aazmaye nahi",
        "hum flyers try karenge",
        "humne flyers abhi tak try nahi kiye",
        "flyers try karun ga",
        "ہم نے فلائر نہیں آزمائے",
        "میں نے کبھی فلائر نہیں آزمائے",
        "ہم نے فلائر آزمانے کا ارادہ کیا ہے",
        "لم أجرب الفلاير",
        "لم نجرب الفلاير",
        "سأجرب الفلاير",
        "हमने फ्लायर नहीं आज़माया",
        "मैंने कभी फ्लायर नहीं आजमाया",
        "हमने फ्लायर आज़माने का इरादा किया है",
    ]
]
NOT_DONE += [
    ("flyers", f"{s} flyers {v} lekin kaam nahi aaya")
    for s, v in [
        ("padosi ne", "aazmaye"),
        ("dost ne", "try kiye"),
        ("bhai ne", "aazmaye"),
        ("manager ne", "try kiye"),
        ("competitor ne", "aazmaye"),
    ]
]
NOT_DONE += [
    ("فلائر", "پڑوسی نے فلائر آزمائے"),
    ("فلائر", "دوست نے فلائر آزمائے"),
    ("فلائر", "منیجر نے فلائر آزمائے"),
    ("फ्लायर", "पड़ोसी ने फ्लायर आज़माए"),
    ("फ्लायर", "दोस्त ने फ्लायर आज़माए"),
    ("الفلاير", "جاري جرب الفلاير"),
    ("الفلاير", "أخي جرب الفلاير"),
    ("الفلاير", "المدير جرب الفلاير"),
    ("الفلاير", "هم جربوا الفلاير"),
]


@pytest.mark.parametrize("what,text", OTHERS + NOT_DONE)
def test_matrix_an_attempt_the_owner_did_not_make_is_not_stored(what, text):
    assert tried(what, text) == [], text


OWN = []
for s in ["I", "we"]:
    OWN += [
        ("flyers", f"{s} tried flyers and it did not work", "failed"),
        ("flyers", f"{s} tried flyers but it failed", "failed"),
        ("flyers", f"{s} tried flyers, no result", "failed"),
        ("flyers", f"{s} tried flyers, it was useless", "failed"),
        ("flyers", f"{s} tried flyers and it never worked", "failed"),
        ("flyers", f"{s} tried flyers and it worked well", "worked"),
        ("flyers", f"{s} tried flyers and it helped", "worked"),
        ("flyers", f"{s} tried flyers", ""),
    ]
OWN += [
    ("flyers", "humne flyers try kiye lekin kaam nahi aaya", "failed"),
    ("flyers", "humne flyers try kiye, fayda nahi hua", "failed"),
    ("flyers", "maine flyers aazmaye lekin nakam raha", "failed"),
    ("flyers", "maine flyers try kiye lekin bekaar raha", "failed"),
    ("flyers", "humne flyers try kiye aur bahut kaam aaya", "worked"),
    ("flyers", "humne flyers try kiye aur fayda hua", "worked"),
    ("فلائر", "ہم نے فلائر آزمائے لیکن ناکام رہا", "failed"),
    ("فلائر", "میں نے فلائر آزمائے کوئی فائدہ نہیں", "failed"),
    ("الفلاير", "جربنا الفلاير لكن لم ينجح", "failed"),
    ("الفلاير", "جربت الفلاير وفشل", "failed"),
    ("फ्लायर", "हमने फ्लायर आज़माए पर काम नहीं आया", "failed"),
    ("फ्लायर", "मैंने फ्लायर आजमाए लेकिन असफल", "failed"),
    ("flyers", "we tried flyers, it worked at first then stopped", "failed"),
    ("flyers", "we tried flyers and then it stopped working", "failed"),
]


@pytest.mark.parametrize("what,text,outcome", OWN)
def test_matrix_the_owners_own_attempt_is_stored_with_its_outcome(what, text, outcome):
    got = tried(what, text)
    assert len(got) == 1 and got[0]["outcome"] == outcome, (text, got)


def test_the_matrix_is_at_least_three_hundred_probes():
    assert len(NOT_OWNERS) + len(OWNERS) + len(OTHERS + NOT_DONE) + len(OWN) >= 300


# ------------------------------------------------------------------ second round: found by probing
# my own matrix (12 of these 24 were wrongly owner_said before the attribution lists were widened)
ADVERSARIAL = [
    ("rent", "the team reckons the rent is high"),
    ("rent", "word is that the rent is high"),
    ("rent", "rumour has it the rent is high"),
    ("rent", "everybody knows it's the rent"),
    ("rent", "according to my accountant the rent is high"),
    ("rent", "per the consultant the rent is high"),
    ("rent", "the report shows the rent is high"),
    ("rent", "analysis suggests rent is the issue"),
    ("rent", "my wife feels the rent is high"),
    ("kiraya", "bhai ko lagta hai kiraya zyada hai"),
    ("kiraya", "mera dost bolta hai kiraya zyada hai"),
    ("kiraya", "unka kehna hai kiraya zyada hai"),
    ("kiraya", "sab kehte hain kiraya zyada hai"),
    ("الإيجار", "الجميع يقول الإيجار مرتفع"),
    ("الإيجار", "حسب المحاسب الإيجار مرتفع"),
    ("किराया", "भाई को लगता है किराया ज़्यादा है"),
    ("किराया", "दोस्त बोलता है किराया ज़्यादा है"),
    ("किराया", "उनका कहना है किराया ज़्यादा है"),
    ("rent", "reportedly the rent is high"),
    ("rent", "allegedly the rent is high"),
    ("rent", "some say the rent is high"),
    ("rent", "my gut says the rent is high"),
    ("rent", "the data indicates rent is the cause"),
    ("rent", "our sales report says rent is high"),
]


@pytest.mark.parametrize("word,text", ADVERSARIAL)
def test_adversarial_attribution_is_not_the_owners_cause(word, text):
    assert status(word, text) == "pi_inferred", text


@pytest.mark.parametrize(
    "word,text",
    [
        ("kiraya", "mujhko lagta hai kiraya zyada hai"),
        ("kiraya", "mujh ko lagta hai kiraya zyada hai"),
        ("किराया", "मुझे लगता है किराया ज़्यादा है"),
        ("rent", "in my opinion the rent is high"),
    ],
)
def test_the_owners_own_belief_phrases_with_ko_are_still_theirs(word, text):
    assert status(word, text) == "owner_said", text
