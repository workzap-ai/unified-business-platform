# ruff: noqa: E501
"""The idea filter of the platform spec Book 5, 7.1 (G1 to G9).

`solution_rules.check_idea` already covers honesty (G6) and no how-to (G5), and the free idea
vetting covers "uses something the person said". This module adds the rest, from the live chats:

- G1 goal: a "keep a buffer back" idea for someone who wants to clear stock.
- G2 grounded: "online launches" or "a website shop" for a business that never mentioned either.
- G3 sub-type: a stock-sync idea for a stock-clearing problem.
- G4 cause-fit: an idea that assumes a cause the owner did not give (or one other than theirs).
- G7 new: an idea that repeats one already given in the conversation.
- G8 on the map: an idea for a problem the owner never raised.
- G9 vocabulary: an idea in another trade's words (`idea_vocabulary`), when the trade is known.

G1 and G2 need only the owner's words. G3, G4, G7 and G8 need what the conversation holds (the noted
problems with their sub-type, goal verb and cause, the ideas already given, the map nodes), passed
as an `IdeaContext`; with none they are skipped, so a caller that has no such data behaves as before.

Pure functions. An idea that fails is dropped; if every idea fails pi asks for one more fact
(`need_fact_line`): it never gives a weak idea."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.modules.pi import idea_vocabulary, solution_ideas, solution_library, taxonomy

# A goal verb and the ideas that work against it.
_AGAINST_CLEARING = re.compile(
    r"\b(?:buffer|safety stock|stock up|order more|re-?order|keep (?:a )?(?:little|some|extra) "
    r"(?:stock )?(?:back|in reserve)|hold back|keep stock back)\b",
    re.IGNORECASE,
)
_AGAINST_KNOWING = re.compile(
    r"\b(?:discount|clearance|sale|mark(?:ing)? down|cut (?:the )?price)\b", re.IGNORECASE
)
_AGAINST_COLLECTING = re.compile(
    r"\b(?:give (?:more )?credit|extend (?:the )?credit|longer terms|offer (?:a )?discount for "
    r"(?:new|more) (?:orders|sales))\b",
    re.IGNORECASE,
)
_AGAINST = {
    "sell_clear": _AGAINST_CLEARING,
    "know_track": _AGAINST_KNOWING,
    "collect_cash": _AGAINST_COLLECTING,
}

# Context an idea must not bring in unless the owner said it (G2).
_INVENTED_CONTEXT = re.compile(
    r"\b(?:web ?site|online (?:store|shop|launch(?:es)?|sales?)|e-?commerce|webshop|web shop|"
    r"social media (?:ads?|campaign)|influencers?|franchis(?:e|es|ing)|export(?:s|ing)?)\b",
    re.IGNORECASE,
)

# --- G3: the idea belongs to the problem's sub-type ---------------------------------------------
# What is distinctive of an idea for each sub-type. An idea that is distinctive of ANOTHER sub-type
# and not of the problem's own fails ("keep the shop and warehouse counts in step" for clearing).
_SUBTYPE_MARKS: dict[str, re.Pattern[str]] = {
    "overstock_ageing": re.compile(
        r"\b(?:oldest|aged|ageing|aging|by age|age and|slow[- ]moving|dead stock|"
        r"(?:old|aged|slow) (?:stock|lines?|sets?|items?)|clear(?:ing)? the (?:old|stock))\b",
        re.IGNORECASE,
    ),
    "stockout": re.compile(
        r"\b(?:re-?order|running out|runs? out|minimum level|restock|low[- ]stock|reorder level)\b",
        re.IGNORECASE,
    ),
    "no_visibility": re.compile(
        r"\b(?:tally|stock (?:count|register|record|book)|count (?:the |all )?(?:stock|shelves)|"
        r"shelf count|one list of (?:what|all))\b",
        re.IGNORECASE,
    ),
    "stock_sync": re.compile(
        r"\b(?:sync\w*|in step|same (?:number|count)s? (?:in|across|at)|reconcile|"
        r"match(?:ing)? the (?:shop|online|outlet|warehouse)s? (?:count|figures?|numbers?)|"
        r"(?:counts?|stock levels?) (?:between|across) (?:the )?(?:warehouse|outlets?|shops?|channels?))\b",
        re.IGNORECASE,
    ),
}

# --- G4: the idea fits the known cause, or helps whatever the cause is ---------------------------
_CAUSE_WORDS: dict[str, re.Pattern[str]] = {
    "price": re.compile(
        r"\b(?:price|qeemat|qimat|mehng\w*|expensive|costly|too high|rate)\b", re.IGNORECASE
    ),
    "design": re.compile(
        r"\b(?:design\w*|style|fashion|purane|outdated|old[- ]fashioned|pasand)\b", re.IGNORECASE
    ),
    "season": re.compile(r"\b(?:season\w*|weather|mausam|winter|summer|eid)\b", re.IGNORECASE),
    "awareness": re.compile(
        r"\b(?:pata nahi|nobody knows|not know|unaware|dekhte nahi|don'?t know about|reach)\b",
        re.IGNORECASE,
    ),
}
_IDEA_ASSUMES: dict[str, re.Pattern[str]] = {
    "price": re.compile(
        r"\b(?:lower the price|cut the price|price cut|mark(?:ing)? down|discount\w*|cheaper|"
        r"lower rate|reduce the price)\b",
        re.IGNORECASE,
    ),
    "design": re.compile(
        r"\b(?:redesign\w*|restyle|refresh the (?:look|design|style)|new look|update the designs?|"
        r"alter the|repackage|modernis\w*|new designs?)\b",
        re.IGNORECASE,
    ),
    "season": re.compile(
        r"\b(?:wait for the (?:season|winter|summer|eid)|seasonal|(?:before|ahead of) (?:the )?"
        r"(?:season|winter|summer|eid)|hold (?:it )?until)\b",
        re.IGNORECASE,
    ),
    "awareness": re.compile(
        r"\b(?:tell (?:more )?people|let (?:people|customers|everyone) know|announce\w*|"
        r"spread the word|advertis\w*|short videos?|reels?)\b",
        re.IGNORECASE,
    ),
}
# An idea that is useful under most causes (spec 7.5): look at the facts, group, test small.
_ROBUST = re.compile(
    r"\b(?:by age|group the|sort the|test (?:one|a single|it)|in one (?:outlet|shop|branch)|"
    r"count|tally|note down|write down|compare|find out why|see (?:which|what|how)|ask (?:a few|ten|some) "
    r"(?:customers|buyers|people))\b",
    re.IGNORECASE,
)

# --- G7: the idea is new ---------------------------------------------------------------------------
SAME_IDEA = 0.7  # share of the idea's content words found in one idea already given

# --- G8: the idea relates to a node on the map -------------------------------------------------------
# Words that belong to a goal even when the owner's own words for the node do not repeat them.
_GOAL_VOCAB: dict[str, str] = {
    "sell_clear": "sell clear sale offer oldest bundle outlet clearance",
    "know_track": "count record track list tally know",
    "avoid_running_out": "reorder running low stock supplier level fast sellers",
    "bring_back": "repeat return regular message remind",
    "collect_cash": "collect payment owed reminder dues credit",
}


@dataclass(frozen=True)
class IdeaContext:
    """What the conversation holds that G3, G4, G7 and G8 judge an idea against."""

    subtype: str = ""  # the problem's sub-type (the goal verb's sort overrides the model's guess)
    goal_verb: str = ""
    cause: str = ""  # what the owner believes or gave as the cause; "" when unknown
    entry_ideas: tuple[str, ...] = ()  # the ideas of the industry entry for this sub-type
    given: tuple[str, ...] = ()  # ideas (and replies) already given in this conversation
    nodes: tuple[str, ...] = ()  # the words of each node on the map
    industries: tuple[str, ...] = ()  # the trade(s) pi is talking about (G9); () when unknown
    node_categories: tuple[str, ...] = ()  # the category of each node

    def active(self) -> bool:
        return bool(self.subtype or self.cause or self.given or self.nodes)


def goal_conflict(idea: str, owner_words: str) -> str | None:
    """G1: the rule id when the idea works against what the owner wants, else None."""
    sort = taxonomy.goal_sort(owner_words)
    if sort is None:
        return None
    pattern = _AGAINST.get(sort.goal_verb)
    if pattern is not None and pattern.search(idea):
        return "G1"
    return None


# A channel or asset an idea may only assume when the owner named it (or a word of the same kind): a
# car showroom owner who never said "video" or "page" is not told to "pin a short video on your page"
# (seen live, 2026-10-27). Telling the owner to ASK customers, LOOK at what a customer sees, or use
# what they said they have (their manager, their records, their showroom) needs no such word.
_ASSET_GROUPS: tuple[tuple[re.Pattern[str], re.Pattern[str]], ...] = (
    (  # videos
        re.compile(r"\b(?:videos?|reels?|shorts|clips?|captions?|vlogs?|tiktok|youtube)\b", re.I),
        re.compile(r"\b(?:videos?|reels?|shorts|clips?|captions?|vlogs?|tiktok|youtube)\b", re.I),
    ),
    (  # a social page or account
        re.compile(
            r"\b(?:(?:your |the |a )(?:business |social |facebook |instagram )?(?:page|pages)"
            r"|posts?|stories|story|followers?|facebook|instagram|insta|social media)\b",
            re.I,
        ),
        re.compile(
            r"\b(?:page|pages|posts?|stories|story|followers?|facebook|instagram|insta|"
            r"social|fb|tiktok|reels?|whatsapp status)\b",
            re.I,
        ),
    ),
    (  # an online listing, search result or map entry
        re.compile(
            r"(?:search(?:es|ed|ing)? (?:for|online|nearby)|online (?:listing|presence|reviews?)|"
            r"(?:map|google|business) listing|listing|google)",
            re.I,
        ),
        re.compile(
            r"(?:search|online|google|listing|map|website|facebook|instagram|page|app|reviews?)",
            re.I,
        ),
    ),
    (  # paid adverts
        re.compile(
            r"\b(?:ads?|adverts?|advertis\w*|campaigns?|boost(?:ed|ing)?|sponsored)\b", re.I
        ),
        re.compile(
            r"\b(?:ads?|adverts?|advertis\w*|campaigns?|boost\w*|sponsored|ishtehaar)\b", re.I
        ),
    ),
)


def invented_context(idea: str, owner_words: str) -> str | None:
    """G2: the rule id when the idea brings in a channel, asset or business model the owner never
    named."""
    for match in _INVENTED_CONTEXT.finditer(idea):
        word = match.group(0).lower()
        if word.split()[0] not in owner_words.lower():
            return "G2"
    for in_idea, in_owner in _ASSET_GROUPS:
        if in_idea.search(idea) and not in_owner.search(owner_words):
            return "G2"
    return None


def wrong_subtype(idea: str, subtype: str, entry_ideas: Sequence[str] = ()) -> str | None:
    """G3: the rule id when the idea is distinctive of another sub-type than the problem's.
    An idea that is (nearly) one of the entry's own ideas for the sub-type always passes."""
    if not subtype or subtype not in _SUBTYPE_MARKS:
        return None
    if any(solution_library.already_said(idea, [own]) for own in entry_ideas):
        return None
    if _SUBTYPE_MARKS[subtype].search(idea):
        return None
    for other, mark in _SUBTYPE_MARKS.items():
        if other != subtype and mark.search(idea):
            return "G3"
    return None


def causes_in(text: str) -> set[str]:
    return {name for name, pattern in _CAUSE_WORDS.items() if pattern.search(text or "")}


def cause_misfit(idea: str, cause: str) -> str | None:
    """G4: the rule id when the idea assumes a cause. With a known cause it must assume that one;
    with none known it may assume none at all, unless it is useful whatever the cause is."""
    assumed = {name for name, pattern in _IDEA_ASSUMES.items() if pattern.search(idea)}
    if not assumed or _ROBUST.search(idea):
        return None
    known = causes_in(cause)
    if not known:
        return "G4" if not (cause or "").strip() else None  # an odd cause we cannot read: no ruling
    return None if assumed & known else "G4"


def repeats(idea: str, given: Sequence[str]) -> str | None:
    """G7: the rule id when most of the idea's content words are already in one given idea."""
    mine = solution_ideas._evidence(idea)
    if len(mine) < 3:
        return None
    for old in given:
        if len(mine & solution_ideas._evidence(old)) / len(mine) >= SAME_IDEA:
            return "G7"
    return None


def off_the_map(
    idea: str, nodes: Sequence[str], categories: Sequence[str] = (), goal_verb: str = ""
) -> str | None:
    """G8: the rule id when the idea shares nothing with any problem on the map. It relates when it
    shares a content word with a node's words, or with the vocabulary of a node's category or of the
    owner's goal; no nodes means no map to judge by."""
    if not nodes:
        return None
    mine = solution_ideas._evidence(idea)
    weak = solution_ideas.WEAK
    theirs = solution_ideas._evidence(" ".join(nodes))
    shared = mine & theirs
    if shared - weak or len(shared & weak) >= 2:
        return None
    cues = " ".join(solution_library.CUES.get(c, "") for c in categories)
    if mine & (solution_ideas._evidence(cues) - weak):
        return None
    if mine & solution_ideas._evidence(_GOAL_VOCAB.get(goal_verb, "")):
        return None  # the goal's own words ("sale", "oldest"), not only the node's
    return "G8"


def failures(idea: str, owner_words: str, ctx: IdeaContext | None = None) -> list[str]:
    """Rule ids of the filter that the idea breaks (empty when it passes). G1 and G2 always; G3,
    G4, G7 and G8 only with an `IdeaContext` that holds data."""
    found = [goal_conflict(idea, owner_words), invented_context(idea, owner_words)]
    if ctx is not None and ctx.industries:
        found.append(idea_vocabulary.foreign_vocabulary(idea, owner_words, ctx.industries))
    if ctx is not None and ctx.active():
        found += [
            wrong_subtype(idea, ctx.subtype, ctx.entry_ideas),
            cause_misfit(idea, ctx.cause),
            repeats(idea, ctx.given),
            off_the_map(idea, ctx.nodes, ctx.node_categories, ctx.goal_verb),
        ]
    return [rule for rule in found if rule]


def context_from(
    noted: Sequence[dict[str, Any]],
    owner_words: str,
    given: Sequence[str] = (),
    entries: Sequence[dict[str, Any]] = (),
    industries: Sequence[str] = (),
) -> IdeaContext:
    """The context from the noted problems (what `problems.noted_context` returns), the owner's
    words, the ideas already given and the industry's entries. The latest noted problem that has a
    sub-type, a goal verb or a cause speaks for the problem; the goal verb's sort (spec 7.2)
    overrides the model's own sub-type."""
    subtype = goal_verb = cause = ""
    for item in reversed(list(noted)):
        subtype = subtype or str(item.get("subtype") or "")
        goal_verb = goal_verb or str(item.get("goal_verb") or "")
        cause = cause or str(item.get("cause") or "")
    sort = taxonomy.goal_sort(owner_words)
    if sort is not None:
        subtype, goal_verb = sort.subtype, sort.goal_verb
    elif goal_verb and not subtype:
        subtype = next(
            (s.subtype for _p, s in taxonomy._GOAL_RULES if s.goal_verb == goal_verb), ""
        )
    entry_ideas: list[str] = []
    for entry in entries:
        if subtype and entry.get("subtype") == subtype:
            entry_ideas += [str(i) for i in entry.get("quick_ideas") or []]
            entry_ideas += [str(e.get("text") or "") for e in entry.get("extra_ideas") or []]
    nodes = tuple(
        " ".join(
            [
                str(n.get("title") or ""),
                str(n.get("title_local") or ""),
                *map(str, n.get("user_words") or []),
            ]
        )
        for n in noted
    )
    return IdeaContext(
        subtype=subtype,
        goal_verb=goal_verb,
        cause=cause,
        entry_ideas=tuple(i for i in entry_ideas if i),
        given=tuple(given),
        nodes=nodes,
        node_categories=tuple(str(n.get("group") or "") for n in noted),
        industries=tuple(industries),
    )


NEED_FACT_CAUSE = (
    "I need one more fact before I can say anything useful here. What do you think is the main "
    "reason behind it: how it looks, what it costs, the season, or people not knowing?"
)
NEED_FACT_SINCE = (
    "I need one more fact before I can say anything useful here. Since when has this been going on?"
)


def need_fact_line(ctx: IdeaContext | None) -> str:
    """When the filter removed every idea: no weak idea, one missing fact, one question, last."""
    return NEED_FACT_SINCE if ctx is not None and ctx.cause.strip() else NEED_FACT_CAUSE
