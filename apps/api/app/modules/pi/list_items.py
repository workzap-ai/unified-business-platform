"""B1: when the owner lists several things, none may be dropped between their message and the notes.

Pure functions. `items` cuts a message that is a list (bullets, numbers, or several short lines)
into candidate items, each with a stable id and the figures it carries. `dropped` says which items
no note of this turn (or an earlier one) mentions, by a figure or by content words. The model still
writes the notes; this only catches an item that fell between the message and the record, so the
caller can ask for it in the one rewrite. Nothing here invents a note.
"""

import re
from dataclasses import dataclass
from typing import Any

MIN_ITEM_WORDS = 3  # a shorter line is a heading or an aside, not an item
MIN_ITEMS = 2  # one line is a sentence, not a list
MAX_REPORTED = 4
STEM = 5
BULLET = re.compile(r"^\s*(?:[-•*–—▪●]|\d{1,2}\s*[.)]|[a-zA-Z]\s*[.)])\s+")
INLINE_NUMBER = re.compile(r"(?:(?<=\s)|^)(\d{1,2})\s*[.)]\s+(?=\S)")
FIGURE = re.compile(r"\d[\d,]*(?:\.\d+)?")
WORD = re.compile(r"\w+", re.UNICODE)
UNSPACED = re.compile(r"[぀-ヿ㐀-鿿가-힯฀-๿]")
STOPWORDS = frozenset(
    """about after again also because been before being could does doing from have having here
    just like make more much only other over really should some such than that their them then
    there these they this those very want what when where which while will with would your
    aap apni apna apne bhi hai hain hota hote hoti kar karna karne karta karte karti kaise kia
    kya kyun kyunke lekin mera meri mere mujhe nahi phir sab thi thha unka unki unke wala wali
    wale yeh woh aur bas bohat bahut abhi jab tak toh agar""".split()
)


@dataclass(frozen=True)
class Item:
    id: str  # c1, c2 ...: stable for one message, in the owner's order
    text: str
    figures: tuple[str, ...]


def _words(text: str) -> set[str]:
    return {
        w[:STEM]
        for w in (m.group(0).casefold() for m in WORD.finditer(text))
        if len(w) >= 4 and not w.isdigit() and w not in STOPWORDS
    }


def _figures(text: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(f.replace(",", "") for f in FIGURE.findall(text)))


def _enough(text: str) -> bool:
    return len(WORD.findall(text)) >= MIN_ITEM_WORDS


def _split(message: str) -> list[str]:
    lines = [ln for ln in (message or "").splitlines() if ln.strip()]
    marked = [BULLET.sub("", ln, count=1).strip() for ln in lines if BULLET.match(ln)]
    if len(marked) >= MIN_ITEMS:
        return marked
    inline = list(INLINE_NUMBER.finditer(message or ""))
    if len(inline) >= MIN_ITEMS and [m.group(1) for m in inline][:2] == ["1", "2"]:
        starts = [m.end() for m in inline] + [len(message)]
        return [
            message[
                start : (inline[i + 1].start() if i + 1 < len(inline) else len(message))
            ].strip()
            for i, start in enumerate(starts[:-1])
        ]
    long_lines = [ln.strip() for ln in lines if _enough(ln)]
    return long_lines if len(lines) >= 3 and len(long_lines) >= 3 else []


def items(message: str) -> list[Item]:
    """The candidate items of a message that is a list, oldest first; [] when it is not a list."""
    if UNSPACED.search(message or ""):
        return []  # words cannot be compared in these scripts: stay out of it
    found = [part for part in _split(message) if _enough(part)]
    if len(found) < MIN_ITEMS:
        return []
    return [Item(f"c{i}", part, _figures(part)) for i, part in enumerate(found, 1)]


def covered(item: Item, notes: list[str]) -> bool:
    """A note mentions the item: it carries one of its figures, or shares enough content words."""
    said = " ".join(notes)
    if item.figures and any(f in said.replace(",", "") for f in item.figures):
        return True
    wanted = _words(item.text)
    if not wanted:
        return True  # nothing to compare: do not flag what cannot be checked
    have = _words(said)
    need = 2 if len(wanted) >= 4 else 1
    return len(wanted & have) >= need


def dropped(message_texts: list[str], notes: list[str]) -> list[Item]:
    """The items of the owner's list that no note mentions. `notes` is the text of every note of
    this turn plus the problems already noted (title, summary, their own words)."""
    missing: list[Item] = []
    for text in message_texts:
        missing.extend(it for it in items(text) if not covered(it, notes))
    return missing


def reason(missing: list[Item]) -> str | None:
    """The sentence for the rewrite request, or None when nothing is missing."""
    if not missing:
        return None
    shown = "; ".join(f"'{it.text[:80]}'" for it in missing[:MAX_REPORTED])
    more = len(missing) - MAX_REPORTED
    tail = f" (and {more} more)" if more > 0 else ""
    return (
        f"the owner listed items that are not in your notes: {shown}{tail}. Note each one with "
        "problem_ops (their own words and figures), or ask one question about it. Do not drop one"
    )


LISTENING = frozenset(
    {"S1_LISTENING", "S2_CLARIFYING", "S3_NOTED", "S4_SORTED_SUMMARY", "S_LISTEN_THINK"}
)


def _note_text(note: object) -> str:
    parts = [
        str(getattr(note, name, "") or "")
        for name in ("title", "title_local", "summary", "of_total", "money_text", "products")
    ]
    parts.append(" ".join(str(w) for w in getattr(note, "user_words", None) or []))
    return " ".join(parts)


def guard(context: dict[str, Any], ops: list[Any]) -> str | None:
    """The rewrite reason when the owner's list lost an item between the message and the notes.
    Only in brain mode, while listening, and only for a workspace that turned `list_guard` on."""
    if context.get("pi_mode") != "brain" or not context.get("list_guard"):
        return None
    if (context.get("flow") or {}).get("state", "") not in LISTENING:
        return None
    texts = [
        *(str(t) for t in context.get("burst_texts") or []),
        str(context.get("latest_customer_message") or ""),
    ]
    notes = [_note_text(op.note) for op in ops if getattr(op, "note", None) is not None]
    notes += [
        " ".join(str(p.get(k) or "") for k in ("title", "summary"))
        for p in context.get("noted_problems") or []
    ]
    return reason(dropped(texts, notes))
