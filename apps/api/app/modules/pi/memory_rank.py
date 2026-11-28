"""Which remembered records a model call should see first (pure: no database, no model).

`shared_memory` hands a model about 1,800 characters of what pi knows about a customer. Until now
the records went in a fixed order (facts, problems, corrections ... messages) and the block was cut
from the END, so a long history lost exactly the records that were not at the top of that list,
whatever the owner had just asked. Long-term memory work (LongMemEval, ICLR 2025) names the same
weak spots: finding the one buried fact, joining facts from different sessions, knowing WHEN
something was said, preferring the newer value over the older one, and not mistaking a guess for
something the person said.

`order` ranks the records for the owner's latest message, with rules a person can read:

* a record that shares the message's rarer words comes first (rare words count more than "the");
* what the owner said or confirmed outranks a derived reading, which outranks a pi guess;
* a correction and a stated fact outrank a stored message or file name;
* a newer record beats an older one with the same words (a small bonus, never enough to beat a
  clearly more relevant record);
* the same thing said twice is kept once (the better ranked one).

It never drops a record by itself and never changes one: it only decides the order, so the cap in
`shared_memory._fit` removes the LEAST useful records. With no message it keeps the old order.
Everything here is data handling; the rules about what pi may say stay where they were.
"""

import math
import re
from collections import Counter
from collections.abc import Sequence
from datetime import date
from typing import Any

WORD = re.compile(r"\w+", re.UNICODE)
# words that say nothing about which record matters (English, plus common Roman Urdu glue words)
STOP = frozenset(
    "a an and are as at be been but by can did do does for from had has have he her his how i if "
    "in "
    "is it its me my of on or our she so that the their them they this to was we were what when "
    "where which who why will with you your about again also just not now than then there too very "
    "hai hain ka ki ke ko se mein me par pe aur ya kya kyun kyu kab kahan kaun ye yeh wo woh hum "
    "main mera meri mere aap apna apni apne tha thi the hoga hogi nahi nahin bhi to toh".split()
)
STATUS_WEIGHT = {
    "owner_said": 1.0,
    "confirmed": 1.0,
    "remembered": 0.9,
    "stored": 0.5,
    "derived": 0.5,
    "pi_inferred": 0.3,
    "page_read": 0.3,
}
SOURCE_WEIGHT = {
    "corrections": 0.5,
    "facts": 0.4,
    "problems": 0.3,
    "decisions": 0.3,
    "rejections": 0.3,
    "solutions": 0.2,
    "tried": 0.2,
    "files": 0.1,
    "messages": 0.0,
}
RELEVANCE = 4.0  # how much matching the message weighs next to status and source
RECENT = 0.25  # the most a newer date can add
SAME = 0.85  # share of words two records must share to be the same thing said twice


def stem(word: str) -> str:
    """A crude stem so "orders" matches "order" and "delivered" matches "delivering"."""
    for tail in ("ing", "ed", "es", "s"):
        if len(word) > len(tail) + 3 and word.endswith(tail):
            return word[: -len(tail)]
    return word


def tokens(text: str) -> list[str]:
    return [
        stem(w)
        for w in (m.lower() for m in WORD.findall(text or ""))
        if len(w) > 1 and w not in STOP
    ]


def _similar(a: set[str], b: set[str]) -> bool:
    return bool(a and b) and len(a & b) / min(len(a), len(b)) >= SAME


def order(records: Sequence[dict[str, Any]], query: str = "") -> list[dict[str, Any]]:
    """The records, most useful first for `query`. Without a query they stay in their own order."""
    items = list(records)
    asked = set(tokens(query))
    if len(items) < 2 or not asked:
        return items
    words = [set(tokens(str(r.get("text") or ""))) for r in items]
    seen = Counter(w for ws in words for w in ws)
    total = len(items)
    # rare words weigh more: a word in every record tells nothing, a word in one is a pointer
    idf = {w: math.log(1 + total / seen[w]) if seen[w] else 0.0 for w in asked}
    weight = sum(idf.values()) or 1.0
    newest = max((str(r.get("at") or "") for r in items), default="")
    scored: list[tuple[float, int]] = []
    for i, record in enumerate(items):
        match = sum(idf[w] for w in asked & words[i]) / weight
        score = (
            RELEVANCE * match
            + STATUS_WEIGHT.get(str(record.get("status") or ""), 0.4)
            + SOURCE_WEIGHT.get(str(record.get("source") or ""), 0.0)
        )
        score += RECENT * _recency(str(record.get("at") or ""), newest)
        scored.append((score, i))
    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    kept: list[int] = []
    for _, i in scored:
        if not any(_similar(words[i], words[j]) for j in kept):  # said twice: keep the better one
            kept.append(i)
    return [items[i] for i in kept]


def _recency(at: str, newest: str) -> float:
    """1.0 for the newest date in the block, 0 after a year or for a record with no date."""
    if len(at) < 10 or len(newest) < 10:
        return 0.0
    try:
        days = (date.fromisoformat(newest[:10]) - date.fromisoformat(at[:10])).days
    except ValueError:
        return 0.0
    return max(0.0, 1.0 - days / 365)
