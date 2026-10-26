"""pi gives an industry idea only when the problem really fits (the live chats of 2026-10-26 got
"exchange request" ideas for "price asked, then silence" and "shift rota" ideas for theft).

Two measured numbers, on every industry pack, with a fixed seed:
- RECALL: a problem put in its own words finds its own entry (must stay near 100%).
- FALSE MATCH: a problem of industry A put to industry B must NOT be served an entry that shares no
  content word with what the person said. On 2026-10-26 that happened for 65% of the entries
  served (1,139 of 1,749 probes). The ceiling below is a ratchet: it may only go DOWN, and the goal
  is under 5%. A higher ceiling is never the fix."""

import random
import re

from app.modules.pi import solution_ideas as si
from app.modules.pi import solutions

STOP = set(
    (
        "the and for with that this have from your you but not are was were our their they them "
        "what when how all any can will would into out too very much many one aur hai hain nahi "
        "ka ki ke ko se mein par ye woh kya kuch bhi"
    ).split()
)
FALSE_MATCH_CEILING = 0.66  # share of served entries with no shared content word (goal: 0.05)


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{4,}", text.lower()) if w not in STOP}


def _industries() -> dict[str, list[dict]]:
    return {i: (solutions.load(i) or {}).get("problems") or [] for i in solutions.industries()}


def test_a_problem_in_its_own_words_finds_its_own_entry():
    found = total = 0
    for problems in _industries().values():
        for entry in problems:
            if entry.get("words"):
                total += 1
                m = si.match_problem(problems, "", "", entry["words"])
                found += bool(m and m["id"] == entry["id"])
    assert total >= 2000 and found / total >= 0.98


def test_an_entry_that_shares_no_word_with_the_person_is_rarely_served():
    random.seed(11)
    data = _industries()
    names = list(data)
    served = irrelevant = 0
    for _ in range(3000):
        a, b = random.sample(names, 2)
        src = random.choice(data[a])
        if not data[b] or not src.get("words"):
            continue
        m = si.match_problem(data[b], src.get("category", ""), src.get("subtype", ""), src["words"])
        if m is not None:
            served += 1
            irrelevant += not (_tokens(src["words"]) & _tokens(m.get("words", "")))
    share = irrelevant / max(served, 1)
    assert served > 0
    assert share <= FALSE_MATCH_CEILING, (
        f"{share:.0%} of served entries share no word with the person"
    )
