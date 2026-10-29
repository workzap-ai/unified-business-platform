"""A number the owner corrects ("not 10, 100", "10 nahi, 100", "no wait, it is 15 kg").

Platform spec B7.1/B7.3: a correction is kept, not lost. The saved problem must show the corrected
figure, the old figure stays in the revision history, and the reply must use the new figure.

Pure functions. `numeric_correction` finds (wrong, right) from the latest message and the owner's
earlier ones; it is deliberately strict (an explicit "not X, Y" pair, or a correction cue plus
an old number followed by the same word as the new one),
so an unrelated number is never swapped.
"""

import re

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
NUM = r"(\d[\d,]*(?:\.\d+)?)(?!\d)"
_NUMBER = re.compile(NUM)
NO = r"(?:nahi|nahin|nhi|nai|نہیں|نہی)"
CUE = re.compile(
    r"\b(?:not|no|sorry|correction|actually|wait|wrong|instead|rather|nahi|nahin|nhi|galat|ghalat)\b"
    r"|نہیں|غلط",
    re.IGNORECASE,
)
# "not 10, 100" / "not 10, it was 100" / "not 10 but 100"
NOT_THEN = re.compile(
    rf"\bnot\s+{NUM}\s*[,;:.،؛-]?\s*(?:but\s+|it\s+(?:was|is)\s+|its\s+|it's\s+)?{NUM}",
    re.IGNORECASE,
)
# "100, not 10"
THEN_NOT = re.compile(rf"{NUM}\s*[,;:.،؛-]?\s*not\s+{NUM}", re.IGNORECASE)
# "10 nahi, 100" / "nahi 20 nahi, 12" / "20 nahi 12 hain"
NUM_NAHI = re.compile(
    rf"{NUM}\s*{NO}\s*[,;:.،؛-]?\s*(?:it\s+(?:was|is)\s+|woh\s+|wo\s+|ye\s+|yeh\s+)?{NUM}",
    re.IGNORECASE,
)
_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)
STOP = frozenset("the and was are for with that this have has had not but its our their".split())


def norm(token: str) -> str:
    """A number as a comparable string: commas out, Eastern digits turned into 0-9, no zero tail."""
    whole, _, frac = token.translate(_DIGITS).replace(",", "").partition(".")
    whole = whole.lstrip("0") or "0"
    frac = frac.rstrip("0")
    return f"{whole}.{frac}" if frac else whole


def numbers_in(text: str) -> list[str]:
    return [norm(m) for m in _NUMBER.findall((text or "").translate(_DIGITS))]


def _following_word(text: str, number: str) -> str:
    """The first word after the number ("10 clients" gives "client"): the same fact?"""
    for m in _NUMBER.finditer((text or "").translate(_DIGITS)):
        if norm(m.group(1)) == number:
            tail = [w.casefold() for w in _WORD.findall(text.translate(_DIGITS)[m.end() :])]
            tail = [w for w in tail if w not in STOP]
            return tail[0][:5] if tail else ""
    return ""


def numeric_correction(latest: str, earlier: list[str]) -> tuple[str, str] | None:
    """(wrong, right) when the latest message corrects a number, else None."""
    text = " ".join((latest or "").translate(_DIGITS).split())
    if not text:
        return None
    for pattern, order in ((NOT_THEN, (0, 1)), (NUM_NAHI, (0, 1)), (THEN_NOT, (1, 0))):
        m = pattern.search(text)
        if m:
            wrong, right = norm(m.group(order[0] + 1)), norm(m.group(order[1] + 1))
            if wrong != right:
                return wrong, right
    if not CUE.search(text):
        return None
    mine = numbers_in(text)
    named = re.search(rf"\bnot\s+{NUM}", text, re.IGNORECASE)  # "5,000 subscribers, not 500"
    if named and len(set(mine)) == 2:
        wrong = norm(named.group(1))
        others = [n for n in dict.fromkeys(mine) if n != wrong]
        if len(others) == 1:
            return wrong, others[0]
    if len(set(mine)) != 1:
        return None
    right = mine[0]
    for old in reversed([e for e in earlier if e and e != latest]):
        olds = [n for n in dict.fromkeys(numbers_in(old)) if n != right]
        if not olds:
            continue
        word = _following_word(text, right)
        same = [n for n in olds if word and _following_word(old, n) == word]
        if len(same) == 1:
            return same[0], right
        return None  # the nearest earlier message with numbers does not match: do not guess
    return None


def standalone(number: str) -> re.Pattern[str]:
    """The number as its own figure: 10 matches "10 clients" but not "100", "10.5" or "5,10"."""
    plain = number.replace(".", r"\.")
    return re.compile(rf"(?<![\d.,]){plain}(?![\d]|[.,]\d)")


def has_figure(text: str, number: str) -> bool:
    return any(norm(n) == number for n in numbers_in(text))


def replace_figure(text: str, wrong: str, right: str) -> str:
    """The text with every standalone `wrong` figure (any comma style) written as `right`."""
    out, last = [], 0
    source = text or ""
    for m in _NUMBER.finditer(source):
        if norm(m.group(1)) == wrong:
            out.append(source[last : m.start()])
            out.append(right)
            last = m.end()
    out.append(source[last:])
    return "".join(out)


_ACK = re.compile(
    r"(?:\bnot\b|\binstead of\b|\brather than\b|\bnahi\b|\bnahin\b|\bnhi\b|\bnot\s+the\b)"
    r"[^.?!\n]{0,12}$",
    re.IGNORECASE,
)


def reply_problem(reply: str, wrong: str, right: str) -> str | None:
    """Why a reply to a correction cannot go: it does not use the new figure, or it still gives the
    old one as a fact ("not 10" or "instead of 10" is an acknowledgement, not a fact)."""
    if not has_figure(reply, right):
        return (
            f"the owner just corrected a figure to {right} (not {wrong}): the reply must use "
            f"{right}"
        )
    plain = reply.translate(_DIGITS)
    for m in _NUMBER.finditer(plain):
        if norm(m.group(1)) != wrong:
            continue
        before = plain[max(0, m.start() - 14) : m.start()]
        after = plain[m.end() : m.end() + 8]
        if _ACK.search(before) or re.match(r"\s*(?:nahi|nahin|nhi)\b", after, re.IGNORECASE):
            continue
        return (
            f"the owner corrected {wrong} to {right}, but the reply still gives {wrong} as a "
            f"fact: use {right} only"
        )
    return None


def superseded(old_word: str, new_texts: list[str], correction: bool) -> bool:
    """An earlier user_word that the correction replaces: it carries a figure that the new wording
    contradicts (a different figure about the same thing), so the record does not keep it as the
    current fact. It stays in the revision history, which holds the old list in full."""
    if not correction:
        return False
    old = set(numbers_in(old_word))
    new = {n for t in new_texts for n in numbers_in(t)}
    if not old or not new or old & new:
        return False
    stems = {w.casefold()[:5] for w in _WORD.findall(old_word) if len(w) >= 4} - STOP
    fresh = {w.casefold()[:5] for t in new_texts for w in _WORD.findall(t) if len(w) >= 4}
    return bool(stems & fresh)
