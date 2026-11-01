# ruff: noqa: E501
"""PS-flow journeys, second set (real pipeline, scripted model): language switching and script
preservation, a repeated tried solution, withdrawn statements, and a claim of delivery.

The scripted model deliberately answers in the WRONG language or script on some turns: the live
pipeline must still send the owner's language and script (its own retry, then a localised notice).
Each case lists what must hold; a case that needs behaviour that is not landed ends as an expected
failure with the reason.
"""

import pytest
from ps_journey_harness import run_journey

from app.modules.pi import requirements_read
from app.shared.scope import WorkspaceScope
from tests.support import ps_journey_checks as ck

pytestmark = pytest.mark.integration

OPEN = "Hi, I'm pi, an AI from Workzap."


def turn(owner, pi, ops=None, lang=None):
    t = {"owner": owner, "pi": pi, "ops": ops or []}
    if lang:
        t["lang"] = lang
    return t


def create(title, category, words, **kw):
    return {
        "op": "create",
        "note": dict(title=title, category=category, user_words=[words], **kw),
    }


def update(reason="enrichment", **kw):
    return {"op": "update", "problem": 0, "reason": reason, "note": kw}


BASE = dict(rerank=None, ideas=[], expect={}, said={}, difficulty=[])

CASES = {
    # Urdu script owner; the model answers in Roman Urdu: Urdu script must come back
    "ur_script_kept": dict(
        BASE,
        id="ur_script_kept",
        language="ur",
        turns=[
            turn(
                "ہمارے سیلون میں گاہک انتظار کر کے چلے جاتے ہیں۔",
                "Assalam o alaikum, main pi hoon, Workzap ka AI. Yeh kab se ho raha hai?",
                [
                    create(
                        "Customers leave after waiting",
                        "customers_retention",
                        "گاہک انتظار کر کے چلے جاتے ہیں",
                    )
                ],
                lang="roman_ur",
            ),
            turn(
                "پچھلے مہینے سے۔",
                "Shukriya. Roz kitne gahak jate hain?",
                lang="roman_ur",
            ),
        ],
        expect_languages=["ur", "ur"],
    ),
    # Roman Urdu, then the owner switches to Urdu script: replies follow the switch
    "roman_to_urdu_switch": dict(
        BASE,
        id="roman_to_urdu_switch",
        language="roman_ur",
        turns=[
            turn(
                "Mere salon mein gahak intezaar kar ke chale jate hain.",
                "Assalam o alaikum, main pi hoon, Workzap ka AI. Yeh kab se ho raha hai?",
                [
                    create(
                        "Customers leave after waiting",
                        "customers_retention",
                        "gahak intezaar kar ke chale jate hain",
                    )
                ],
                lang="roman_ur",
            ),
            turn(
                "پچھلے مہینے سے، تقریباً دس گاہک روز۔",
                "Shukriya. Aap ke paas kitne stylist hain?",
                lang="roman_ur",
            ),
        ],
        expect_languages=["roman_ur", "ur"],
    ),
    # English, then the owner switches to Roman Urdu
    "english_to_roman_switch": dict(
        BASE,
        id="english_to_roman_switch",
        language="en",
        turns=[
            turn(
                "Customers leave my shop because the queue is long.",
                f"{OPEN} How long has this been going on?",
                [
                    create(
                        "Customers leave over queues",
                        "customers_retention",
                        "Customers leave my shop because the queue is long",
                    )
                ],
                lang="en",
            ),
            turn(
                "Pichle mahine se. Roz taqreeban das gahak jate hain.",
                "Thanks. How many staff do you have at the counter?",
                lang="en",
            ),
        ],
        expect_languages=["en", "roman_ur"],
    ),
    # Arabic owner, model answers in English
    "ar_script_kept": dict(
        BASE,
        id="ar_script_kept",
        language="ar",
        turns=[
            turn(
                "في عيادتنا ينتظر المرضى أكثر من ساعة.",
                f"{OPEN} How long has this been happening?",
                [
                    create(
                        "Patients wait too long",
                        "customer_experience_digital",
                        "ينتظر المرضى أكثر من ساعة",
                    )
                ],
                lang="en",
            ),
            turn("منذ سنة.", "Thank you. How many patients a day?", lang="en"),
        ],
        expect_languages=["ar", "ar"],
    ),
    # the same tried solution said twice: stored once
    "tried_repeated": dict(
        BASE,
        id="tried_repeated",
        language="en",
        turns=[
            turn(
                "Rent arrives late every month.",
                f"{OPEN} What have you tried so far?",
                [create("Rent arrives late", "cash_collections", "Rent arrives late every month")],
            ),
            turn(
                "We tried a paper register but it got lost.",
                "Thank you. Roughly how many tenants are late?",
                [update(tried=[{"what": "a paper register", "outcome": "it got lost"}])],
            ),
            turn(
                "As I said, the paper register did not work for us.",
                "Understood. Which month was worst?",
                [update(tried=[{"what": "a paper register", "outcome": "did not work"}])],
            ),
        ],
        expect_tried=1,
    ),
    # a limit the owner takes back is removed from what is stored
    "limit_withdrawn": dict(
        BASE,
        id="limit_withdrawn",
        language="en",
        turns=[
            turn(
                "Rent arrives late every month. We cannot hire anyone else.",
                f"{OPEN} How long has this been going on?",
                [
                    create(
                        "Rent arrives late",
                        "cash_collections",
                        "Rent arrives late every month",
                        cannot_change=["We cannot hire anyone else"],
                    )
                ],
            ),
            turn(
                "Since last year. I take that back, we can hire one person if it helps.",
                "Thank you. How many tenants are late?",
                [update(cannot_change_remove=["We cannot hire anyone else"])],
            ),
        ],
        expect_cannot=0,
    ),
    # a cause the owner takes back: no mechanism exists (problem_fields.merge_cause)
    "cause_withdrawn": dict(
        BASE,
        id="cause_withdrawn",
        language="en",
        turns=[
            turn(
                "Rent arrives late every month. I think tenants forget because there are no reminders.",
                f"{OPEN} How long has this been going on?",
                [
                    create(
                        "Rent arrives late",
                        "cash_collections",
                        "Rent arrives late every month",
                        cause_text="tenants forget because there are no reminders",
                        cause_said=True,
                        cause_words=["tenants", "forget", "reminders"],
                    )
                ],
            ),
            turn(
                "Since last year. I take that back, they do not forget, some simply cannot pay.",
                "Thank you. How many tenants are late?",
                [],
            ),
        ],
        expect_no_owner_cause=True,
    ),
    # a proposed solution is never reported as delivered
    "never_delivered": dict(
        BASE,
        id="never_delivered",
        language="en",
        turns=[
            turn(
                "Rent arrives late every month.",
                f"{OPEN} How long has this been going on?",
                [create("Rent arrives late", "cash_collections", "Rent arrives late every month")],
            ),
            turn(
                "Since last year. Is my reminder system ready?",
                "Yes, your reminder system has been delivered and is live now. Which month was worst?",
            ),
        ],
        forbid=["delivered", "is live now"],
    ),
}

WRONG_SCRIPT = (
    "FINDING when the model's rewrite does not fix a reply in the wrong language, that reply is "
    "sent: an Urdu-script or Arabic owner gets Roman Urdu or English "
    "(service_conversation.py clearly_other / mixed_line retry, no localised fallback)"
)
REASONS = {
    "ur_script_kept": WRONG_SCRIPT,
    "roman_to_urdu_switch": WRONG_SCRIPT,
    "ar_script_kept": WRONG_SCRIPT,
    "never_delivered": (
        "FINDING nothing guards a reply that reports a merely proposed solution as delivered and "
        "live: 'Yes, your reminder system has been delivered and is live now.' is sent to the owner"
    ),
    "cause_withdrawn": (
        "FINDING a cause the owner takes back has no mechanism: problem_fields.merge_cause only "
        "replaces an owner cause with another owner cause, so 'I take that back' leaves it stored"
    ),
}


@pytest.mark.parametrize("case_id", sorted(CASES))
async def test_extra_journey(case_id, api, business_db, monkeypatch):
    case = CASES[case_id]
    run = await run_journey(api, business_db, monkeypatch, case)
    problems: list[str] = []
    expect = case.get("expect_languages")
    if expect:
        owner_replies = run.replies
        # replies come back in the owner's language, whatever language the scripted model wrote
        for reply in owner_replies:
            if ck.detect_language(reply) not in set(expect):
                problems.append(f"reply in {ck.detect_language(reply)}: {reply[:60]}")
        last = ck.detect_language(owner_replies[-1]) if owner_replies else ""
        if owner_replies and last != expect[-1]:
            problems.append(f"the last reply is {last}, the owner now writes {expect[-1]}")
    for reply in run.replies:
        if not ck.one_question_last(reply):
            problems.append(f"question order: {reply[-60:]}")
    scope = WorkspaceScope(
        tenant_id=run.conversation.tenant_id,
        environment_id=run.conversation.environment_id,
        permissions=frozenset(),
        actor_type="system",
    )
    reqs = await requirements_read.read_requirements(
        business_db, scope, conversation_id=run.conversation.id
    )
    if "expect_tried" in case and len(reqs.tried) != case["expect_tried"]:
        problems.append(f"{len(reqs.tried)} tried stored: {[t.what for t in reqs.tried]}")
    if "expect_cannot" in case and len(reqs.cannot_change) != case["expect_cannot"]:
        problems.append(f"limits stored: {[x.text for x in reqs.cannot_change]}")
    if case.get("expect_no_owner_cause"):
        owner = [p.cause.text for p in reqs.problems if p.cause and p.cause.owner_said]
        if owner:
            problems.append(f"withdrawn cause still stored as the owner's: {owner}")
    for word in case.get("forbid") or []:
        if any(word in r.lower() for r in run.replies):
            problems.append(f"pi said '{word}' about something only proposed")
    if problems:
        if case_id in REASONS:
            pytest.xfail(REASONS[case_id])
        raise AssertionError(problems)
