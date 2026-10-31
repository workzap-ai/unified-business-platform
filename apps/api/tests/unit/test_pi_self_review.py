# ruff: noqa: E501
"""PS-10: the self-review gate. Golden, planted breakage (30+ per check), property, adversarial, fuzz,
timing. No database, no model."""

from __future__ import annotations

import random
import time
from dataclasses import replace

import pytest

from app.modules.pi import self_review_text as T
from app.modules.pi.self_review import (
    CRITICAL,
    fallback_templates,
    owner_safe_fallback,
    render_report,
    review,
)
from app.modules.pi.self_review_types import (
    BLOCKED,
    COMPLETE,
    FAIL,
    INCOMPLETE,
    NOT_APPLICABLE,
    PASS,
    UNKNOWN,
    BlueprintIn,
    CauseIn,
    ConstraintIn,
    ContextIn,
    DraftResult,
    FactIn,
    OptionIn,
    ProblemIn,
    QuestionsIn,
)

LANGS = ("en", "roman_ur", "ur", "ar")

HEDGED = {
    "en": "Tenants may lose track because everything stays in your head.",
    "roman_ur": "Shayad kirayedar ki shikayat isliye kho jati hai ke sab kuch aap ke zehan mein hota hai.",
    "ur": "شاید کرایہ دار کی شکایات اس لیے کھو جاتی ہیں کہ سب کچھ آپ کے ذہن میں رہتا ہے۔",
    "ar": "ربما تضيع بلاغات المستأجرين لأن كل شيء يبقى في ذهنك.",
}
FLAT = {  # the same sentence with the hedge removed
    "en": "Tenants lose track because everything stays in your head.",
    "roman_ur": "Kirayedar ki shikayat isliye kho jati hai ke sab kuch aap ke zehan mein hota hai.",
    "ur": "کرایہ دار کی شکایات اس لیے کھو جاتی ہیں کہ سب کچھ آپ کے ذہن میں رہتا ہے۔",
    "ar": "تضيع بلاغات المستأجرين لأن كل شيء يبقى في ذهنك.",
}
QUESTION = {
    "en": "Which would you like to start with, the list or the reminders?",
    "roman_ur": "Aap list se shuru karna chahenge ya reminder se?",
    "ur": "کیا آپ فہرست سے شروع کرنا چاہیں گے یا یاد دہانی سے؟",
    "ar": "هل تفضل أن نبدأ بالقائمة أم بالتذكيرات؟",
}
OTHER = {  # a second, different sample reply per language
    "en": "Thank you, that is clear. How long has this been going on for you?",
    "roman_ur": "Shukriya, baat saaf hai. Yeh masla aap ke saath kab se chal raha hai?",
    "ur": "شکریہ، بات صاف ہے۔ یہ مسئلہ آپ کے ساتھ کب سے چل رہا ہے؟",
    "ar": "شكرا، الأمر واضح. منذ متى وأنت تواجه هذا الأمر؟",
}
OWNER_TEXT = {
    "en": "I am what do you think about the late rent and what can we do for you",
    "roman_ur": "Mujhe kiraya late milta hai aur aap kya kar sakte hain",
    "ur": "مجھے کرایہ دیر سے ملتا ہے اور آپ کیا کر سکتے ہیں",
    "ar": "لا أستلم الإيجار في وقته وما الذي يمكنك فعله",
}
CLAIMS = {
    "en": ("This will definitely double your sales.", "We guarantee a result within a month."),
    "roman_ur": ("Yeh guarantee hai ke aap ki bachat hogi.", "Is se faida hoga zaroor."),
    "ur": ("اس سے آپ کا فائدہ ہوگا اور ضمانت ہے۔", "یہ یقینی نتیجہ دے گا۔"),
    "ar": ("نضمن لك نتيجة خلال شهر.", "سيزيد هذا مبيعاتك."),
}
DONE = {
    "en": ("The reminder system has been implemented.", "We have set up the list for you."),
    "roman_ur": ("Reminder system lagaa diya gaya hai.", "Yeh kaam mukammal ho gaya hai."),
    "ur": ("یاد دہانی کا نظام لگا دیا گیا ہے۔", "یہ کام مکمل ہو گیا ہے۔"),
    "ar": ("تم تنفيذ نظام التذكير.", "نفذنا القائمة لك."),
}
APPROVED = {
    "en": "Everything checks out and it is approved.",
    "roman_ur": "Sab theek hai, koi masla nahi.",
    "ur": "سب ٹھیک ہے۔",
    "ar": "كل شيء جيد ولا توجد مشاكل.",
}
PERCENT = {
    "en": "It will help by 40%.",
    "roman_ur": "Is se 40% madad milegi.",
    "ur": "اس سے 40 فیصد مدد ملے گی۔",
    "ar": "سيساعد بنسبة 40 بالمئة.",
}
MONEY = {
    "en": "It costs Rs 5000.",
    "roman_ur": "Is ki qeemat Rs 5000 hai.",
    "ur": "اس کی قیمت 5000 روپے ہے۔",
    "ar": "تكلفته 5000 ريال.",
}


def base(lang: str = "en") -> DraftResult:
    o1 = OptionIn(
        "o1", "shared list of tenant reports", gate="satisfied", relevance="LINKED", rank=1,
        addresses=("p1", "p2"), cause_id="c1",
    )  # fmt: skip
    o2 = OptionIn("o2", "buy better software", relevance="GENERIC", viable=False, rank=2)
    return DraftResult(
        owner_language=lang,
        reply_text=f"{HEDGED[lang]} {QUESTION[lang]}",
        kind="solution",
        context=ContextIn(True, ("conversation", "problems"), True),
        noted_problems=(
            ProblemIn("p1", "Late rent", True, 2),
            ProblemIn("p2", "Lost reports", True, 1),
        ),
        connected_problems=(("p1", "p2"),),
        main_problem_id="p1",
        facts=(FactIn("rent is late every month", "owner_said"),),
        root_causes=(
            CauseIn("c1", FLAT["en"] if lang == "en" else FLAT[lang], "hypothesis", (), "p1"),
        ),
        stored_constraint_ids=("k1", "k2"),
        constraints=(
            ConstraintIn("k1", "one assistant", "satisfied", "satisfied"),
            ConstraintIn("k2", "phone only", "unknown", "unknown"),
        ),
        options=(o1, o2),
        recommended=o1,
        tried_solutions=("paper register",),
        blueprint=BlueprintIn(
            ("steps", "dependencies", "risks"),
            ("list before reminders",),
            ("assistant may forget",),
            unknowns=("phone only",),
        ),  # fmt: skip
        questions=QuestionsIn(1, "", False),
        next_steps=1,
    )


def st(report, cid):
    return report.by_id(cid).status


# ---------------------------------------------------------------- golden


@pytest.mark.parametrize("lang", LANGS)
def test_good_draft_is_complete(lang):
    r = review(base(lang))
    assert r.verdict == COMPLETE, r.reasons
    assert r.next_actions == () or len(r.next_actions) == 1
    assert owner_safe_fallback(r, lang) == ""
    for c in r.checks:
        assert c.status in (PASS, NOT_APPLICABLE), (c.id, c.status, c.evidence)


def test_plain_question_turn_is_complete_and_solution_checks_not_applicable():
    r = review(DraftResult(owner_language="en", reply_text="What does your business do?"))
    assert r.verdict == COMPLETE
    assert st(r, "SR-01") == NOT_APPLICABLE and st(r, "SR-10") == NOT_APPLICABLE


def test_solution_without_any_structure_is_blocked_not_complete():
    r = review(
        DraftResult(
            owner_language="en", kind="solution", reply_text=f"{HEDGED['en']} {QUESTION['en']}"
        )
    )
    assert r.verdict == BLOCKED
    assert {"SR-01", "SR-06"} <= {x.split()[0] for x in r.reasons}


def test_critical_failure_beats_unknown():
    d = replace(base("en"), noted_problems=None, reply_text=f"{DONE['en'][0]} {QUESTION['en']}")
    assert review(d).verdict == INCOMPLETE


def test_one_next_action_and_priority():
    d = replace(base("en"), reply_text=f"{CLAIMS['en'][0]} {DONE['en'][0]} {QUESTION['en']}")
    r = review(d)
    assert len(r.next_actions) == 1
    assert r.repair_code == "reword_proposed"  # SR-16 outranks SR-14


def test_report_helpers_and_fallback_templates_are_linted():
    r = review(replace(base("en"), recommended=replace(base("en").recommended, gate="violated")))
    assert r.verdict == INCOMPLETE and r.repair_code == "drop_option"
    assert "drop_option" in render_report(r) or "drop the option" in render_report(r)
    for lang in LANGS:
        assert render_report(r, lang).startswith("self_review:")
    for group, by_lang in fallback_templates().items():
        assert set(by_lang) == set(LANGS)
        for lang, text in by_lang.items():
            assert T.question_count(text) == 1 and T.last_is_question(text), (group, lang)
            assert not any(ch.isdigit() for ch in text)
            assert T.detect_language(text) in (lang, None) or (lang == "roman_ur"), (group, lang)
            r2 = review(DraftResult(owner_language=lang, reply_text=text))
            assert r2.verdict == COMPLETE, (group, lang, r2.reasons)
            assert st(r2, "SR-14") == PASS and st(r2, "SR-16") == PASS


def test_fallback_language_and_unknown_language():
    r = review(replace(base("ur"), reply_text=DONE["ur"][0]))
    assert r.verdict == INCOMPLETE
    assert owner_safe_fallback(r, "ur") == fallback_templates()["proposal"]["ur"]
    assert owner_safe_fallback(r, "xx") == fallback_templates()["proposal"]["en"]
    blocked = review(replace(base("en"), noted_problems=None))
    assert blocked.verdict == BLOCKED
    assert owner_safe_fallback(blocked, "ar") == fallback_templates()["detail"]["ar"]


# ---------------------------------------------------------------- planted breakage, 30+ per check


def _opt(d, **kw):
    return replace(d.recommended, **kw)


def _with_rec(d, o):
    return replace(d, recommended=o, options=(o, *[x for x in d.options if x.id != o.id]))


def m_sr01(d, lang, k):
    v = [
        replace(d, noted_problems=()),
        replace(d, noted_problems=(ProblemIn("p1", "Late rent", False, 2),)),
        replace(d, noted_problems=(ProblemIn("p1", "", True, 2),)),
        replace(d, noted_problems=(ProblemIn("p1", "Late rent", True, 0),)),
        replace(d, noted_problems=(ProblemIn("p1", "x", False, 3), ProblemIn("p2", "y", False, 3))),
        replace(d, noted_problems=(ProblemIn("p1", "   ", True, 2),)),
        replace(d, noted_problems=(ProblemIn("p1", "Late rent", True, -1),)),
        replace(d, noted_problems=None),
    ]
    return v[k]


def m_sr02(d, lang, k):
    v = [
        replace(d, context=ContextIn(True, (), True)),
        replace(d, context=ContextIn(False, (), True)),
        replace(d, context=ContextIn(True, ("bogus",), True)),
        replace(d, questions=QuestionsIn(1, "", True)),
        replace(d, context=None, questions=QuestionsIn(1, "", True)),
        replace(d, context=ContextIn(False, (), None)),
        replace(
            d, context=ContextIn(True, ("conversation",), True), questions=QuestionsIn(1, "", True)
        ),
        replace(d, context=None),
    ]
    return v[k]


def m_sr03(d, lang, k):
    n = k + 2
    probs = tuple(ProblemIn(f"p{i}", "t", True, 1) for i in range(1, n + 1))
    edges = (("p1", "zz"),) if k == 7 else ()
    return replace(d, noted_problems=probs, connected_problems=edges, problems_unrelated=False)


def m_sr04(d, lang, k):
    q = QUESTION[lang]
    flat = FLAT[lang]
    v = [
        replace(
            d, reply_text=f"{flat} {q}", root_causes=(CauseIn("c1", flat, "pi_inferred", ("e",)),)
        ),
        replace(d, reply_text=f"{flat} {q}", root_causes=(CauseIn("c1", flat, "hypothesis", ()),)),
        replace(d, root_causes=(CauseIn("c1", flat, "", ("e",)),)),
        replace(d, root_causes=(CauseIn("c1", flat, "bogus", ("e",)),)),
        replace(d, reply_text=f"{flat} {q}", facts=(FactIn(flat, "pi_inferred"),)),
        replace(d, reply_text=f"{flat} {q}", facts=(FactIn(flat, ""),)),
        replace(d, reply_text=f"{flat} {q}", facts=(FactIn(flat, "guess"),)),
        replace(d, facts=None, root_causes=None),
    ]
    return v[k]


def m_sr05(d, lang, k):
    rec = d.recommended
    c = d.root_causes[0]
    v = [
        _with_rec(d, replace(rec, cause_id="")),
        _with_rec(d, replace(rec, cause_id="zz")),
        replace(d, root_causes=(replace(c, status="pi_inferred", evidence=()),)),
        replace(d, root_causes=(replace(c, status="", evidence=()),)),
        replace(d, root_causes=(replace(c, status="bogus", evidence=("  ",)),)),
        replace(d, root_causes=(replace(c, status="pi_inferred", evidence=("", " ")),)),
        replace(d, root_causes=None),
        replace(d, root_causes=()),
    ]
    return v[k]


def m_sr06(d, lang, k):
    k1, k2 = d.constraints
    v = [
        replace(d, constraints=(k1,)),
        replace(d, constraints=(replace(k1, gate=""), k2)),
        replace(d, constraints=(replace(k1, gate="bogus"), k2)),
        replace(d, constraints=None),
        replace(d, stored_constraint_ids=None),
        replace(d, constraints=()),
        replace(d, stored_constraint_ids=("k1", "k2", "k3")),
        replace(d, constraints=(k2,)),
    ]
    return v[k]


def m_sr07(d, lang, k):
    kind = ("UNLINKED", "GENERIC", "REPEATS_TRIED", "VIOLATES")[k % 4]
    rec = d.recommended
    if k < 4:
        return _with_rec(d, replace(rec, relevance=kind))
    if k < 8:
        return replace(d, options=(*d.options, OptionIn("o3", "idea", relevance=kind, viable=True)))
    if k == 8:
        return replace(d, blueprint=replace(d.blueprint, unlinked_items=("paint the hall",)))
    return replace(
        d, options=(*d.options, OptionIn("o3", "idea", relevance="UNKNOWN", viable=True))
    )


def m_sr08(d, lang, k):
    rec = d.recommended
    v = [
        _with_rec(d, replace(rec, relevance="REPEATS_TRIED")),
        replace(d, tried_solutions=(rec.text,)),
        replace(d, tried_solutions=(rec.text + " again",)),
        replace(d, tried_solutions=None, recommended=rec),
        replace(d, options=(*d.options, OptionIn("o3", "idea", relevance="REPEATS_TRIED"))),
        replace(d, tried_solutions=("shared list of tenant reports", "paper")),
        replace(d, tried_solutions=("a shared list of the tenant reports",)),
        _with_rec(d, replace(rec, relevance="REPEATS_TRIED", improves_on_tried=False)),
    ]
    out = v[k]
    if k == 3:  # tried not supplied and no REPEATS verdict anywhere
        out = replace(out, options=(rec,))
    return out


def m_sr09(d, lang, k):
    k1, k2 = d.constraints
    rec = d.recommended
    v = [
        replace(d, constraints=(k1, replace(k2, shown="satisfied"))),
        replace(d, constraints=(k1, replace(k2, shown="clear"))),
        replace(d, constraints=(k1, replace(k2, shown="approved"))),
        replace(d, constraints=(k1, replace(k2, shown="ok"))),
        _with_rec(d, replace(rec, gate="unknown")),
        _with_rec(d, replace(rec, relevance="UNKNOWN")),
        replace(d, blueprint=replace(d.blueprint, unknowns=())),
        replace(d, reply_text=f"{APPROVED[lang]} {QUESTION[lang]}"),
    ]
    return v[k]


def m_sr10(d, lang, k):
    rec = d.recommended
    k1, k2 = d.constraints
    v = [
        _with_rec(d, replace(rec, gate="violated")),
        replace(d, constraints=(replace(k1, gate="violated"), k2)),
        _with_rec(d, replace(rec, gate="unknown")),
        _with_rec(d, replace(rec, gate="")),
        _with_rec(d, replace(rec, gate="bogus")),
        replace(
            _with_rec(d, replace(rec, gate="unknown", labelled_unchecked=True)),
            constraints=(replace(k1, gate="unknown", shown="unknown"), k2),
        ),
        _with_rec(d, replace(rec, gate="violated", learn_first=True)),
        replace(d, constraints=(k1, replace(k2, gate="violated"))),
    ]
    return v[k]


def m_sr11(d, lang, k):
    rec = d.recommended
    v = [
        _with_rec(d, replace(rec, addresses=())),
        _with_rec(d, replace(rec, addresses=("p2",))),
        _with_rec(d, replace(rec, addresses=("zz",))),
        replace(d, main_problem_id="", noted_problems=()),
        replace(d, main_problem_id="p9"),
        _with_rec(d, replace(rec, addresses=("p2", "p3"))),
        replace(d, main_problem_id="p2", recommended=replace(rec, addresses=("p1",))),
        _with_rec(d, replace(rec, addresses=("P1",))),
    ]
    out = v[k]
    return out


def m_sr12(d, lang, k):
    bp = d.blueprint
    v = [
        replace(d, blueprint=replace(bp, dependencies=())),
        replace(d, blueprint=replace(bp, risks=())),
        replace(d, blueprint=replace(bp, dependencies=(), risks=())),
        replace(d, blueprint=replace(bp, sections=("steps", "risks"))),
        replace(d, blueprint=replace(bp, sections=("steps", "dependencies"))),
        replace(d, blueprint=None, kind="blueprint"),
        replace(
            d,
            blueprint=replace(
                bp, risks=(), none_known_risks=False, sections=("dependencies", "risks")
            ),
        ),
        replace(d, blueprint=replace(bp, dependencies=(), none_known_dependencies=False)),
    ]
    return v[k]


def m_sr13(d, lang, k):
    others = [x for x in LANGS if x != lang]
    if k < 6:
        src = others[k % 3]
        pool = HEDGED if k < 3 else OTHER
        return replace(d, reply_text=f"{pool[src]} " + (QUESTION[src] if k < 3 else ""))
    src = others[k - 6]
    return replace(d, owner_language="", owner_text=OWNER_TEXT[lang], reply_text=OTHER[src])


def m_sr14(d, lang, k):
    q = QUESTION[lang]
    v = [
        replace(d, reply_text=f"{CLAIMS[lang][0]} {q}"),
        replace(d, reply_text=f"{CLAIMS[lang][1]} {q}"),
        replace(d, reply_text=f"{PERCENT[lang]} {q}"),
        replace(d, reply_text=f"{MONEY[lang]} {q}"),
        replace(
            d, reply_text=f"{HEDGED[lang]} We will leverage synergy and a scalable pipeline. {q}"
        ),
        replace(d, next_steps=2),
        replace(d, next_steps=3),
        replace(d, reply_text=HEDGED[lang], next_steps=0, questions=None),
    ]
    return v[k]


def m_sr15(d, lang, k):
    q = QUESTION[lang]
    h = HEDGED[lang]
    v = [
        replace(d, reply_text=f"{h} {q} {q}"),
        replace(d, reply_text=f"{q} {h}"),
        replace(d, questions=QuestionsIn(3, "", False)),
        replace(d, reply_text=f"{q} {q} {q}"),
        replace(d, reply_text=f"{h} {q}\n{OTHER[lang]}"),
        replace(d, reply_text=f"{q} {OTHER[lang]} {q}"),
        replace(d, reply_text=f"{h} {q} {h}"),
        replace(d, reply_text=f"{h} {q} {h} {q}"),
    ]
    return v[k]


def m_sr16(d, lang, k):
    q = QUESTION[lang]
    phrase = DONE[lang][k % 2]
    status = ("", "proposed", "approved", "")[k // 2]
    return replace(d, reply_text=f"{phrase} {q}", implementation_status=status)


MUTATORS = {
    "SR-01": (m_sr01, 8, (FAIL, UNKNOWN)),
    "SR-02": (m_sr02, 8, (FAIL, UNKNOWN)),
    "SR-03": (m_sr03, 8, (FAIL,)),
    "SR-04": (m_sr04, 8, (FAIL, UNKNOWN)),
    "SR-05": (m_sr05, 8, (FAIL, UNKNOWN)),
    "SR-06": (m_sr06, 8, (FAIL, UNKNOWN)),
    "SR-07": (m_sr07, 10, (FAIL, UNKNOWN)),
    "SR-08": (m_sr08, 8, (FAIL, UNKNOWN)),
    "SR-09": (m_sr09, 8, (FAIL,)),
    "SR-10": (m_sr10, 8, (FAIL, UNKNOWN)),
    "SR-11": (m_sr11, 8, (FAIL, UNKNOWN)),
    "SR-12": (m_sr12, 8, (FAIL, UNKNOWN)),
    "SR-13": (m_sr13, 9, (FAIL,)),
    "SR-14": (m_sr14, 8, (FAIL,)),
    "SR-15": (m_sr15, 8, (FAIL,)),
    "SR-16": (m_sr16, 8, (FAIL,)),
}
CASES = [(cid, lang, k) for cid, (_, n, _) in MUTATORS.items() for lang in LANGS for k in range(n)]


def test_planted_count_is_at_least_30_per_check():
    for cid, (_, n, _) in MUTATORS.items():
        assert n * len(LANGS) >= 30, cid


@pytest.mark.parametrize("cid,lang,k", CASES)
def test_planted_breakage_is_caught(cid, lang, k):
    mutate, _, allowed = MUTATORS[cid]
    r = review(mutate(base(lang), lang, k))
    got = st(r, cid)
    assert got in allowed, (cid, lang, k, got, r.by_id(cid).evidence)
    if cid in CRITICAL and cid not in ("SR-13", "SR-14") or (cid == "SR-13" and got == FAIL):
        assert r.verdict != COMPLETE, (cid, lang, k, r.verdict)
    if cid == "SR-14" and k <= 3:
        assert r.verdict == INCOMPLETE  # an invented claim is critical
    if r.verdict != COMPLETE:
        fb = owner_safe_fallback(r, lang)
        assert fb and T.question_count(fb) == 1


def test_noncritical_failures_do_not_block_but_are_warned():
    d = m_sr03(base("en"), "en", 3)
    r = review(d)
    assert st(r, "SR-03") == FAIL and r.verdict == COMPLETE
    assert any(w.startswith("SR-03") for w in r.warnings)
    assert r.next_actions and r.repair_code == "connect_problems"


# ---------------------------------------------------------------- properties and adversarial


def test_unknown_in_critical_is_never_pass():
    for cid, mutate in (("SR-01", m_sr01), ("SR-06", m_sr06)):
        r = review(mutate(base("en"), "en", 7 if cid == "SR-01" else 4))
        assert st(r, cid) == UNKNOWN and r.verdict == BLOCKED


def test_unknown_language_is_unknown_not_pass_and_does_not_block():
    r = review(DraftResult(owner_language="en", reply_text="ok 12345"))
    assert st(r, "SR-13") == UNKNOWN and r.verdict == COMPLETE
    r = review(DraftResult(reply_text="What does your business do?"))
    assert st(r, "SR-13") == UNKNOWN


def test_negation_and_condition_do_not_trip_claims_or_done():
    d = replace(
        base("en"), reply_text=f"I cannot guarantee a result, and it is not done. {QUESTION['en']}"
    )
    r = review(d)
    assert st(r, "SR-14") == PASS and st(r, "SR-16") == PASS
    d = replace(base("en"), reply_text=f"Once it is done we can check it. {QUESTION['en']}")
    assert st(review(d), "SR-16") == PASS
    d = replace(base("roman_ur"), reply_text=f"Hum guarantee nahi de sakte. {QUESTION['roman_ur']}")
    assert st(review(d), "SR-14") == PASS


def test_owner_numbers_may_be_repeated_but_invented_ones_may_not():
    d = replace(
        base("en"),
        owner_text="80 tenants pay late",
        reply_text=f"You said 80 tenants, or 80% of them? {QUESTION['en']}",
    )
    r = review(d)
    assert (
        st(r, "SR-14") == PASS and st(r, "SR-15") == FAIL
    )  # 80 is the owner's figure; two questions
    assert st(review(replace(d, owner_text="")), "SR-14") == FAIL  # without it the 80% is invented
    d2 = replace(base("en"), facts=(FactIn("80 tenants pay late", "owner_said"),),
                 reply_text=f"Out of 80 tenants, 80% is a lot. {QUESTION['en']}")  # fmt: skip
    assert st(review(d2), "SR-14") == PASS


def test_implemented_status_allows_done_wording():
    d = replace(
        base("en"),
        reply_text=f"The list has been implemented. {QUESTION['en']}",
        implementation_status="implemented",
    )
    assert st(review(d), "SR-16") == NOT_APPLICABLE


def test_learn_first_and_not_yet_checked_are_accepted():
    rec = replace(base("en").recommended, gate="unknown", labelled_unchecked=True)
    d = replace(
        _with_rec(base("en"), rec),
        constraints=(
            ConstraintIn("k1", "a", "unknown", "unknown"),
            ConstraintIn("k2", "b", "unknown", "unknown"),
        ),
    )
    r = review(d)
    assert st(r, "SR-10") == FAIL  # all unknown and not learn-first
    rec2 = replace(rec, learn_first=True)
    r2 = review(replace(d, recommended=rec2, options=(rec2,)))
    assert st(r2, "SR-10") == PASS and r2.verdict == COMPLETE, r2.reasons


def test_repeat_with_labelled_improvement_is_allowed():
    rec = replace(base("en").recommended, relevance="REPEATS_TRIED", improves_on_tried=True)
    r = review(_with_rec(base("en"), rec))
    assert st(r, "SR-07") == PASS and st(r, "SR-08") == PASS


def test_urdu_versus_arabic_and_roman_detection():
    assert T.detect_language(HEDGED["ur"]) == "ur"
    assert T.detect_language(HEDGED["ar"]) == "ar"
    assert T.detect_language(HEDGED["roman_ur"]) == "roman_ur"
    assert T.detect_language(HEDGED["en"]) == "en"
    assert T.detect_language("") is None and T.detect_language("1234 !!") is None


def test_script_mismatch_by_owner_script_only():
    d = DraftResult(owner_script="arabic", reply_text=OTHER["en"])
    assert st(review(d), "SR-13") == FAIL
    d = DraftResult(owner_script="latin", reply_text=OTHER["en"])
    assert st(review(d), "SR-13") == UNKNOWN


# ---------------------------------------------------------------- fuzz and timing


def _rand_text(rng):
    pool = list("abc xyz?؟.!؀ابتثجحخ٠١٢٣ٹڈ%$0123456789\n\t ") + [
        "guarantee",
        "done",
        "شاید",
        "ho gaya",
        "Rs 5",
        "\u0000",
    ]
    return "".join(rng.choice(pool) for _ in range(rng.randint(0, 300)))


def test_fuzz_never_raises_and_always_valid():
    rng = random.Random(7)
    for _ in range(400):
        d = DraftResult(
            owner_language=rng.choice(("", "en", "ur", "zz")),
            reply_text=_rand_text(rng),
            owner_text=_rand_text(rng),
            kind=rng.choice(("", "solution", "blueprint", "question")),
            options=tuple(
                OptionIn(
                    str(i),
                    _rand_text(rng),
                    rng.choice(("", "x", "unknown", "satisfied")),
                    rng.choice(("", "LINKED", "GENERIC", "?")),
                )
                for i in range(rng.randint(0, 4))
            ),
            tried_solutions=rng.choice((None, (_rand_text(rng),))),
        )
        r = review(d)
        assert r.verdict in (COMPLETE, INCOMPLETE, BLOCKED) and len(r.checks) == 16
        assert len(r.next_actions) <= 1
        render_report(r, "ar")
        owner_safe_fallback(r, "ur")


def test_garbage_types_never_raise():
    r = review(
        DraftResult(
            reply_text=123, options="nope", noted_problems=5, facts=[1, 2], root_causes=(object(),)
        )
    )  # type: ignore[arg-type]
    assert r.verdict in (COMPLETE, INCOMPLETE, BLOCKED)
    assert review(None).verdict in (COMPLETE, INCOMPLETE, BLOCKED)  # type: ignore[arg-type]


def test_huge_input_is_linear_and_fast():
    big = ("word " * 200000) + "?"
    d = replace(base("en"), reply_text=big, owner_text=big, tried_solutions=(big,) * 500,
                options=tuple(OptionIn(str(i), big) for i in range(500)))  # fmt: skip
    t0 = time.perf_counter()
    for _ in range(5):
        review(d)
    assert (time.perf_counter() - t0) / 5 < 0.5


def test_adversarial_regex_backtracking():
    evil = "a" * 50000 + " will " * 5000 + "1" * 50000 + "% " + "رs" * 20000
    t0 = time.perf_counter()
    review(DraftResult(owner_language="en", reply_text=evil))
    assert time.perf_counter() - t0 < 1.0


def test_review_is_deterministic():
    d = m_sr09(base("ar"), "ar", 7)
    assert review(d) == review(d)


# ---------------------------------------------------------------- application-written text must pass clean

APP_TEXTS = {
    "en": (
        "Please confirm: you approve quote Q-0001 for PKR 450,000. Is that right?",
        "The quote is free of charge. Shall I send it?",
    ),
    "roman_ur": (
        "Tasdeeq karein: aap quote Q-0001 ko PKR 450,000 ke liye manzoor karte hain. Kya yeh theek hai?",
        "Yeh quote bilkul muft hai. Kya main isay bhej doon?",
    ),
    "ur": (
        "تصدیق کریں: آپ کوٹیشن Q-0001 کو PKR 450,000 کے لیے منظور کرتے ہیں۔ کیا یہ درست ہے؟",
        "یہ کوٹیشن بالکل مفت ہے۔ کیا میں اسے بھیج دوں؟",
    ),
    "ar": (
        "يرجى التأكيد: أنت توافق على عرض السعر Q-0001 بمبلغ PKR 450,000. هل هذا صحيح؟",
        "عرض السعر مجاني تماما. هل أرسله لك؟",
    ),
    "hi": (
        "कृपया पुष्टि करें: आप कोटेशन Q-0001 को PKR 450,000 के लिए मंज़ूर करते हैं। क्या यह सही है?",
        "यह कोटेशन बिल्कुल निःशुल्क है। क्या मैं इसे भेज दूँ?",
    ),
}
APP_CASES = [
    (lang, i, status)
    for lang in APP_TEXTS
    for i in (0, 1)
    for status in ("", "proposed", "approved", "in_progress")
]


@pytest.mark.parametrize("lang,i,status", APP_CASES)
def test_application_written_text_is_clean(lang, i, status):
    d = DraftResult(
        owner_language=lang,
        reply_text=APP_TEXTS[lang][i],
        implementation_status=status,
        known_amounts=("PKR 450,000", "Q-0001"),
    )
    r = review(d)
    assert st(r, "SR-16") == PASS, r.by_id("SR-16").evidence
    assert st(r, "SR-14") == PASS, r.by_id("SR-14").evidence
    assert st(r, "SR-15") == PASS
    assert r.verdict == COMPLETE, r.reasons


def test_quote_reference_alone_is_not_money_and_unlisted_price_still_flagged():
    ok = DraftResult(
        owner_language="en", reply_text="Quote Q-0001 is ready for your approval. Shall I send it?"
    )
    assert review(ok).verdict == COMPLETE
    # SR-16 is never the one to object to a price: SR-14 is, and only for a figure nobody supplied
    bad = DraftResult(owner_language="en", reply_text=APP_TEXTS["en"][0])
    r = review(bad)
    assert st(r, "SR-16") == PASS and st(r, "SR-14") == FAIL and r.by_id("SR-14").tag == "claim"


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("status", ["", "proposed", "approved", "in_progress"])
def test_work_reported_as_done_is_still_flagged_for_every_unfinished_status(lang, status):
    for phrase in DONE[lang]:
        d = DraftResult(
            owner_language=lang,
            reply_text=f"{phrase} {QUESTION[lang]}",
            implementation_status=status,
        )
        assert st(review(d), "SR-16") == FAIL, (lang, status, phrase)


def test_hindi_done_wording_flagged_and_guarded():
    d = DraftResult(owner_language="hi", reply_text="यह काम पूरा हो गया है। क्या आप देखना चाहेंगे?")
    assert st(review(d), "SR-16") == FAIL
    d = DraftResult(owner_language="hi", reply_text="जब यह हो गया तो हम जाँच करेंगे। क्या ठीक है?")
    assert st(review(d), "SR-16") == PASS
