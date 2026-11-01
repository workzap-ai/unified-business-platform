# ruff: noqa: E501  (one fixed line per row reads better than wrapped text)
"""Two pre-model gates of brain mode, from a real production conversation.

1. A customer who paid ANOTHER company (a subscription app, a shop) and wrote to pi by mistake asking for
   a refund. pi is Workzap's AI, not that merchant: it says so in sentence one, says it cannot see, change
   or refund charges made by other companies or apps, points the customer to that company's own support
   (no invented contact details), offers a Workzap person for anything about Workzap, and does NOT guess
   why the other company charged them or ask about their phone or payment accounts. It claims no action.
   (`other_company_charge`, `other_company_reply`.)

2. A request for a supervisor, a manager or a person ("contact me with your supervisor", "manager se baat
   karao") is a hand-over: the fixed hand-over notice goes at once, in the customer's language, and the
   conversation is raised for staff. (`wants_human`.)

Pure and deterministic; the texts are fixed, with no question about the customer's phone or accounts, no
price and no offer.
"""

import re

WORKZAP = re.compile(r"work\s?zap", re.IGNORECASE)

# a refund or a charge dispute, in the words customers use (English, Roman Urdu, Urdu, Arabic, Hindi)
REFUND_WORDS = re.compile(
    r"\b(?:refund|refunds|money back|charge ?back|wrongly charged|charged me|deducted|"
    r"pais(?:a|e|ay|on)\s+(?:wapa(?:s|is)|kat)|paise?\s+wapa(?:s|is)|wapa(?:s|is)\s+(?:karo|kar do|chahiye|chahie)|"
    r"(?:rakam|raqam)\s+wapa(?:s|is)|refund chahiye|mera paisa)\b"
    r"|ریفنڈ|پیسے واپس|رقم واپس|پیسے کٹ|استرداد|استرجاع|رد المبلغ|اعادة المبلغ|रिफंड|पैसे वापस|पैसा वापस",
    re.IGNORECASE,
)

# someone asks for a supervisor, a manager or a person: a request, not a story about their own manager
HUMAN_ASK = re.compile(
    r"\b(?:(?:talk|speak|connect|transfer|contact|call|reach|get|put|bring)\b[^.?!\n]{0,30}"
    r"\b(?:supervisor|manager|human|person|agent|representative|someone senior|somebody senior|real person)"
    r"|your (?:supervisor|manager|boss)|(?:supervisor|manager) (?:please|now|only)"
    r"|real person|human agent|human being|live agent|customer care|someone senior)\b"
    r"|\b(?:supervisor|manager)\s+se\b|\binsaan se baat\b|\bbande se baat\b|\bkisi insaan se\b"
    r"|سپروائزر|مینیجر سے|مینیجر کو|کسی انسان سے|انسان سے بات"
    r"|(?:التحدث|الكلام|اتصل|تواصل)[^.?!؟\n]{0,25}(?:المشرف|مشرف|المدير|مدير|شخص|موظف)|المشرف|شخص حقيقي"
    r"|(?:सुपरवाइज़र|सुपरवाइजर|मैनेजर)\s*(?:से|को)|किसी इंसान से|इंसान से बात",
    re.IGNORECASE,
)

# an open Workzap payment or quote means a refund ask may well be about Workzap
WORKZAP_PAYMENT_STATES = (
    "S7_DELIVERED",
    "S8_NEGOTIATING",
    "S9_APPROVED",
    "S10_AWAITING_PAYMENT",
    "S11_PAYMENT_CONFIRMED",
    "S12_KICKOFF",
    "S13_IN_BUILD",
)


def wants_human(text: str) -> bool:
    """A short message that asks for a supervisor, a manager or a person."""
    said = " ".join((text or "").split())
    return 0 < len(said) <= 300 and bool(HUMAN_ASK.search(said))


def other_company_charge(text: str, context: dict) -> bool:
    """A refund or charge dispute that is not about Workzap: the message does not name Workzap and no
    Workzap quote or payment is open in this chat."""
    said = " ".join((text or "").split())
    if not said or not REFUND_WORDS.search(said) or WORKZAP.search(said):
        return False
    if context.get("open_quote"):
        return False
    state = str((context.get("flow") or {}).get("state") or "")
    return state not in WORKZAP_PAYMENT_STATES


OTHER_COMPANY_TEXT = {
    "en": "I'm pi, an AI from Workzap. I can't see, change or refund charges made by other companies or apps, so please contact that company's own support about it. If you want to ask something about Workzap, I can ask a Workzap person to help.",
    "roman_ur": "Main pi hoon, Workzap ka AI. Doosri companies ya apps ke charges yahan dekhe, badle ya wapas nahi kiye ja sakte, is liye is baare mein usi company ki support se rabta karein. Workzap ke baare mein kuch poochhna ho to Workzap ke kisi insaan se madad ke liye keh diya ja sakta hai.",
    "ur": "میں pi ہوں، Workzap کی طرف سے ایک مصنوعی ذہانت۔ دوسری کمپنیوں یا ایپس کے چارجز یہاں دیکھے، بدلے یا واپس نہیں کیے جا سکتے، اس لیے اس بارے میں اسی کمپنی کی اپنی سپورٹ سے رابطہ کریں۔ Workzap کے بارے میں کچھ پوچھنا ہو تو Workzap کے کسی فرد سے مدد کے لیے کہا جا سکتا ہے۔",
    "ar": "أنا pi، ذكاء اصطناعي من Workzap. لا يمكنني رؤية أو تغيير أو استرداد المبالغ التي حصّلتها شركات أو تطبيقات أخرى، لذلك يرجى التواصل مع دعم تلك الشركة نفسها. وإذا أردت السؤال عن Workzap فيمكنني أن أطلب من شخص في Workzap مساعدتك.",
}


def other_company_reply(language: str | None) -> str:
    return OTHER_COMPANY_TEXT.get(language or "en") or OTHER_COMPANY_TEXT["en"]


HANDOVER_TEXT = {
    "en": "Of course. I'm pi, an AI from Workzap, and I've asked a Workzap person to take over this chat. They'll reply here.",
    "roman_ur": "Zaroor. Main pi hoon, Workzap ka AI, aur maine Workzap ke kisi insaan se is chat par baat karne ko kaha hai. Wo yahin jawab dein ge.",
    "ur": "ضرور۔ میں pi ہوں، Workzap کی طرف سے ایک مصنوعی ذہانت، اور میں نے Workzap کے ایک فرد سے کہا ہے کہ وہ اس چیٹ پر بات کریں۔ وہ یہیں جواب دیں گے۔",
    "ar": "بالتأكيد. أنا pi، ذكاء اصطناعي من Workzap، وقد طلبت من شخص في Workzap أن يتولى هذه المحادثة. سيردّون هنا.",
}


def handover_reply(language: str | None) -> str:
    return HANDOVER_TEXT.get(language or "en") or HANDOVER_TEXT["en"]
