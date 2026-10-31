# ruff: noqa: E501
"""PS-3: idea_relevance.evaluate_idea. One golden test per verdict kind, then the hard rules:
a gate violation always wins, unknown stays unknown, no word sharing is needed, Urdu, Arabic and
Hindi script are never rejected for being non-Latin, the function never raises and is linear."""

import random
import string
import time
from dataclasses import dataclass

import pytest

from app.modules.pi import idea_relevance as ir
from app.modules.pi.idea_relevance import IdeaKind, evaluate_idea

LATE_ORDERS = [
    {
        "id": "p1",
        "title": "Orders reach customers late",
        "user_words": ["our orders always arrive late"],
        "category": "orders_fulfilment",
        "subtype": "delivery_late",
    }
]
DOUBLE_BOOKING = [
    {
        "id": "p1",
        "title": "Two teams booked for one slot",
        "user_words": ["we get double bookings every month"],
        "category": "operations_process",
    }
]
RENT = [
    {
        "id": "p1",
        "title": "Tenants pay the rent late",
        "user_words": ["tenants pay after the due date"],
        "category": "cash_collections",
    }
]


@dataclass
class _V:
    status: str
    rule: str = "budget"
    reason: str = "over the stated budget"


def _violates(idea, constraints, language):  # a stand-in gate
    return _V("violates") if "hire" in idea.lower() else _V("ok")


def _unknown_gate(idea, constraints, language):
    return _V("unknown", "none", "cannot check")


# ----- one golden value per kind ---------------------------------------------------------------


def test_linked_by_meaning_not_by_words() -> None:
    # "delivery delay" vs "late orders": no content word in common except none of the owner's own
    v = evaluate_idea(
        "Ask the courier for a tracking number so a delivery delay shows early.", LATE_ORDERS
    )
    assert v.kind is IdeaKind.LINKED
    assert v.linked_problem_ids == ("p1",)
    assert v.evidence_words
    assert v.constraint_status == "unknown"  # no gate: never ok


def test_linked_double_booking_overlapping_reservations() -> None:
    v = evaluate_idea("Show overlapping reservations in one shared calendar.", DOUBLE_BOOKING)
    assert v.kind is IdeaKind.LINKED


def test_unlinked_names_a_topic_that_is_not_the_problem() -> None:
    v = evaluate_idea("Repaint the entrance hall in brighter colours.", LATE_ORDERS)
    assert v.kind is IdeaKind.UNLINKED
    assert v.linked_problem_ids == ()


def test_unlinked_other_problem_topic() -> None:
    v = evaluate_idea("Send each tenant a reminder before the rent is due.", LATE_ORDERS)
    assert v.kind is IdeaKind.UNLINKED


def test_generic_boilerplate() -> None:
    v = evaluate_idea("Use better software to improve your business.", LATE_ORDERS)
    assert v.kind is IdeaKind.GENERIC


def test_unknown_when_no_topic_is_recognised() -> None:
    v = evaluate_idea("Zorp the flibber with a glorbish.", LATE_ORDERS)
    assert v.kind is IdeaKind.UNKNOWN


def test_unknown_without_any_problem() -> None:
    assert evaluate_idea("Keep a list of late orders.", []).kind is IdeaKind.UNKNOWN
    assert evaluate_idea("Keep a list of late orders.", None).kind is IdeaKind.UNKNOWN  # type: ignore[arg-type]


def test_unknown_for_unsupported_script_never_linked() -> None:
    v = evaluate_idea("请每天给客户发送订单跟踪信息以减少延迟", LATE_ORDERS)
    assert v.kind is IdeaKind.UNKNOWN
    assert v.reason == "unsupported_script"


def test_unknown_empty() -> None:
    for text in ("", "   ", None, 5, b"x"):
        assert evaluate_idea(text, LATE_ORDERS).kind is IdeaKind.UNKNOWN  # type: ignore[arg-type]


def test_repeats_tried() -> None:
    tried = [{"what": "I tried a discount on late orders", "outcome": "no effect", "msg": "m1"}]
    v = evaluate_idea(
        "Offer a discount to customers whose orders were late.", LATE_ORDERS, None, tried
    )
    assert v.kind is IdeaKind.REPEATS_TRIED


def test_repeats_tried_string_shape_and_other_script() -> None:
    v = evaluate_idea(
        "ہر آرڈر پر ڈسکاؤنٹ دیں", LATE_ORDERS, None, ["ہم نے ڈسکاؤنٹ دیا مگر کوئی فائدہ نہیں ہوا"]
    )
    assert v.kind is IdeaKind.REPEATS_TRIED


def test_a_different_remedy_is_not_a_repeat() -> None:
    tried = [{"what": "I tried a discount", "outcome": "no effect"}]
    v = evaluate_idea(
        "Ask the courier for a tracking number for every parcel.", LATE_ORDERS, None, tried
    )
    assert v.kind is IdeaKind.LINKED


# ----- the gate ---------------------------------------------------------------------------------


def test_gate_violation_beats_relevance() -> None:
    v = evaluate_idea(
        "Hire two drivers so no delivery is late.",
        LATE_ORDERS,
        {"staff": {"text": "I cannot hire anyone"}},
        constraint_gate=_violates,
    )
    assert v.kind is IdeaKind.VIOLATES_CONSTRAINT
    assert v.constraint_status == "violated"
    assert v.linked_problem_ids == ("p1",)  # still reported, but the verdict is the violation
    assert "budget" in v.reason or v.reason


def test_gate_violation_beats_everything_even_generic_and_tried() -> None:
    always = lambda i, c, lg: _V("violates")  # noqa: E731
    for idea in ("Use better software to improve your business.", "Offer a discount", "zzz", "请"):
        v = evaluate_idea(idea, LATE_ORDERS, None, [{"what": "a discount"}], constraint_gate=always)
        assert v.kind is IdeaKind.VIOLATES_CONSTRAINT


def test_gate_ok_sets_constraint_ok_and_never_changes_relevance() -> None:
    v = evaluate_idea(
        "Track every parcel with the courier's number.", LATE_ORDERS, {}, constraint_gate=_violates
    )
    assert v.kind is IdeaKind.LINKED and v.constraint_status == "ok"


def test_gate_unknown_stays_unknown_constraint() -> None:
    v = evaluate_idea(
        "Track every parcel with the courier's number.",
        LATE_ORDERS,
        {},
        constraint_gate=_unknown_gate,
    )
    assert v.kind is IdeaKind.LINKED and v.constraint_status == "unknown"


def test_gate_that_raises_or_returns_junk_is_unknown_not_ok() -> None:
    def boom(i, c, lg):
        raise RuntimeError("x")

    for gate in (boom, lambda i, c, lg: None, lambda i, c, lg: 7, lambda i, c, lg: _V("OK!!")):
        v = evaluate_idea(
            "Track every parcel with the courier's number.", LATE_ORDERS, {}, constraint_gate=gate
        )
        assert v.kind is IdeaKind.LINKED and v.constraint_status == "unknown"


def test_adapter_for_option_gate() -> None:
    class Gated:
        def __init__(self, verdict):
            self.verdict = verdict

    class Result:
        def __init__(self, accepted=(), rejected=(), unknown=()):
            self.accepted, self.rejected, self.unknown = accepted, rejected, unknown

    def fake_gate_options(options, requirements, language=None):
        return (
            Result(rejected=(Gated(_V("violates")),))
            if requirements == "R"
            else Result(accepted=(Gated(_V("ok")),))
        )

    gate = ir.gate_from_option_gate(
        fake_gate_options, lambda constraints: "R" if constraints else None
    )
    v = evaluate_idea(
        "Track every parcel with the courier's number.", LATE_ORDERS, {"x": 1}, constraint_gate=gate
    )
    assert v.kind is IdeaKind.VIOLATES_CONSTRAINT
    v = evaluate_idea(
        "Track every parcel with the courier's number.", LATE_ORDERS, {}, constraint_gate=gate
    )
    assert v.constraint_status == "ok"


# ----- scripts ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("idea", "problem", "kind"),
    [
        (
            "کورئیر سے ٹریکنگ نمبر مانگیں تاکہ ڈیلیوری کی دیر جلد نظر آئے",
            "ڈیلیوری گاہکوں کو دیر سے پہنچتی ہے",
            IdeaKind.LINKED,
        ),
        (
            "اطلبوا من شركة الشحن رقم التتبع لكل طرد لتظهر التأخيرات مبكراً",
            "تصل توصيلاتنا إلى الزبائن متأخرة",
            IdeaKind.LINKED,
        ),
        (
            "हर पार्सल के लिए कूरियर से ट्रैकिंग नंबर लें ताकि डिलीवरी में देरी जल्दी दिखे",
            "हमारी डिलीवरी ग्राहकों तक देर से पहुँचती है",
            IdeaKind.LINKED,
        ),
        (
            "Courier se tracking number mangein taake delivery ki dair jaldi nazar aaye",
            "Delivery gahakon ko dair se pohanchti hai",
            IdeaKind.LINKED,
        ),
        ("दीवारों को नए रंग से पेंट करें", "हमारी डिलीवरी ग्राहकों तक देर से पहुँचती है", IdeaKind.UNLINKED),
        (
            "دیواروں کو نئے رنگ سے پینٹ کریں",
            "ڈیلیوری گاہکوں کو دیر سے پہنچتی ہے",
            IdeaKind.UNLINKED,
        ),
        ("اصبغوا الجدران بلون جديد", "تصل توصيلاتنا إلى الزبائن متأخرة", IdeaKind.UNLINKED),
    ],
)
def test_non_latin_script_is_judged_not_rejected(idea: str, problem: str, kind: IdeaKind) -> None:
    probs = [
        {"id": "p1", "title": problem, "user_words": [problem], "category": "orders_fulfilment"}
    ]
    assert evaluate_idea(idea, probs).kind is kind


def test_tashkeel_digits_and_arabic_letter_forms_do_not_change_the_verdict() -> None:
    base = "اطلبوا من شركة الشحن رقم التتبع لكل طرد لتظهر التأخيرات مبكراً"
    marked = "اطْلُبُوا مِنْ شَرِكَةِ الشَّحْنِ رَقْمَ التَّتَبُّعِ لِكُلِّ طَرْدٍ لِتَظْهَرَ التَّأْخِيرَاتُ مُبَكِّراً"
    probs = [
        {
            "id": "p1",
            "title": "تأخر التوصيل للزبائن",
            "user_words": ["١٠ طرود متأخرة"],
            "category": "",
        }
    ]
    assert evaluate_idea(base, probs).kind is evaluate_idea(marked, probs).kind is IdeaKind.LINKED
    assert ir.normalize_text("١٢٣ ۴۵۶ १२३") == "123 456 123"
    assert ir.normalize_text("كيف ي") == ir.normalize_text("کیف ی")


def test_unlinked_is_not_unknown_and_unknown_is_never_linked() -> None:
    v = evaluate_idea("Sell protein bars at the entrance.", LATE_ORDERS)
    assert v.kind in (IdeaKind.UNLINKED, IdeaKind.UNKNOWN)
    assert v.kind is not IdeaKind.LINKED


def test_known_facts_never_link_by_themselves() -> None:
    v = evaluate_idea(
        "Sell protein bars at the entrance.",
        LATE_ORDERS,
        known_facts={"business": "gym with protein bars"},
    )
    assert v.kind is not IdeaKind.LINKED


def test_no_money_or_promise_in_the_verdict() -> None:
    v = evaluate_idea(
        "Ask the courier for tracking numbers to cut the delivery delay by 50%.", LATE_ORDERS
    )
    blob = f"{v.reason} {v.evidence_words} {v.concepts}"
    assert "%" not in blob and "50" not in blob and "rs" not in blob.lower().split()


# ----- never raises, linear time -----------------------------------------------------------------


def test_junk_fuzz_never_raises() -> None:
    rng = random.Random(7)
    alphabet = (
        string.printable
        + "اإأآبتثجحخدذرزسشصضطظعغفقكلمنهويىةءئؤ"
        + "ٱﷲ‏‎​‮"
        + "अआइईउऊएऐओऔकखगघचछजझ"
        + "😀🏳️‍🌈\x00\x07"
    )
    for _ in range(400):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 300)))
        prob = [{"id": "p", "title": text[:50], "user_words": [text[50:90]], "category": text[:5]}]
        v = evaluate_idea(text, prob, {"budget": text[:9]}, [text[:20]], text[:2], {"k": text[:3]})
        assert isinstance(v.kind, IdeaKind)


@pytest.mark.parametrize(
    "bad",
    [
        None,
        1,
        "str",
        [None],
        [1, 2],
        ["x"],
        [{"id": None, "title": None, "user_words": None}],
        [{"title": 5, "user_words": 7, "category": 9, "subtype": [], "where": {}, "impact": 3}],
        [{"title": "late orders", "user_words": [None, 3, "late orders"], "cause": "str"}],
        {"p1": 1},
    ],
)
def test_junk_problem_shapes_never_raise(bad) -> None:  # type: ignore[no-untyped-def]
    for constraints in (None, 5, "x", [], {"cannot_change": 5}, {"staff": None}):
        for tried in (None, 5, "x", [None], [{"what": 5}], {"a": 1}):
            v = evaluate_idea("late orders tracking", bad, constraints, tried, 5, 5)  # type: ignore[arg-type]
            assert isinstance(v.kind, IdeaKind)


def test_input_caps_and_linear_time() -> None:
    probs = LATE_ORDERS
    unit = "Ask the courier for a tracking number so a delivery delay shows early. "
    times = {}
    for n in (1_000, 10_000, 100_000):
        text = (unit * (n // len(unit) + 1))[:n]
        t = time.perf_counter()
        v = evaluate_idea(text, probs, {"cannot_change": ["x" * 50] * 300}, ["y " * 50] * 300)
        times[n] = time.perf_counter() - t
        assert v.kind in (IdeaKind.LINKED, IdeaKind.REPEATS_TRIED, IdeaKind.UNKNOWN)
    assert times[100_000] < 1.0
    # capped input: 100k is not 100x slower than 10k (it would be 10x for linear, so allow 40x)
    assert times[100_000] < max(times[10_000], 0.01) * 40


def test_many_problems_are_capped() -> None:
    probs = [
        {"id": f"p{i}", "title": "late orders delivery delay", "user_words": []}
        for i in range(5000)
    ]
    t = time.perf_counter()
    v = evaluate_idea("Track every late delivery.", probs)
    assert time.perf_counter() - t < 1.0
    assert len(v.linked_problem_ids) <= ir.MAX_PROBLEMS


def test_pathological_repeats_do_not_blow_up() -> None:
    for text in (
        "ا" * 100_000,
        "و" * 50_000 + " ",
        ("ال" * 20 + " ") * 3000,
        "a " * 60_000,
        "​" * 100_000,
    ):
        t = time.perf_counter()
        evaluate_idea(text, LATE_ORDERS)
        assert time.perf_counter() - t < 1.5


# ----- inputs of other shapes, causes, several problems, facts -----------------------------------------


class _Obj:  # a record read by attribute, as an ORM row would be
    def __init__(self, **kw):  # type: ignore[no-untyped-def]
        self.__dict__.update(kw)


def test_problem_records_may_be_objects() -> None:
    row = _Obj(id="p9", title="Orders reach customers late", user_words=["late"], category="")
    v = evaluate_idea("Ask the courier for a tracking number.", [row])
    assert v.kind is IdeaKind.LINKED and v.linked_problem_ids == ("p9",)


def test_a_guessed_cause_links_nothing_but_an_owner_cause_does() -> None:
    base = {"id": "p1", "title": "Sales are slow", "user_words": [], "category": ""}
    idea = "Ask the courier for a tracking number."
    guessed = {**base, "cause": {"text": "the courier is late", "status": "pi_inferred"}}
    said = {**base, "cause": {"text": "the courier is late", "status": "owner_said"}}
    confirmed = {**base, "cause_text": "the courier is late", "cause_status": "confirmed"}
    assert evaluate_idea(idea, [guessed]).kind is not IdeaKind.LINKED
    assert evaluate_idea(idea, [said]).kind is IdeaKind.LINKED
    assert evaluate_idea(idea, [confirmed]).kind is IdeaKind.LINKED


def test_several_problems_the_idea_links_to_the_right_one() -> None:
    probs = [
        {"id": "a", "title": "Tenants pay the rent late", "user_words": [], "category": ""},
        {"id": "b", "title": "Orders reach customers late", "user_words": [], "category": ""},
    ]
    v = evaluate_idea("Ask the courier for a tracking number.", probs)
    assert v.kind is IdeaKind.LINKED and v.linked_problem_ids == ("b",)
    v = evaluate_idea("Send each tenant a payment reminder.", probs)
    assert v.linked_problem_ids == ("a",)


def test_ids_fall_back_to_ref_number_then_position() -> None:
    def mk(**k):  # type: ignore[no-untyped-def]
        return {"title": "Orders reach customers late", **k}

    idea = "Ask the courier for a tracking number."
    assert evaluate_idea(idea, [mk(ref="r1")]).linked_problem_ids == ("r1",)
    assert evaluate_idea(idea, [mk(number=3)]).linked_problem_ids == ("3",)
    assert evaluate_idea(idea, [mk()]).linked_problem_ids == ("p1",)


def test_taxonomy_category_alone_links_a_concept_idea() -> None:
    probs = [{"id": "p1", "title": "", "user_words": [], "category": "orders_fulfilment"}]
    assert evaluate_idea("Ask the courier for a tracking number.", probs).kind is IdeaKind.LINKED
    probs = [{"id": "p1", "title": "", "user_words": [], "category": "other"}]
    assert evaluate_idea("Ask the courier for a tracking number.", probs).kind is IdeaKind.UNKNOWN


def test_subtype_narrows_the_category() -> None:
    probs = [{"id": "p1", "title": "", "category": "orders_fulfilment", "subtype": "delivery_late"}]
    assert evaluate_idea("Ask the courier for a tracking number.", probs).kind is IdeaKind.LINKED
    # a custom pack sub-type the lexicon does not know falls back to the category
    probs = [{"id": "p1", "title": "", "category": "orders_fulfilment", "subtype": "made_up"}]
    assert evaluate_idea("Ask the courier for a tracking number.", probs).kind is IdeaKind.LINKED


def test_a_single_record_passed_alone_is_accepted() -> None:
    one = {"id": "p1", "title": "Orders reach customers late"}
    assert evaluate_idea("Ask the courier for a tracking number.", one).kind is IdeaKind.LINKED  # type: ignore[arg-type]


def test_known_facts_explain_an_unlinked_idea() -> None:
    v = evaluate_idea(
        "Send each tenant a payment reminder.",
        LATE_ORDERS,
        known_facts={"business": "we collect rent from tenants"},
    )
    assert v.kind is IdeaKind.UNLINKED and v.reason == "business_context_only"
    v = evaluate_idea("Send each tenant a payment reminder.", LATE_ORDERS)
    assert v.reason == "other_topic"


def test_tried_by_words_without_a_named_remedy() -> None:
    tried = [{"what": "phoned every late customer personally", "outcome": "no time"}]
    v = evaluate_idea("Phone every late customer personally each week.", LATE_ORDERS, None, tried)
    assert v.kind is IdeaKind.REPEATS_TRIED and v.reason == "tried_words"


def test_one_shared_word_with_a_tried_entry_is_not_a_repeat() -> None:
    tried = [{"what": "phoned every late customer personally"}]
    v = evaluate_idea("Ask the courier for a tracking number.", LATE_ORDERS, None, tried)
    assert v.kind is IdeaKind.LINKED


def test_generic_wording_does_not_beat_a_specific_link() -> None:
    v = evaluate_idea(
        "Improve your business: ask the courier for a tracking number and track every parcel.",
        LATE_ORDERS,
    )
    assert v.kind is IdeaKind.LINKED


def test_weak_tool_concept_alone_is_not_a_link() -> None:
    probs = [{"id": "p1", "title": "Our software keeps crashing", "user_words": []}]
    assert evaluate_idea("Use better software.", probs).kind is not IdeaKind.LINKED


def test_decor_idea_needs_real_evidence() -> None:
    probs = [{"id": "p1", "title": "Customers wait too long in the queue", "user_words": []}]
    assert evaluate_idea("Paint the walls of the waiting room.", probs).kind is IdeaKind.UNLINKED


def test_setting_word_only_is_not_a_link() -> None:
    probs = [{"id": "p1", "title": "Birds die every week in the shed", "user_words": []}]
    assert evaluate_idea("Print a new logo for the farm gate.", probs).kind is IdeaKind.UNLINKED
    assert (
        evaluate_idea("Count the birds in the shed every morning.", probs).kind is IdeaKind.LINKED
    )


def test_verdict_is_frozen_and_hashable() -> None:
    v = evaluate_idea("x y z", LATE_ORDERS)
    with pytest.raises(AttributeError):
        v.kind = IdeaKind.LINKED  # type: ignore[misc]
    assert hash(v) == hash(v)


def test_gate_receives_the_idea_constraints_and_language() -> None:
    seen = []

    def gate(idea, constraints, language):  # type: ignore[no-untyped-def]
        seen.append((idea, constraints, language))
        return _V("ok")

    cons = {"budget": {"text": "none"}}
    evaluate_idea("Track parcels.", LATE_ORDERS, cons, None, "ur", constraint_gate=gate)
    assert seen == [("Track parcels.", cons, "ur")]


def test_gate_detail_is_capped_and_rule_sanitised() -> None:
    def gate(i, c, lg):  # type: ignore[no-untyped-def]
        return _V("violates", "Bud get!!", "x" * 999)

    v = evaluate_idea("Track parcels.", LATE_ORDERS, constraint_gate=gate)
    assert v.reason == "constraint_gate:budget" and len(v.detail) == 200


def test_gate_may_return_a_mapping() -> None:
    def gate(i, c, lg):  # type: ignore[no-untyped-def]
        return {"status": "violates", "rule": "staff", "reason": "cannot hire"}

    v = evaluate_idea("Track parcels.", LATE_ORDERS, constraint_gate=gate)
    assert v.kind is IdeaKind.VIOLATES_CONSTRAINT and v.detail == "cannot hire"


def test_normalize_text_is_idempotent_and_total() -> None:
    for text in ("Ask THE courier’s tracking-number", "كيف ي ٱلله", "१२३ abc", "é", "", None, 5):
        once = ir.normalize_text(text)
        assert ir.normalize_text(once) == once
    assert ir.normalize_text("don't") == "dont"
    assert ir.normalize_text("é") == "e"
    assert ir.normalize_text("a​b") == "ab"


def test_expand_and_split_helpers() -> None:
    assert ir._split_terms("a|b (c|d)|e") == ["a", "b (c|d)", "e"]
    assert sorted(ir._expand("late orders?")) == ["late order", "late orders"]
    assert sorted(ir._expand("(a |b )?c")) == ["a c", "b c", "c"]
    assert sorted(ir._expand("[ae]x")) == ["ax", "ex"]
    assert len(ir._expand("(a|b)(c|d)(e|f)(g|h)(i|j)(k|l)(m|n)(o|p)", limit=64)) <= 64
