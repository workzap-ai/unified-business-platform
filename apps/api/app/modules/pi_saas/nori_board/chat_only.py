"""Which of a registry person's messages are only conversation, and the acknowledgement pi sends.

A greeting, a thanks or an "ok" is kept in the chat for the team but does not become a requirement
card on the Nori Platform board (and is not sent to nori as one). The rule is deliberately plain and
deterministic: every word of the message is a known greeting or acknowledgement word, in English,
Roman Urdu or Urdu script, and it is short. Anything else, or any photo, voice note or file, is a
card. The word lists are small on purpose: a message that is not clearly a greeting is filed.
"""

import re

from app.modules.pi.language import detect_language, notice_in

_WORD = re.compile(r"[^\W_]+", re.UNICODE)
MAX_WORDS = 5

_WORDS = {
    # English
    "hello", "hi", "hey", "hii", "hiii", "helo", "good", "morning", "afternoon", "evening",
    "night", "thanks", "thank", "you", "thx", "ok", "okay", "k", "kk", "sure", "fine", "great",
    "cool", "nice", "yes", "yeah", "yep", "no", "nope", "hmm", "hmmm", "bye", "goodbye", "there",
    "pi", "a", "lot", "much", "so", "very", "sir", "madam", "maam", "team", "please", "pls",
    "welcome", "got", "it", "alright",
    # Roman Urdu
    "salam", "salaam", "assalam", "assalamu", "assalamualaikum", "assalamoalaikum", "aoa",
    "walaikum", "walaikumassalam", "alaikum", "slam", "shukriya", "shukria", "jazakallah",
    "theek", "thik", "hai", "han", "haan", "ji", "jee", "jani", "bhai", "acha", "accha", "achha",
    "bilkul", "khuda", "hafiz", "allah", "mehrbani", "meherbani", "nahi", "nahin", "g", "kia",
    "kya", "hal", "ap", "aap", "sab", "khair", "mubarak", "eid",
    # Urdu script
    "سلام", "السلام", "علیکم", "وعلیکم", "شکریہ", "ٹھیک", "ہے", "جی", "ہاں", "نہیں", "اچھا",
    "بہت", "خدا", "حافظ", "مہربانی", "آپ", "کیسے", "ہیں", "بھائی",
}  # fmt: skip


def is_chat_only(text: str | None) -> bool:
    words = [w.lower() for w in _WORD.findall(text or "")]
    if not words:
        return True  # emoji or punctuation only: conversation
    return len(words) <= MAX_WORDS and all(w in _WORDS for w in words)


# One acknowledgement per chat, in the person's language. Each says it is an AI (rule R-ID-01).
FILED_ACK = {
    "en": "I'm pi, an AI assistant. I've passed this to the Workzap team.",
    "roman_ur": "Main pi hoon, ek AI assistant. Maine yeh Workzap team ko bhej diya hai.",
    "ur": "میں pi ہوں، ایک AI اسسٹنٹ۔ میں نے یہ Workzap ٹیم کو بھیج دیا ہے۔",
}
CHAT_ACK = {
    "en": (
        "I'm pi, an AI assistant. The Workzap team reads what you write here. "
        "What would you like to tell them?"
    ),
    "roman_ur": (
        "Main pi hoon, ek AI assistant. Aap jo yahan likhenge Workzap team parhegi. "
        "Aap un se kya kehna chahte hain?"
    ),
    "ur": (
        "میں pi ہوں، ایک AI اسسٹنٹ۔ آپ جو یہاں لکھیں گے Workzap ٹیم پڑھے گی۔ "
        "آپ ان سے کیا کہنا چاہتے ہیں؟"
    ),
}


def ack_text(chat_only: bool, language: str | None, text: str | None) -> str:
    table = CHAT_ACK if chat_only else FILED_ACK
    return notice_in(table, language or detect_language(text))
