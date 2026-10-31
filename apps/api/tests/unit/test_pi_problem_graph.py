# ruff: noqa: E501
"""PS-7: the problem graph and root-cause layer model. No database, no model.

Scripted inputs prove the wiring and the rules (evidence-only edges, pi_inferred never shown as
owner_said or confirmed, unknown never ranked), not real-world reasoning."""

import json
import random
import time

import pytest

from app.modules.pi import problem_graph as g
from app.modules.pi import problem_graph_lexicon as lx

OWNER = {g.OWNER_SAID, g.CONFIRMED}


def rec(pid, title, words, category="orders_fulfilment", subtype="", **kw):
    return {
        "id": pid,
        "title": title,
        "user_words": words,
        "category": category,
        "subtype": subtype,
        **kw,
    }


# ---------------------------------------------------------------------------------------------
# Golden
# ---------------------------------------------------------------------------------------------
def test_golden_roman_urdu_owner_stated_edge_and_cause():
    problems = [
        rec(
            "p1", "customers refuse parcels at the door", ["log darwaze par parcel le hi nahi lete"]
        ),
        rec("p2", "courier delivers late", ["courier late deliver"], subtype="delivery_late"),
    ]
    msgs = [
        "Hamara courier late deliver bhi karta hai, is liye log darwaze par parcel le hi nahi lete. "
        "Mera khayal hai courier isliye sust hai ke woh sab kuch ek depot se bhejta hai."
    ]
    gr = g.build_problem_graph(problems, msgs, None, "roman_ur")
    owner_edges = [e for e in gr.edges if e.kind is g.EdgeKind.OWNER_STATED]
    assert [(e.from_id, e.to_id) for e in owner_edges] == [("p2", "p1")]
    e = owner_edges[0]
    assert e.evidence_status == g.OWNER_SAID and not e.hypothesis and not e.confirmed
    assert e.strength == "strong" and "is liye" in e.evidence[0]
    cause = [s for s in gr.statements if s.reason == "cause_claim"]
    assert len(cause) == 1 and cause[0].problem_id == "p2" and cause[0].hedged
    assert cause[0].status == g.OWNER_SAID and cause[0].layer is g.Layer.ROOT_CAUSE_CANDIDATE
    assert cause[0].quote in msgs[0]
    assert gr.to_dict()["edges"][0]["kind"] in {k.value for k in g.EdgeKind}
    json.dumps(gr.to_dict(), ensure_ascii=False)


def test_golden_english_orders_cancelled_hypotheses_are_pi_inferred():
    p = rec(
        "p1",
        "orders cancelled before delivery",
        ["orders get cancelled before delivery"],
        subtype="orders_lost",
    )
    hs = g.hypotheses_for(
        p,
        {
            "owner_messages": [
                "Many orders get cancelled before delivery. Sometimes we are out of stock."
            ]
        },
        "en",
    )
    keys = [h.key for h in hs if h.source == "taxonomy"]
    for k in (
        "stock_unavailable",
        "order_processing_delay",
        "delivery_failure",
        "customer_unconfirmed",
        "wrong_contact_data",
        "cod_payment_issue",
        "inventory_sync",
        "communication_gap",
    ):
        assert k in keys
    assert all(h.status == g.PI_INFERRED for h in hs)
    first = hs[0]
    assert (
        first.key == "stock_unavailable"
        and first.supports
        and first.supports[0].status == g.OWNER_SAID
    )
    assert all(
        h.what_to_check and h.shown_text.startswith("A possibility to check")
        for h in hs
        if h.source == "taxonomy"
    )


def test_owner_stated_cause_is_not_offered_again_as_a_guess():
    p = rec(
        "p1",
        "orders cancelled",
        ["orders cancelled"],
        subtype="orders_lost",
        cause={
            "text": "we are out of stock",
            "status": "owner_said",
            "evidence": {"words": ["out of stock"]},
        },
    )
    hs = g.hypotheses_for(
        p, {"owner_messages": ["Orders cancelled because we are out of stock."]}, "en"
    )
    assert "stock_unavailable" not in [h.key for h in hs]


def test_contradicted_hypothesis_is_ranked_last_with_evidence():
    p = rec("p1", "orders cancelled", ["orders cancelled"], subtype="orders_lost")
    hs = g.hypotheses_for(
        p, {"owner_messages": ["Orders cancelled a lot. It is not out of stock, we checked."]}, "en"
    )
    h = next(x for x in hs if x.key == "stock_unavailable")
    assert h.contradicts and not h.supports
    tax = [x.key for x in hs if x.source == "taxonomy"]
    assert tax[-1] == "stock_unavailable"


def test_pack_hypotheses_are_english_and_labelled():
    p = rec(
        "p1",
        "flights half empty",
        ["domestic sectors fly half empty"],
        category="sales_revenue",
        industry="airlines",
    )
    hs = g.hypotheses_for(p, {}, "ur")
    packs = [h for h in hs if h.source == "pack"]
    assert packs and all(h.text_language == "en" and h.status == g.PI_INFERRED for h in packs)


# ---------------------------------------------------------------------------------------------
# Status rules (L2-2 semantics)
# ---------------------------------------------------------------------------------------------
def test_owner_said_cause_without_the_owners_words_becomes_pi_inferred():
    p = rec(
        "p1",
        "late rent",
        ["rent late"],
        category="cash_collections",
        cause={"text": "tenants forget", "status": "owner_said", "evidence": {"words": ["forget"]}},
    )
    gr = g.build_problem_graph([p], ["Rent comes late every month."], None, "en")
    st = [s for s in gr.statements if s.reason == "cause_record"]
    assert st and st[0].status == g.PI_INFERRED


def test_owner_said_cause_with_words_in_owner_text_stays_owner_said_and_confirmed_stays():
    p1 = rec(
        "p1",
        "late rent",
        ["rent late"],
        category="cash_collections",
        cause={"text": "tenants forget", "status": "owner_said", "evidence": {"words": ["forget"]}},
    )
    p2 = rec(
        "p2",
        "late repairs",
        ["repairs late"],
        category="operations_process",
        cause={"text": "tenants forget", "status": "confirmed", "evidence": {"words": ["forget"]}},
    )
    gr = g.build_problem_graph(
        [p1, p2], ["Tenants forget the due date. Repairs late too."], None, "en"
    )
    st = {s.problem_id: s.status for s in gr.statements if s.reason == "cause_record"}
    assert st == {"p1": g.OWNER_SAID, "p2": g.CONFIRMED}


def test_pi_inferred_cause_and_model_written_belief_never_owner_said():
    p = rec(
        "p1",
        "late rent",
        ["rent late"],
        category="cash_collections",
        cause={"text": "x", "status": "pi_inferred", "evidence": {"words": ["rent"]}},
        person_believes_cause="tenants forget",
    )
    gr = g.build_problem_graph([p], ["Rent late. Tenants forget."], None, "en")
    assert all(
        s.status == g.PI_INFERRED
        for s in gr.statements
        if s.layer in (g.Layer.ROOT_CAUSE_CANDIDATE, g.Layer.CONTRIBUTING_FACTOR)
    )


def test_no_edge_without_evidence_for_unrelated_problems():
    gr = g.build_problem_graph(
        [
            rec("a", "rent late", ["rent"], "cash_collections"),
            rec("b", "website slow", ["website"], "tech_systems"),
        ],
        ["Hello."],
        None,
        "en",
    )
    assert gr.edges == ()


def test_confirmed_links_promote_only_named_pair():
    ps = [
        rec("a", "rent late", ["rent"], "cash_collections"),
        rec("b", "dues late", ["dues"], "cash_collections"),
        rec("c", "slow", ["slow"], "cash_collections"),
    ]
    gr = g.build_problem_graph(ps, [], None, "en", confirmed_links=[("a", "b")])
    by = {frozenset((e.from_id, e.to_id)): e for e in gr.edges}
    assert by[frozenset("ab")].confirmed and by[frozenset("ab")].evidence_status == g.CONFIRMED
    assert not by[frozenset("ac")].confirmed and by[frozenset("ac")].hypothesis


def test_shared_cause_and_shared_resource_edges():
    ps = [
        rec(
            "a",
            "late deliveries",
            ["deliveries late"],
            cause={
                "text": "courier is slow",
                "status": "owner_said",
                "evidence": {"words": ["courier"]},
            },
        ),
        rec(
            "b",
            "returned parcels",
            ["parcels come back"],
            cause={
                "text": "the courier is slow",
                "status": "owner_said",
                "evidence": {"words": ["courier"]},
            },
        ),
    ]
    gr = g.build_problem_graph(
        ps, ["The courier is slow. Deliveries late and parcels come back."], None, "en"
    )
    kinds = {e.kind for e in gr.edges}
    assert g.EdgeKind.SHARED_CAUSE in kinds
    sc = next(e for e in gr.edges if e.kind is g.EdgeKind.SHARED_CAUSE)
    assert sc.evidence_status == g.OWNER_SAID and not sc.hypothesis
    ps2 = [dict(p, cause=None) for p in ps]
    gr2 = g.build_problem_graph(
        [
            rec("a", "courier late", ["courier late"]),
            rec("b", "courier lost parcels", ["courier lost"]),
        ],
        [],
        None,
        "en",
    )
    sr = [e for e in gr2.edges if e.kind is g.EdgeKind.SHARED_RESOURCE]
    assert sr and all(e.hypothesis and e.strength == "weak" for e in sr)
    assert ps2


def test_coverage_direct_shared_cause_and_directed_edges():
    ps = [
        rec("a", "late deliveries", ["deliveries late"]),
        rec("b", "customers cancel orders", ["customers cancel orders"]),
        rec("c", "rent late", ["rent"], "cash_collections"),
    ]
    gr = g.build_problem_graph(
        ps, ["Customers cancel orders because deliveries are late."], None, "en"
    )
    cov = g.coverage(["a"], gr)
    assert cov.direct == ("a",) and [v.problem_id for v in cov.through_shared_cause] == ["b"]
    assert all(v.hypothesis for v in cov.through_shared_cause)
    assert (
        g.coverage(["b"], gr).through_shared_cause == ()
    )  # fixing the effect does not address the cause
    assert g.coverage(["zzz"], gr).unknown_ids == ("zzz",)
    assert "c" in cov.not_covered


def test_learn_first_ranks_by_problems_explained_without_probability():
    ps = [
        rec("a", "orders cancelled", ["orders cancelled"], subtype="orders_lost"),
        rec("b", "late deliveries", ["deliveries late"], subtype="delivery_late"),
        rec("c", "rent late", ["rent late"], "cash_collections", "receivables_late"),
    ]
    gr = g.build_problem_graph(ps, [], None, "en")
    lf = gr.learn_first
    assert lf and lf[0].count >= lf[-1].count
    assert all(i.status in (g.PI_INFERRED, g.OWNER_SAID) for i in lf)
    top = next(i for i in lf if i.key == "order_processing_delay")
    assert set(top.explains) == {"a", "b"}
    assert "probab" not in json.dumps(gr.to_dict()).lower()


def test_priority_uses_only_stated_figures_and_reports_ties():
    ps = [
        {
            "id": "a",
            "title": "a",
            "frequency": {"normalised": "daily"},
            "impact": {"money_value": 5000, "money_text": "5000 rupees a month"},
        },
        {
            "id": "b",
            "title": "b",
            "frequency": {"normalised": "weekly"},
            "impact": {"money_value": 2000, "money_text": "2000 rupees a month"},
        },
        {
            "id": "c",
            "title": "c",
            "frequency": {"normalised": "weekly"},
            "impact": {"money_value": 2000, "money_text": "2000 rupees a month"},
        },
        {"id": "d", "title": "d"},
        {
            "id": "e",
            "title": "e",
            "frequency": {"normalised": "monthly"},
            "impact": {"money_value": 9000, "money_text": "9000 rupees a year"},
        },
    ]
    r = g.priority_order(ps)
    assert r.levels[0] == ("a", "e") or r.levels[0] == ("a",)
    assert ("a", "b", "frequency,money") in r.ordered_pairs
    lv = {x.problem_id: x.level for x in r.ranked}
    assert lv["b"] == lv["c"] > lv["a"]
    assert r.cannot_rank == ("d",) and not r.complete and "cannot rank yet" in r.note


def test_priority_drops_figure_the_owner_never_wrote():
    ps = [{"id": "a", "title": "a", "impact": {"money_value": 0, "money_text": "99999 rupees"}}]
    assert g.priority_order(ps, ["It costs us a lot."]).cannot_rank == ("a",)
    assert g.priority_order(ps, ["It costs us 99999 rupees."]).cannot_rank == ()


def test_layers():
    ps = [
        rec("a", "sales dropped", ["sales dropped"], "sales_revenue", "sales_drop"),
        rec("b", "I lose track of who reported", ["lose track"], "operations_process", "handoffs"),
        rec("c", "parcels come back late", ["late"], "orders_fulfilment"),
        rec("d", "", [], "orders_fulfilment"),
        rec("e", "something odd", ["odd thing"], "other"),
    ]
    gr = g.build_problem_graph(ps, [], None, "en")
    layers = {n.id: n.layer for n in gr.problems}
    assert layers["a"] is g.Layer.BUSINESS_CONSEQUENCE
    assert layers["b"] is g.Layer.OPERATIONAL_PROBLEM
    assert layers["c"] is g.Layer.SYMPTOM
    assert layers["d"] is g.Layer.UNVERIFIED
    assert layers["e"] is g.Layer.IMMEDIATE_PROBLEM


def test_problem_only_in_pi_note_is_unverified_when_owner_text_given():
    gr = g.build_problem_graph(
        [rec("a", "warehouse theft", ["pilferage"], "loss_security")],
        ["Hello there, rent is late."],
        None,
        "en",
    )
    assert gr.problems[0].layer is g.Layer.UNVERIFIED and gr.problems[0].status == g.PI_INFERRED


# ---------------------------------------------------------------------------------------------
# Adversarial multilingual (generated)
# ---------------------------------------------------------------------------------------------
PROBS = {
    "en": [
        rec("late", "late deliveries", ["deliveries come late"]),
        rec("cancel", "customers cancel orders", ["customers cancel their orders"]),
    ],
    "roman_ur": [
        rec("late", "deliveries late", ["deliveries late aati hain"]),
        rec("cancel", "customers orders cancel", ["customers apne orders cancel"]),
    ],
    "ur": [
        rec("late", "ڈیلیوری دیر", ["ڈیلیوری دیر سے آتی ہے"]),
        rec("cancel", "گاہک آرڈر منسوخ", ["گاہک اپنے آرڈر منسوخ"]),
    ],
    "ar": [
        rec("late", "التوصيل يتأخر", ["التوصيل يتأخر"]),
        rec("cancel", "العملاء يلغون الطلبات", ["العملاء يلغون الطلبات"]),
    ],
}
POS = {
    "en": [
        "Customers cancel their orders because the deliveries come late.",
        "Deliveries come late, so customers cancel their orders.",
    ],
    "roman_ur": [
        "Customers apne orders cancel kar dete hain kyun ke deliveries late aati hain.",
        "Deliveries late aati hain, is liye customers apne orders cancel kar dete hain.",
    ],
    "ur": [
        "گاہک اپنے آرڈر منسوخ کر دیتے ہیں کیونکہ ڈیلیوری دیر سے آتی ہے۔",
        "ڈیلیوری دیر سے آتی ہے اس لیے گاہک اپنے آرڈر منسوخ کر دیتے ہیں۔",
    ],
    "ar": ["العملاء يلغون الطلبات لأن التوصيل يتأخر.", "التوصيل يتأخر لذلك يلغي العملاء الطلبات."],
}
NEG = {
    "en": [
        "Is it because the deliveries come late that customers cancel their orders?",
        "Customers cancel their orders, not because the deliveries come late.",
        "If customers cancel their orders because deliveries come late, we lose money.",
    ],
    "roman_ur": [
        "Kya customers apne orders cancel karte hain kyun ke deliveries late aati hain?",
        "Customers apne orders cancel karte hain lekin deliveries late hone ki wajah se nahi.",
        "Agar customers apne orders cancel karein kyun ke deliveries late aati hain to nuqsan hota hai.",
    ],
    "ur": [
        "کیا گاہک اپنے آرڈر منسوخ کرتے ہیں کیونکہ ڈیلیوری دیر سے آتی ہے؟",
        "گاہک اپنے آرڈر منسوخ کرتے ہیں مگر ڈیلیوری دیر کی وجہ سے نہیں۔",
        "اگر گاہک اپنے آرڈر منسوخ کریں کیونکہ ڈیلیوری دیر سے آتی ہے تو نقصان ہوتا ہے۔",
    ],
    "ar": [
        "هل يلغي العملاء الطلبات لأن التوصيل يتأخر؟",
        "يلغي العملاء الطلبات ليس بسبب تأخر التوصيل.",
        "إذا ألغى العملاء الطلبات لأن التوصيل يتأخر فنخسر المال.",
    ],
}
NOISE = [
    "{}",
    "  {}  ",
    "{} Thanks.",
    "Hello. {}",
    "{} ok",
    "\n{}\n",
    "{} !!",
    "{} {}",
]


def _noise(s, fmt):
    return fmt.replace("{} {}", f"{s} {s}").replace("{}", s) if fmt != "{} {}" else f"{s} {s}"


@pytest.mark.parametrize("lang", list(POS))
@pytest.mark.parametrize("n", [0, 1])
@pytest.mark.parametrize("fmt", NOISE)
def test_positive_claims_give_a_directed_owner_stated_edge(lang, n, fmt):
    gr = g.build_problem_graph(PROBS[lang], [_noise(POS[lang][n], fmt)], None, lang)
    edges = [e for e in gr.edges if e.kind is g.EdgeKind.OWNER_STATED]
    assert [(e.from_id, e.to_id) for e in edges] == [("late", "cancel")], gr.to_dict()["edges"]
    assert edges[0].evidence_status == g.OWNER_SAID and not edges[0].hypothesis


@pytest.mark.parametrize("lang", list(NEG))
@pytest.mark.parametrize("n", [0, 1, 2])
@pytest.mark.parametrize("fmt", NOISE[:4])
def test_questions_denials_and_conditionals_make_no_claim(lang, n, fmt):
    gr = g.build_problem_graph(PROBS[lang], [_noise(NEG[lang][n], fmt)], None, lang)
    assert not [e for e in gr.edges if e.kind is g.EdgeKind.OWNER_STATED]
    assert not [s for s in gr.statements if s.reason.startswith("cause_claim")]


SUBTYPES = sorted(lx.SUBTYPE_CAUSES)


@pytest.mark.parametrize("lang", ["en", "roman_ur", "ur", "ar"])
@pytest.mark.parametrize("subtype", SUBTYPES)
def test_hypotheses_every_subtype_every_language(lang, subtype):
    hs = g.hypotheses_for(
        {"id": "p", "title": "x problem", "category": "orders_fulfilment", "subtype": subtype},
        None,
        lang,
    )
    tax = [h for h in hs if h.source == "taxonomy"]
    assert 2 <= len(tax) <= g.MAX_HYPOTHESES
    for h in hs:
        assert h.status == g.PI_INFERRED and h.text.strip() and h.what_to_check.strip()
        assert h.shown_text.startswith(lx.GUESS_PREFIX[lang]) or h.source == "pack"
    if lang in ("ur", "ar"):
        assert all(any("؀" <= c <= "ۿ" for c in h.text) for h in tax)


def test_every_catalogue_entry_is_complete():
    for key, e in lx.CAUSES.items():
        assert len(e["label"]) == 4 and len(e["check"]) == 4 and e["triggers"], key
        assert all(x.strip() for x in e["label"]) and all(
            x.strip()[-1] in "?؟" for x in e["check"]
        ), key
    used = {
        k
        for v in (*lx.SUBTYPE_CAUSES.values(), *lx.CATEGORY_CAUSES.values(), lx.FALLBACK_CAUSES)
        for k in v
    }
    assert used <= set(lx.CAUSES)


@pytest.mark.parametrize(
    "bad",
    [
        None,
        "",
        0,
        [],
        {},
        [None],
        ["x"],
        [{"id": 1}],
        [{"title": None, "user_words": 5}],
        object(),
        [[]],
        [{"cause": "x"}],
    ],
)
def test_never_raises_on_bad_input(bad):
    gr = g.build_problem_graph(bad, bad, bad, "klingon")
    assert gr.language == "en"
    g.hypotheses_for(bad, bad, "zz")
    g.coverage(bad, gr)
    g.learn_first(gr)
    g.priority_order(bad, bad)
    json.dumps(gr.to_dict(), ensure_ascii=False)


# ---------------------------------------------------------------------------------------------
# Property and fuzz
# ---------------------------------------------------------------------------------------------
def _check_graph(gr, msgs_text):
    ids = {n.id for n in gr.problems}
    for e in gr.edges:
        assert e.evidence and all(x.strip() for x in e.evidence)
        assert e.from_id in ids and e.to_id in ids and e.from_id != e.to_id
        assert e.strength in g.STRENGTH_RANK and e.strength_rank == g.STRENGTH_RANK[e.strength]
        if e.kind is g.EdgeKind.OWNER_STATED:
            assert e.evidence_status in OWNER and not e.hypothesis
        if e.evidence_status == g.PI_INFERRED:
            assert e.hypothesis and not e.confirmed
        if e.kind in (g.EdgeKind.CATEGORY_FAMILY, g.EdgeKind.SHARED_RESOURCE) and not e.confirmed:
            assert e.hypothesis
        assert e.confirmed == (e.evidence_status == g.CONFIRMED)
    for s in gr.statements:
        if s.status == g.OWNER_SAID and s.reason.startswith("cause_claim"):
            assert s.quote and s.quote in msgs_text
    for _pid, hs in gr.hypotheses:
        assert all(h.status == g.PI_INFERRED for h in hs)
    for it in gr.learn_first:
        assert it.count == len(it.explains) >= 1


WORDS = "courier late stock rent staff register parcel order cancel refund because is liye kyun ke so hai nahi کیونکہ اس لیے لأن لذلك بسبب the a of customers deliveries ڈیلیوری العملاء ? . , !".split()


@pytest.mark.parametrize("seed", range(60))
def test_fuzz_random_inputs_keep_every_invariant(seed):
    r = random.Random(seed)

    def sent():
        return " ".join(r.choice(WORDS) for _ in range(r.randint(2, 14)))

    msgs = [". ".join(sent() for _ in range(r.randint(1, 6))) for _ in range(r.randint(0, 5))]
    cats = list(g.taxonomy.BY_KEY)
    ps = []
    for i in range(r.randint(0, 9)):
        ps.append(
            rec(
                f"p{i}",
                sent()[:60],
                [sent()[:50]],
                r.choice(cats),
                r.choice(["", "stockout", "delivery_late", "x"]),
                cause=r.choice(
                    [
                        None,
                        {
                            "text": sent(),
                            "status": r.choice(["owner_said", "pi_inferred", "confirmed", "zzz"]),
                            "evidence": {"words": [r.choice(WORDS)]},
                        },
                    ]
                ),
            )
        )
    gr = g.build_problem_graph(ps, msgs, None, r.choice(list(lx.LANGUAGES)))
    _check_graph(gr, "\n".join(msgs))
    assert (
        gr.to_dict() == g.build_problem_graph(ps, msgs, None, gr.language).to_dict()
    )  # deterministic


def test_pi_inferred_is_never_presented_as_confirmed_over_many_random_graphs():
    r = random.Random(7)
    for _ in range(80):
        msgs = [" ".join(r.choice(WORDS) for _ in range(12)) + "."]
        ps = [
            rec(
                "a",
                "late courier",
                ["late courier"],
                cause={
                    "text": "courier slow",
                    "status": "pi_inferred",
                    "evidence": {"words": ["courier"]},
                },
            ),
            rec(
                "b",
                "stock out",
                ["stock"],
                cause={
                    "text": "courier slow",
                    "status": "pi_inferred",
                    "evidence": {"words": ["courier"]},
                },
            ),
        ]
        gr = g.build_problem_graph(ps, msgs, None, "en")
        assert not any(
            e.confirmed or e.evidence_status in OWNER
            for e in gr.edges
            if e.kind is g.EdgeKind.SHARED_CAUSE
        )
        assert all(s.status == g.PI_INFERRED for s in gr.statements if s.reason == "cause_record")


def test_caps_hold():
    ps = [rec(f"p{i}", f"courier late {i}", ["courier"], "orders_fulfilment") for i in range(500)]
    gr = g.build_problem_graph(ps, ["x. " * 5000] * 300, None, "en")
    assert len(gr.problems) == g.MAX_PROBLEMS and gr.truncated
    for kind in g.EdgeKind:
        assert sum(e.kind is kind for e in gr.edges) <= g.MAX_EDGES_PER_KIND


def test_fold_maps_back_to_the_owners_characters():
    text = "كيف  حالُك؟ Rent ٥٠٠٠ ."
    folded, idx = g.fold(text)
    assert len(folded) == len(idx) and "5000" in folded
    assert all(0 <= i < len(text) for i in idx)


# ---------------------------------------------------------------------------------------------
# Timing: growth ratio for 10x input must stay near linear
# ---------------------------------------------------------------------------------------------
def _timed(chars):
    base = "Customers cancel orders because deliveries are late. The courier is slow, so parcels come back. "
    msgs = [(base * 25)[: min(2000, chars)] for _ in range(max(1, chars // 2000))]
    ps = [
        rec(f"p{i}", t, [t], c)
        for i, (t, c) in enumerate(
            [
                ("late deliveries", "orders_fulfilment"),
                ("customers cancel orders", "orders_fulfilment"),
                ("parcels come back", "orders_fulfilment"),
                ("rent late", "cash_collections"),
            ]
        )
    ]
    best = 1e9
    g.build_problem_graph(ps, msgs[:1], None, "en")  # warm-up (pack index, regex caches)
    for _ in range(3):
        t0 = time.perf_counter()
        g.build_problem_graph(ps, msgs, None, "en")
        best = min(best, time.perf_counter() - t0)
    return best


def test_timing_growth_is_near_linear():
    t1, t10, t100 = _timed(1_000), _timed(10_000), _timed(100_000)
    print(
        f"timing 1k={t1:.4f}s 10k={t10:.4f}s 100k={t100:.4f}s ratios {t10 / t1:.1f} {t100 / t10:.1f}"
    )
    assert t100 / max(t10, 1e-4) < 25 and t10 / max(t1, 1e-4) < 25
    assert t100 < 10


# ---------------------------------------------------------------------------------------------
# Added after the mutation pass (each kills a surviving mutant)
# ---------------------------------------------------------------------------------------------
def test_rhetorical_question_is_not_a_claim():
    gr = g.build_problem_graph(
        PROBS["en"], ["Customers cancel their orders because the deliveries come late?"], None, "en"
    )
    assert not [e for e in gr.edges if e.kind is g.EdgeKind.OWNER_STATED]
    assert not [s for s in gr.statements if s.reason.startswith("cause_claim")]


def test_shared_cause_with_one_guess_is_a_hypothesis():
    owner = {"text": "courier is slow", "status": "owner_said", "evidence": {"words": ["courier"]}}
    guess = {"text": "courier is slow", "status": "pi_inferred", "evidence": {"words": ["courier"]}}
    ps = [
        rec("a", "late deliveries", ["deliveries late"], cause=owner),
        rec("b", "returned parcels", ["parcels back"], cause=guess),
    ]
    gr = g.build_problem_graph(ps, ["The courier is slow."], None, "en")
    sc = next(e for e in gr.edges if e.kind is g.EdgeKind.SHARED_CAUSE)
    assert sc.evidence_status == g.PI_INFERRED and sc.hypothesis and sc.strength == "weak"


def test_learn_first_leaves_out_a_contradicted_guess_and_names_it():
    p = rec("a", "orders cancelled", ["orders cancelled"], subtype="orders_lost")
    gr = g.build_problem_graph([p], ["Orders cancelled. It is not out of stock."], None, "en")
    keys = {i.key for i in gr.learn_first}
    assert "stock_unavailable" not in keys
    contradicted = [h.key for h in gr.hypotheses_of("a") if h.contradicts and not h.supports]
    assert contradicted == ["stock_unavailable"]


def test_learn_first_keeps_explained_guess_with_ruled_against_on_other_problem():
    ps = [
        rec("a", "orders cancelled", ["orders cancelled"], subtype="orders_lost"),
        rec("b", "orders lost", ["orders lost"], subtype="orders_lost"),
    ]
    gr = g.build_problem_graph(
        ps, ["Orders cancelled. Orders lost. We are out of stock sometimes."], None, "en"
    )
    item = next(i for i in gr.learn_first if i.key == "stock_unavailable")
    assert set(item.explains) == {"a", "b"} and item.status == g.PI_INFERRED


def test_confirmed_note_status_is_confirmed_and_guess_note_is_not():
    ps = [
        rec("a", "rent late", ["rent late"], "cash_collections", status="confirmed"),
        rec("b", "dues late", ["dues"], "cash_collections", status="draft"),
    ]
    gr = g.build_problem_graph(ps, ["Rent late every month."], None, "en")
    st = {n.id: n.status for n in gr.problems}
    assert st["a"] == g.CONFIRMED and st["b"] != g.CONFIRMED


def test_money_in_different_periods_is_not_compared():
    ps = [
        {"id": "a", "impact": {"money_value": 9000, "money_text": "9000 rupees a month"}},
        {"id": "b", "impact": {"money_value": 100, "money_text": "100 rupees a year"}},
    ]
    r = g.priority_order(ps)
    assert r.ordered_pairs == () and r.levels == (("a", "b"),) and not r.complete


def test_merged_and_withdrawn_problems_are_left_out():
    ps = [
        rec("a", "rent late", ["rent"], "cash_collections", status="merged"),
        rec("b", "dues late", ["dues"], "cash_collections", status="withdrawn"),
        rec("c", "slow", ["slow"], "cash_collections"),
    ]
    assert [n.id for n in g.build_problem_graph(ps, [], None, "en").problems] == ["c"]
