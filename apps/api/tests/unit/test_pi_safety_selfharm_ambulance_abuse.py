"""Self-harm, an ambulance asked for, and abuse said in the present, in Roman Urdu, Urdu, Hindi and
Arabic; and the ordinary business text that must not trip them."""

import pytest

from app.modules.pi import safety

E = safety.Emergency

YES = [
    ("mujhe marna hai", E.SELF_HARM),
    ("main khatam kar loon", E.SELF_HARM),
    ("jaan de dunga", E.SELF_HARM),
    ("khudkushi", E.SELF_HARM),
    ("zindagi khatam", E.SELF_HARM),
    ("ab jeena nahi chahta", E.SELF_HARM),
    ("مجھے مرنا ہے", E.SELF_HARM),
    ("جان دے دوں گا", E.SELF_HARM),
    ("میں زندگی ختم کر دوں", E.SELF_HARM),
    ("मुझे मरना है", E.SELF_HARM),
    ("मैं आत्महत्या करना चाहता हूँ", E.SELF_HARM),
    ("أريد الموت", E.SELF_HARM),
    ("سأقتل نفسي", E.SELF_HARM),
    ("ambulance chahiye", E.MEDICAL),
    ("ambulance chahiye abhi", E.MEDICAL),
    ("doctor chahiye abhi", E.MEDICAL),
    ("jaldi doctor bulao", E.MEDICAL),
    ("ایمبولینس چاہیے", E.MEDICAL),
    ("एम्बुलेंस चाहिए", E.MEDICAL),
    ("i am being abused at home", E.SAFEGUARDING),
    ("my husband keeps beating me", E.SAFEGUARDING),
    ("bachay ke saath zyadti ho rahi hai", E.SAFEGUARDING),
    ("mere saath marpeet ho rahi hai", E.SAFEGUARDING),
    ("sasural wale mujhe maar rahe hain", E.SAFEGUARDING),
    ("بچے کے ساتھ زیادتی ہو رہی ہے", E.SAFEGUARDING),
    ("बच्चे के साथ मारपीट हो रही है", E.SAFEGUARDING),
]


@pytest.mark.parametrize(("text", "kind"), YES)
def test_these_are_emergencies(text, kind):
    assert safety.emergency(text) is kind


@pytest.mark.parametrize(
    "text",
    [
        "death certificate ka quote chahiye",
        "rate marna band karo",
        "competitor ne price gira marna shuru kar diya",
        "marna hai to bata dein, quote bhej do",
        "ambulance ka quote chahiye",
        "ambulance chahiye, price aur service details bhej dein",
        "hamari company ko 3 ambulance chahiye, fleet order ke liye",
        "ambulance sales business ke liye model chahiye",
        "doctor chahiye clinic ke liye",
        "doctor ki website chahiye",
        "bachon ke school ka logo chahiye",
        "zindagi bima ka quote chahiye",
    ],
)
def test_ordinary_business_text_is_not_an_emergency(text):
    got = safety.emergency(text)
    assert got is None, (text, got)
