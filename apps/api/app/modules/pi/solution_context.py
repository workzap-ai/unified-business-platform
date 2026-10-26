"""What the solution ideas add to one turn's context (Addendum 2 to the pi Brain v3, Parts 2 and 3).

Only when the workspace set `response_rules.brain.solution_mode` to true. Then, once the problems
are sorted (S4 or S5, never while pi is still listening), pi may be handed at most two ideas for
the problem the person cares about, chosen by `solution_ideas.choose`: none they have had, none of
a kind they rejected, the better ones more often. A returning customer is greeted with their last
ideas instead (the follow-up is the one question of that message). The counts of the value line
are enforced here: a conversation never gets more than IDEAS_BEFORE_OFFER ideas, never more than
IDEAS_PER_PROBLEM for one problem, and after a declined offer at most IDEAS_AFTER_DECLINE more,
for a new problem only. Which ideas were handed over is stamped on the conversation, so the
nightly run can score them by what the person says next; the first message after the ideas is
also looked at at once (the instant speed of Part 3.1), so "already doing that" is honoured in the
same chat and a returning customer's "it worked" is heard.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi import (
    flow,
    learning_bank,
    learning_rules,
    learning_solutions,
    learning_voice,
    solution_ask,
    solution_ideas,
    solution_library,
    solutions,
    value_line,
)
from app.modules.pi.language import detect_language
from app.modules.pi.models import PiConversation
from app.shared.scope import WorkspaceScope

GIVING = {flow.State.S4_SORTED_SUMMARY.value, flow.State.S5_READINESS.value}
# What a person says after ideas that means "give me something else / more" (Part 3.3)
AGAIN = {
    "idea_already_doing": "swap",
    "idea_not_possible": "swap",
    "idea_generic": "swap",
    "idea_no_help": "swap",
    "idea_more": "more",
    "idea_worked": "worked",
}
NOTED_TITLES = 3


def switched_on(response_rules: dict[str, Any] | None) -> bool:
    rules = response_rules or {}
    return (
        rules.get("pi_mode") == "brain" and (rules.get("brain") or {}).get("solution_mode") is True
    )


def _sector(industry: str | None) -> str | None:
    """The sector of an industry ("7.I Health and care"); it decides the Workzap line wording."""
    return str((solutions.load(industry or "") or {}).get("sector") or "") or None


def given_so_far(conversation: PiConversation) -> int:
    """Ideas handed over in this chat. Kept in the brief, apart from the stamps, which are
    trimmed to the last few: a long chat must never reset the count (R-VAL-02)."""
    return int((conversation.service_brief or {}).get("ideas_given") or 0)


def _put(conversation: PiConversation, **changes: Any) -> dict[str, Any]:
    brief = {**(conversation.service_brief or {}), **changes}
    conversation.service_brief = brief
    return brief


def allowance(brief: dict[str, Any], given: int) -> int:
    """How many more ideas this chat may be given (R-VAL-02 and RV-02). Before any decline the
    budget is IDEAS_BEFORE_OFFER in all; once the offer was declined, IDEAS_AFTER_DECLINE more."""
    if int(brief.get("declines") or 0) > 0:
        taken = given - int(brief.get("ideas_at_decline", given))
        return value_line.IDEAS_AFTER_DECLINE - taken
    return value_line.IDEAS_BEFORE_OFFER - given


def _no_ideas(
    conversation: PiConversation,
    noted: list[dict[str, Any]],
    industry: str | None,
    why: str,
    now: datetime,
) -> dict[str, Any]:
    """A request for a fix that gets no idea must still be answered (R-SELL-04): pi says honestly
    what it noted and offers the document. The miss is logged on the chat for the audit (S7) and
    the metrics (3.10: solution request left unanswered, always 0)."""
    brief = conversation.service_brief or {}
    log = [*list(brief.get("solution_unanswered") or [])[-9:]]
    log.append({"industry": industry or "", "why": why, "at": now.isoformat()})
    _put(
        conversation,
        solution_unanswered=log,
        solution_unanswered_n=int(brief.get("solution_unanswered_n") or 0) + 1,
    )
    if why == "nothing_noted":
        # R-SOL-02: they asked and nothing is noted yet. pi may ask ONE question; the answer to it
        # (the problem) is answered with ideas, not with another question: carried to the next turn
        _put(conversation, open_ask=True)
    titles = [str(n.get("title") or "")[:80] for n in noted[-NOTED_TITLES:] if n.get("title")]
    return {"solution_asked_no_ideas": True, "solution_noted": titles, "solution_why": why}


def _from_library(
    conversation: PiConversation, noted: list[dict[str, Any]], language: str
) -> dict[str, Any] | None:
    """Two ideas from the generic library for the latest noted problem's category (platform spec
    Book 2 Part 7.4), when no industry entry has any: an unknown industry, or a problem none of the
    entry's problems matches. None when the budget is spent, nothing is noted, or the library has
    nothing new for the category: the honest "those are the ideas I have" line then follows."""
    brief = conversation.service_brief or {}
    left = allowance(brief, given_so_far(conversation))
    if left <= 0 or not noted:
        return None
    before = [str(x) for x in brief.get("library_given") or []]
    ideas: list[str] = []
    category = ""
    heard = " ".join(
        " ".join([str(n.get("title") or ""), *[str(w) for w in n.get("user_words") or []]])
        for n in noted[-3:]
    )
    for category in solution_library.best_category(noted):
        count = min(value_line.IDEAS_PER_MESSAGE, left)
        ideas = solution_library.ideas_for(category, before, count, heard)
        if ideas:
            break
    if not ideas:
        return None
    problem = {
        "id": f"library:{category}",
        "workzap_build": {"keys": solution_library.build_keys(category)},
    }
    line = solution_ask.bridge(dict(brief), problem, language, None)
    conversation.service_brief = solution_ask.remember_bridge(
        {
            **brief,
            "ideas_given": given_so_far(conversation) + len(ideas),
            "library_given": [*before, *ideas][-20:],
            "solution_last_problem": problem["id"],
        },
        line,
    )
    out: dict[str, Any] = {"solution_ideas": ideas, "solution_asked": True}
    if never := solution_library.never_say(category):
        out["solution_never_say"] = [never]
    if line:
        out["solution_build"] = solution_ask.public(line)
    return out


async def _prefer_bridge(
    session: AsyncSession,
    scope: WorkspaceScope,
    conversation: PiConversation,
    said: str,
    used: dict[str, Any],
) -> None:
    """A2-FIX-5: with learning on, the opener of this turn's Workzap line is the learned choice;
    with learning frozen (no `voice_arm` key in the stamp) the openers rotate as before. The variant
    is stamped on the turn, and credited only if the reply really used it."""
    if conversation is None:
        return
    brief = conversation.service_brief or {}
    if "voice_arm" not in used:  # learning is off for this turn: no preference carries over
        if brief.get("bridge_preferred"):
            _put(conversation, bridge_preferred="")
        return
    if used.get("voice_arm"):
        return  # the stamp holds one voice variant: an acknowledgement is already in it
    language = detect_language(said) or conversation.language or "en"
    if language not in ("en", "roman_ur"):
        return
    await learning_voice.ensure_seeded(session, scope)
    arm = await learning_voice.choose(session, scope, "bridge", language)
    if arm is None:
        return
    _put(conversation, bridge_preferred=arm.text)
    used["voice_arm"] = str(arm.id)


async def build(
    session: AsyncSession,
    scope: WorkspaceScope,
    conversation: PiConversation,
    said: str,
    noted: list[dict[str, Any]],
    used: dict[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Context keys `solution_ideas`, `solution_followup`, `solution_exhausted`,
    `solution_asked_no_ideas`, `solution_next`, `solution_not_tried` (each may be missing); fills
    `used` with the stamp for the nightly scoring. Never raises: before migration 0043 is applied
    the tables are missing and pi simply gives no ideas."""
    await _prefer_bridge(session, scope, conversation, said, used)
    carried = bool((getattr(conversation, "service_brief", None) or {}).get("open_ask"))
    if carried and conversation is not None:
        _put(conversation, open_ask=False)  # one turn only: the answer to pi's one question
    churning = solution_ask.churn_risk(said) and conversation is not None
    if churning:
        # R-SOL-03: the churn signal is logged on the chat (the flag and the time, never the words)
        stamp = (now or datetime.now(UTC)).isoformat()
        _put(conversation, churn_risk_at=stamp)
    for attempt in (1, 2):
        try:
            async with session.begin_nested():
                out = await _build(session, scope, conversation, said, noted, used, now)
            if carried and not out.get("solution_ideas"):
                out = {**out, "open_ask": True}
            if churning:
                out = {**out, "churn_risk": True}
            return out
        except ProgrammingError:
            return {}
        except IntegrityError:
            # Two messages of one business at once both seeded the same industry (its first
            # version, its idea arms). The other one won: look again, it is there now. Never let
            # a seeding race cost the person their reply.
            if attempt == 2:
                return {}
    return {}


async def _instant(
    session: AsyncSession,
    scope: WorkspaceScope,
    conversation: PiConversation,
    said: str,
    now: datetime,
) -> str | None:
    """The instant look (Part 3.1): what this message says about the ideas pi last gave. A
    returning customer's answer to "did anything start?" applies to the ideas that follow-up named;
    otherwise the first message after the ideas settles the latest open stamp. Returns the
    signal."""
    if conversation.customer_id is None:
        return None
    brief = conversation.service_brief or {}
    pending = [str(i) for i in brief.get("solution_followup_arms") or []]
    if pending and not brief.get("solution_followup_reacted"):
        reaction = await learning_solutions.react_to_followup(
            session, scope, customer_id=conversation.customer_id, arm_ids=pending, said=said
        )
        if reaction is None:
            return None
        stamps = list(brief.get("learning_used") or [])
        for stamp in stamps:  # the same ideas are not scored again overnight
            if (
                stamp.get("ideas")
                and not stamp.get("ideas_scored")
                and set(map(str, stamp["ideas"])) <= set(pending)
            ):
                stamp["ideas_scored"], stamp["reaction"] = True, reaction.signal
        _put(conversation, solution_followup_reacted=True, learning_used=stamps)
        return reaction.signal
    stamps = list(brief.get("learning_used") or [])
    for stamp in reversed(stamps):
        if not stamp.get("ideas") or stamp.get("ideas_scored"):
            continue
        outcome = await learning_solutions.settle(
            session, scope, conversation, stamp, now, final=False, current=said
        )
        if outcome in ("scored", "not_given"):
            _put(conversation, learning_used=stamps)
        return str(stamp.get("reaction")) if outcome == "scored" else None
    return None


async def _give(
    session: AsyncSession,
    scope: WorkspaceScope,
    conversation: PiConversation,
    *,
    industry: str,
    problem: dict[str, Any],
    language: str,
    used: dict[str, Any],
    now: datetime,
    asked: bool,
    offerable: bool,
    next_kind: str = "",
    build_line: bool = True,
) -> dict[str, Any] | None:
    """Choose, record and hand over the ideas for one problem inside every cap. None when there is
    nothing to give (the budget is spent, or nothing new is left for this business)."""
    assert conversation.customer_id is not None
    brief = conversation.service_brief or {}
    left = allowance(brief, given_so_far(conversation))
    if left <= 0:
        return None
    if int(brief.get("declines") or 0) > 0 and str(problem["id"]) in [
        str(p) for p in brief.get("problems_at_decline") or []
    ]:
        return None  # after a declined offer, a new problem only (RV-02)
    choice = await solution_ideas.choose(
        session,
        scope,
        industry_key=industry,
        problem_id=problem["id"],
        language=language,
        customer_id=conversation.customer_id,
        count=min(value_line.IDEAS_PER_MESSAGE, left),
        conversation_id=conversation.id,
    )
    if not choice.arms:
        # "Nothing new left" is only true when this business was given ideas for the problem; an
        # entry with no usable idea (its seed ideas failed the idea guard) is "no idea yet".
        given = await solution_ideas.remembered(
            session, scope, conversation.customer_id, str(problem["id"])
        )
        return {"solution_exhausted": True} if choice.exhausted and given else None
    used["ideas"] = [str(a.id) for a in choice.arms]
    used["problem_id"] = problem["id"]
    used["state"] = conversation.flow_state
    # Remember at once what is handed over, so the same idea is never offered twice in one chat
    # (the nightly scoring only adds what the person said about it).
    await solution_ideas.record_given(
        session,
        scope,
        customer_id=conversation.customer_id,
        conversation_id=conversation.id,
        arms=choice.arms,
        now=now,
    )
    used["recorded"] = True
    line = (
        solution_ask.bridge(
            dict(conversation.service_brief or {}), problem, language, _sector(industry)
        )
        if (asked or next_kind == "worked") and build_line
        else None  # a near-problem's build line would read as an irrelevant template
    )
    brief = solution_ask.remember_bridge(
        {
            **(conversation.service_brief or {}),
            "ideas_given": given_so_far(conversation) + len(choice.arms),
            "ideas_problems": [
                *[str(p) for p in (conversation.service_brief or {}).get("ideas_problems") or []],
                str(problem["id"]),
            ][-20:],
            "solution_last_problem": str(problem["id"]),
        },
        line,
    )
    conversation.service_brief = brief
    out: dict[str, Any] = {"solution_ideas": [a.text for a in choice.arms]}
    if asked or next_kind:
        out["solution_never_say"] = solutions.never_say([industry])[:6]
    if line:
        out["solution_build"] = solution_ask.public(line)
        keys = (problem.get("workzap_build") or {}).get("keys") or []
        if keys and "says" in line:
            await solution_ideas.note_builds(
                session,
                scope,
                customer_id=conversation.customer_id,
                problem_id=problem["id"],
                keys=[str(keys[0])],
            )
    if next_kind:
        out["solution_next"] = next_kind
    elif asked:
        out["solution_asked"] = True
        used["offer_appended"] = offerable  # settle never scores a turn that carries the offer
    return out


async def _build(
    session: AsyncSession,
    scope: WorkspaceScope,
    conversation: PiConversation,
    said: str,
    noted: list[dict[str, Any]],
    used: dict[str, Any],
    now: datetime | None,
) -> dict[str, Any]:
    from app.modules.customers.models import Customer

    now = now or datetime.now(UTC)
    asked = solution_ask.asked_for_ideas(said)  # an explicit request for a fix (Part 1.6)
    if conversation.customer_id is None:
        return _no_ideas(conversation, noted, None, "no_customer", now) if asked else {}
    customer = await session.get(Customer, conversation.customer_id)
    industry = customer.industry_primary if customer is not None else None
    if not industry or solutions.load(industry) is None:
        if (
            solution_ask.asked_howto(said)
            and (conversation.flow_state or "") in solution_ask.ASKABLE
        ):
            # "how exactly?" with no trade known yet: the detail is the solution document
            return {
                "solution_howto": {"covers": "", "which_app": solution_ask.asked_which_app(said)}
            }
        if asked and (conversation.flow_state or "") in solution_ask.ASKABLE:
            from_library = _from_library(
                conversation, noted, detect_language(said) or conversation.language or "en"
            )
            if from_library is not None:
                return from_library
        return _no_ideas(conversation, noted, industry, "no_industry", now) if asked else {}
    language = detect_language(said) or conversation.language or "en"
    language = language if language in ("en", "roman_ur", "ar") else "en"
    await solution_ideas.ensure_arms(session, scope, industry)
    used["industry"] = industry
    used["language"] = language
    signal = await _instant(session, scope, conversation, said, now)
    next_kind = AGAIN.get(signal or "", "")
    brief = conversation.service_brief or {}
    if signal == "idea_not_tried":
        if brief.get("blockers_asked"):
            return {}
        _put(conversation, blockers_asked=True)
        return {"solution_not_tried": True}  # ask once what got in the way, give no idea
    if not brief.get("solution_followup_done"):
        back = await solution_ideas.continuity(
            session, scope, customer_id=conversation.customer_id, now=now
        )
        if back is not None:
            _put(
                conversation,
                solution_followup_done=True,
                solution_followup_arms=back["arm_ids"],
                solution_last_problem=back["problem_id"],
            )
            out: dict[str, Any] = {"solution_followup": back}
            if back["worked"] or back["no_help"]:
                # it worked: the next steps and the Workzap line; it did not help: a different
                # kind of idea (the review of the idea's fit is already queued)
                problem = {
                    e["id"]: e for e in await solution_ideas.entries(session, scope, industry)
                }.get(back["problem_id"])
                if problem is not None:
                    more = await _give(
                        session,
                        scope,
                        conversation,
                        industry=industry,
                        problem=problem,
                        language=language,
                        used=used,
                        now=now,
                        asked=False,
                        offerable=False,
                        next_kind="worked" if back["worked"] else "swap",
                    )
                    if more:
                        out.update(more)
            return out
    howto = solution_ask.asked_howto(said)
    asked = asked or bool(next_kind)
    state = conversation.flow_state or ""
    explicit = solution_ask.asked_for_ideas(said)
    reacting = bool(next_kind)
    if howto and not noted and state in solution_ask.ASKABLE:
        # "how exactly?" before anything is noted still gets the one answer pi may give: the detail
        # is in the solution document (an empty reply here ended chats in a real-model sweep)
        return {
            "solution_howto": {"covers": "", "which_app": solution_ask.asked_which_app(said)},
            "solution_never_say": solutions.never_say([industry])[:6],
        }
    if not (noted or reacting) or not (
        state in GIVING or ((asked or howto) and state in solution_ask.ASKABLE)
    ):
        if explicit and not howto and not noted:
            return _no_ideas(conversation, noted, industry, "nothing_noted", now)
        return {}
    entries = await solution_ideas.entries(session, scope, industry)
    problem = None
    strong = False  # the entry matches by the main rule, not only by a near-problem fallback
    # The latest noted problem first, then the earlier ones: a person who then mentions something
    # off the page ("staff forget the entry") still gets ideas for the problem that does match.
    best_fit = -1
    for item in reversed(noted or []):
        group, subtype = str(item.get("group") or ""), str(item.get("subtype") or "")
        said_words = " ".join(
            [
                str(item.get("title") or ""),
                str(item.get("title_local") or ""),
                *[str(w) for w in item.get("user_words") or []],
            ]
        )
        found = solution_ideas.match_problem(entries, group, subtype, said_words)
        if found is None:
            continue
        # The entry that fits the person's own words best, not the first one the category gave
        # (live test 4: "views but no orders" took the attribution ideas before the entry for
        # "price asked in DM, then silence"); a tie goes to the latest noted problem.
        fit = solution_ideas.fit(found, said_words)
        if fit > best_fit:
            best_fit = fit
            problem = found
            strong = solution_ideas.is_strong_match(found, group, subtype, said_words)
    if problem is None and reacting:
        strong = True  # the entry the ideas were already given for
    if problem is None and reacting:
        problem = {e["id"]: e for e in entries}.get(str(brief.get("solution_last_problem") or ""))
    offerable = (conversation.flow_state or "") in solution_ask.OFFERABLE
    if howto:
        line = solution_ask.bridge(
            dict(conversation.service_brief or {}), problem, language, _sector(industry)
        )
        brief = solution_ask.remember_bridge(dict(conversation.service_brief or {}), line)
        brief["howto_asked"] = int(brief.get("howto_asked") or 0) + 1
        conversation.service_brief = brief
        keys = ((problem or {}).get("workzap_build") or {}).get("keys") or []
        if problem is not None and keys and line and "says" in line:
            await solution_ideas.note_builds(
                session,
                scope,
                customer_id=conversation.customer_id,
                problem_id=problem["id"],
                keys=[str(keys[0])],
            )
        return {
            "solution_howto": {
                "covers": solution_ask.covers(problem),
                "which_app": solution_ask.asked_which_app(said),
            },
            "solution_build": solution_ask.public(line),
            "solution_never_say": solutions.never_say([industry])[:6],
        }
    _stamp_decline(conversation)
    if allowance(conversation.service_brief or {}, given_so_far(conversation)) <= 0:
        return _no_ideas(conversation, noted, industry, "budget", now) if explicit else {}
    if problem is None:
        if noted:
            words = " ".join(str(noted[-1].get("title") or "").lower().split()[:8])
            if (
                words
                and learning_bank.redaction_confidence(words) >= learning_rules.PROMOTE_REDACTION
            ):
                used["unmatched"] = words  # only words with no name, figure or contact in them
                used["customer"] = str(conversation.customer_id)
        if explicit and (from_library := _from_library(conversation, noted, language)) is not None:
            return from_library
        return _no_ideas(conversation, noted, industry, "no_match", now) if explicit else {}
    handed = await _give(
        session,
        scope,
        conversation,
        industry=industry,
        build_line=strong,
        problem=problem,
        language=language,
        used=used,
        now=now,
        asked=explicit,
        offerable=offerable,
        next_kind=next_kind,
    )
    if handed is None:
        return _no_ideas(conversation, noted, industry, "none_left", now) if explicit else {}
    return handed


def _stamp_decline(conversation: PiConversation) -> None:
    """The first time pi looks after a declined offer, remember how many ideas it had given and
    for which problems: only a new problem may get ideas now, and at most two (RV-02)."""
    brief = conversation.service_brief or {}
    if int(brief.get("declines") or 0) > 0 and "ideas_at_decline" not in brief:
        _put(
            conversation,
            ideas_at_decline=given_so_far(conversation),
            problems_at_decline=[str(p) for p in brief.get("ideas_problems") or []],
        )
