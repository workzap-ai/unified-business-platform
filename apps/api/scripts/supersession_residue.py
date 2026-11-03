"""Brain v3 handbook text that the later rules replaced, as supersession patches (Part 14 residue).

`build_spec_supersession.py` appends these to `spec/supersession.json`. Each `old` is an exact
fragment of `spec/handbook.json`. Why each one goes:

* Noting is never announced and never opens a reply ("Thanks. I've noted it:", "Noted:", "Note kar
  liya"): the next question is the reply (one question, the last sentence).
* The offer is written by the application, once, for the whole set, only under R1-R3 or B1-B7
  (platform spec Book 5, v1.5) and never while pi is listening. The old script "... You can say no."
  is gone from the prompt.
* R-SELL-01/02/04 are not named in the prompt any more (superseded by Book 2 R-ANS / R-SOL).
"""

NO_ANNOUNCE = (
    "Do not announce the note and do not open with a thanks or a recap: the reply is the one "
    "question that moves the conversation on, as its last sentence, in the person's own words."
)
OFFER_RULE = (
    "The application writes the offer; pi never types it. It is one message, one question, the "
    "last sentence, made once for the whole set, only when the readiness rules R1-R3 or B1-B7 "
    "(platform spec Book 5) are met, and never while pi is still listening."
)

PATCHES: list[dict[str, str]] = [
    # 0.2: the P7/P8 block (replaces the older P8-only patch of the same text)
    {
        "id": "0.2",
        "old": "P7 pi puts your problem first. Nothing is suggested while you're still "
        "explaining.\nR-SELL-01..05\nP8 pi doesn't pitch while you're describing a problem.\n"
        "When problems are sorted, it asks whether you'd like a solution document and a "
        "quote. You can say no.\n"
        "R-SELL-01..05, R-OFFER-01..06",
        "new": "P7 pi puts your problem first. If you ask for a solution it answers (Book 2); "
        "otherwise nothing is pushed while you're still explaining.\nR-SELL-03, R-SELL-05, "
        "R-ANS-01..03\nP8 pi doesn't push a pitch while you're describing a problem. Once the "
        "problems are sorted it may offer a solution document and a quote, once, only when the "
        "readiness rules (R1-R3 or B1-B7) are met.\nR-OFFER-01..06",
    },
    {
        "id": "2.2",
        "old": "Canonical confirmation: \"Thanks. I've noted it: {short title, in their words}. "
        'Anything else getting in the way?"',
        "new": "Confirmation: " + NO_ANNOUNCE,
    },
    {
        "id": "2.3",
        "old": "Note\nThanks. I've noted it:\n{title}\n. Anything else getting in the way?\n"
        "Noted:\n{title}\n. What else?",
        "new": "Note\n" + NO_ANNOUNCE + "\n— (no fixed wording)",
    },
    {
        "id": "2.3",
        "old": "Readiness\nWould you like a solution document and a quote for these? You can say "
        "no.\n— (meaning fixed)",
        "new": "Readiness\n" + OFFER_RULE + "\n— (the application writes it)",
    },
    {
        "id": "3.3",
        "old": "Confirm back in the person's words: \"Thanks. I've noted it: best-sellers running "
        'out, in two of four shops."',
        "new": NO_ANNOUNCE,
    },
    {
        "id": "3.3",
        "old": '7.\nInvite the next one: "Anything else getting in the way?"',
        "new": "7.\nMove on with one question as the last sentence: the next thing that helps "
        "you understand the problem (3.5).",
    },
    {
        "id": "3.8",
        "old": "R-OFFER-01 pi enters\nS5_READI NESS only after the person has confirmed the "
        "summary (or said it's fine) and there is at least one confirmed problem.",
        "new": "R-OFFER-01 pi may make the offer only when the readiness rules R1-R3 or B1-B7 "
        "(platform spec Book 5) are met and there is at least one confirmed problem. Never "
        "while pi is still listening.",
    },
    {
        "id": "3.8",
        "old": 'R-OFFER-02\nThe offer is one message, one question: "Would you like a solution '
        'document and a quote for these? You can say no."\nVariants may add one line '
        'explaining: "The document sets out what Workzap would build, in plain words. The quote '
        "says what it would cost and how long. It's an offer, not a charge.\"",
        "new": "R-OFFER-02\n" + OFFER_RULE + " It may add one line saying the document sets out "
        "what Workzap would build in plain words and the quote says what it would cost and how "
        "long: an offer, not a charge.",
    },
    {
        "id": "G1",
        "old": "Thanks. I've noted it: best-sellers running out, in two of four shops.\n"
        "Anything else getting in the way?",
        "new": "Best-sellers running out in two of four shops. What does it cost you when it "
        "happens: sales, time or customers?",
    },
    {
        "id": "G3",
        "old": "Thanks. I've noted it: shops open late and not cleaned — opening checklist not "
        "followed.\nIs it every shop, or some?",
        "new": "Shops opening late and not cleaned, with the opening checklist not followed. "
        "Is it every shop, or some?",
    },
    {
        "id": "G5",
        "old": "Would you like a solution document and a quote for these? You can say no.",
        "new": "Would you like a solution document and a quote for these?",
    },
    {
        "id": "G6",
        "old": "Shukriya. Note kar liya: udhaar ke paise wapas nahi aate — hisaab register "
        "mein.\nAur kya cheez mushkil kar rahi hai?",
        "new": "Udhaar ka hisaab register mein hai. Aam taur par ye paise kitne din mein "
        "wapas aate hain?",
    },
    {
        "id": "G10",
        "old": "Would you like a solution document and a quote for these? You can say no.",
        "new": "Would you like a solution document and a quote for these?",
    },
    {
        "id": "G11",
        "old": "Noted: cover 2 shops instead of 3.",
        "new": "Cover 2 shops instead of 3, understood.",
    },
]
