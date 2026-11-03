"""Listening-reply tidy (real property-management chat, 2026-11-01).

Pure functions for four faults found in one live chat:

* a labelled section with nothing under it ("*Jo pata hai:*" and then the next label) never prints;
* a question that offers a list of choices ("apartments, houses ya commercial shops?") is dropped
  when the owner already named every choice, and a "pick one first" question is dropped when the
  owner said they do not want to pick (alreadyAnswered, spec v1.5 18.5);
* a cause stated as settled ("ab saaf hai", "the root cause is") is a hypothesis until the owner
  confirms it: the sentence goes;
* a reply to an owner who is still describing their business always ends with one question.
"""

import re

from app.modules.pi.script_words import fold, stem

_QMARKS = ("?", "؟")

# A label line: "*Jo pata hai:*", "*What I know:*", "Unknown:" and nothing after the colon.
LABEL_LINE = re.compile(r"^\s*[*_]*[^\n*_:?؟]{1,60}:[*_]*\s*$")
# The same label with its text on the same line is a sentence, not a bare heading.
_INLINE_LABEL = re.compile(
    r"^\s*(?P<bare>(?:[*_]{1,2})[^\n*_:?؟]{1,60}:(?:[*_]{1,2}))\s*(?P<rest>\S.*)$"
)
BULLET = re.compile(r"^\s*[•\-]\s+\S")


def split_inline_labels(text: str) -> str:
    """`*A:* *B:* text` on one line becomes one line per label (so an empty label can be seen)."""
    out: list[str] = []
    for line in (text or "").split("\n"):
        rest = line
        while (m := _INLINE_LABEL.match(rest)) and re.match(r"\s*[*_]", m.group("rest")):
            out.append(m.group("bare"))
            rest = m.group("rest")
        out.append(rest)
    return "\n".join(out)


def drop_empty_sections(text: str) -> str:
    """A bare label line followed by nothing, or by another bare label, is removed."""
    lines = split_inline_labels(text).split("\n")
    keep: list[str] = []
    for n, line in enumerate(lines):
        if LABEL_LINE.match(line):
            nxt = next((x for x in lines[n + 1 :] if x.strip()), "")
            if not nxt or LABEL_LINE.match(nxt) or _INLINE_LABEL.match(nxt):
                continue
        keep.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(keep)).strip()


# --- choice questions the owner already answered -----------------------------------------------

_OPTIONS = re.compile(
    r"([^\W\d_]+(?:\s+[^\W\d_]+)?)\s*,\s*([^\W\d_]+(?:\s+[^\W\d_]+)?)\s*"
    r"(?:,\s*)?(?:ya|or|aur|and|أو|یا)\s+([^\W\d_]+(?:\s+[^\W\d_]+)?)",
    re.IGNORECASE,
)
_DECLINES_PICK = re.compile(
    r"(?:pehle|poora|pura|puri|saara|saare|whole|entire|all of|sab(?:\s+kuch)?)\W+(?:\w+\W+){0,4}"
    r"(?:business|karobar|workflow|process|kaam)\b.{0,80}(?:samajh|understand|jaan)"
    r"|(?:samajh|understand)\w*.{0,40}(?:whole|poora|pura|puri|saara)\b"
    r"|\bpehle\b.{0,30}\b(?:solution|software|feature)s?\b.{0,20}\bnahi\b"
    r"|\b(?:no|not)\b.{0,20}\b(?:solution|software|features?)\b.{0,30}\b(?:yet|now|first)\b"
    r"|\bpick\b.{0,20}\b(?:nahi|not)\b|\bchoose\b.{0,20}\b(?:nahi|not)\b|\bsab\b.{0,10}\bek\s+saath\b",
    re.IGNORECASE,
)
_PICK_QUESTION = re.compile(
    r"\b(?:pehle|first)\b.{0,40}\b(?:kin|kis|kaun|kon|which|what)\b.{0,60}\b(?:shuru|start|begin)"
    r"|\b(?:kis|kin|which)\b.{0,40}\b(?:par|pe|se|one|of these)\b.{0,40}"
    r"\b(?:shuru|start|first|pehle)\b"
    r"|\b(?:shuru|start)\b.{0,30}\b(?:kis|kin|kaun)\b",
    re.IGNORECASE,
)


def _questions(reply: str) -> list[str]:
    return [
        p for p in re.split(r"(?<=[.!?؟۔。！])\s+", (reply or "").strip()) if p.endswith(_QMARKS)
    ]


def _key(word: str) -> str:
    return stem(fold(word.split()[-1]))[:4]


def choice_answered(question: str, owner_texts: list[str]) -> bool:
    """The question lists three or more choices and every one of them is in the owner's words."""
    theirs = fold(" ".join(owner_texts))
    for m in _OPTIONS.finditer(question):
        keys = [_key(g) for g in m.groups()]
        if all(len(k) >= 3 and k in theirs for k in keys):
            return True
    return False


def owner_declines_pick(owner_texts: list[str]) -> bool:
    return bool(_DECLINES_PICK.search(" ".join(owner_texts)))


def answered_questions(reply: str, owner_texts: list[str]) -> list[str]:
    """The questions in a reply the owner already answered (or refused to pick for)."""
    declines = owner_declines_pick(owner_texts)
    return [
        q
        for q in _questions(reply)
        if choice_answered(q, owner_texts) or (declines and _PICK_QUESTION.search(q))
    ]


def without_answered_questions(reply: str, owner_texts: list[str]) -> str:
    text = reply
    for q in answered_questions(reply, owner_texts):
        text = text.replace(q, "")
    return re.sub(r"[ \t]+\n", "\n", re.sub(r"\n{3,}", "\n\n", text)).strip()


# --- a cause stated as settled -----------------------------------------------------------------

CAUSE_SETTLED = re.compile(
    r"\bab\s+saaf\s+(?:hai|hua|ho\s+gaya)\b|\bsaaf\s+hai\s+ke\b|\bwajah\s+(?:ye|yeh)\s+hai\b"
    r"|\b(?:the\s+)?root\s+cause\s+is\b|\bit(?:'s| is)\s+(?:now\s+)?clear\s+(?:now\s+)?that\b"
    r"|\bthe\s+(?:real\s+)?(?:reason|cause)\s+is\b|\bthat\s+(?:explains|confirms)\s+why\b",
    re.IGNORECASE,
)


def settled_cause(reply: str) -> str | None:
    if CAUSE_SETTLED.search(reply or ""):
        return (
            "it states a cause as settled ('ab saaf hai', 'the root cause is'). A cause stays a "
            "guess until the owner confirms it: restate only what the owner said, then ask one "
            "question"
        )
    return None


def without_settled_cause(reply: str) -> str:
    """The sentences that state a cause as settled are removed."""
    parts = re.split(r"(?<=[.!?؟])\s+", (reply or "").strip())
    kept = [p for p in parts if not CAUSE_SETTLED.search(p)]
    return " ".join(kept).strip()


def has_question(reply: str) -> bool:
    return any(q in (reply or "") for q in _QMARKS)


RECAP_LABEL = re.compile(
    r"pata\s+hai|maloom|maaloom|jaante|unknown|know|confirm|noted|samjha|samjhi|understood|"
    r"missing|still\s+need|baaqi|ma.?loom",
    re.IGNORECASE,
)


def is_recap_list(lines: list[str], first_bullet: int) -> bool:
    """The bullets sit under a label such as "*Jo pata hai:*" or "What I know:": a recap of the
    owner's facts, not a list of ideas."""
    before = first_bullet - 1
    while before >= 0 and not lines[before].strip():
        before -= 1
    return before >= 0 and bool(
        LABEL_LINE.match(lines[before]) and RECAP_LABEL.search(lines[before])
    )
