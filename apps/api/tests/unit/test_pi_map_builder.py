"""The map built from noted problems and the rule for when pi shares it (Book 5, 4.2 to 4.4)."""

from decimal import Decimal
from types import SimpleNamespace as NS
from uuid import uuid4

from app.modules.pi import map_builder as mb
from app.modules.pi import map_render


def problem(number, title="Stock stuck", local="", words=(), status="confirmed", tags=(), **kw):
    return NS(
        id=uuid4(),
        number=number,
        title=title,
        title_local=local,
        user_words=list(words),
        status=status,
        tags=list(tags),
        category=kw.get("category", "stock_inventory"),
        impact=kw.get("impact", {}),
        since=kw.get("since", {}),
        frequency=kw.get("frequency", {}),
        scope=kw.get("scope", {}),
        merged_into=kw.get("merged_into"),
    )


def link(a, b, kind="causes", evidence="owner_said", status="suggested", confidence="0.8"):
    return NS(
        from_id=a.id,
        to_id=b.id,
        type=kind,
        evidence=evidence,
        status=status,
        confidence=Decimal(confidence),
    )


def test_labels_use_the_owners_words_then_the_english_title():
    assert mb.label_of(problem(1, local="purana maal ruka hai", words=['"x"'])) == (
        "purana maal ruka hai"
    )
    assert mb.label_of(problem(1, words=['"maal phansa hai"'])) == "maal phansa hai"
    assert mb.label_of(problem(1, title="Dead stock")) == "Dead stock"
    long = problem(1, local="one two three four five six seven eight nine ten")
    assert mb.label_of(long) == "one two three four five six seven eight nine"


def test_labels_and_facts_are_redacted_and_facts_come_only_from_the_owner():
    p = problem(
        1,
        local="call me on 0300 1234567 maal",
        impact={"money_text": "6 crore on cost", "time_text": ""},
        since={"text": "since last year"},
        scope={"of_total": "2 of 4 shops"},
    )
    node = mb.build_map([p], [])["nodes"][0]
    assert "1234567" not in node["label"]
    assert node["facts"] == ["6 crore on cost", "since last year", "2 of 4 shops"]
    assert mb.build_map([problem(2)], [])["nodes"][0]["facts"] == []


def test_withdrawn_merged_are_left_out_resolved_and_parked_stay():
    a = problem(1, status="withdrawn")
    b = problem(2, status="resolved")
    c = problem(3, tags=["parked"])
    d = problem(4, merged_into=uuid4())
    e = problem(5)
    nodes = mb.build_map([a, b, c, d, e], [])["nodes"]
    assert [(n["id"], n["status"]) for n in nodes] == [
        ("P2", "resolved"),
        ("P3", "parked"),
        ("P5", "open"),
    ]


def test_links_need_evidence_and_known_types_and_both_ends():
    a, b, c = problem(1), problem(2), problem(3)
    gone = problem(4, status="withdrawn")
    links = [
        link(a, b),
        link(b, c, "same_root_suspected", "pi_inferred", confidence="0.7"),
        link(a, c, "same_area"),
        link(a, gone),
        link(c, a, "worsens", "pi_inferred", confidence="0.2"),  # too unsure to draw
        link(b, a, "blocks", status="rejected"),
        link(a, b),  # duplicate
        link(c, b, "competes", "pi_inferred", status="confirmed"),
    ]
    out = mb.build_map([a, b, c, gone], links)["links"]
    assert out == [
        {"from": "P1", "to": "P2", "type": "causes", "label": "", "evidence": "owner_said"},
        {"from": "P2", "to": "P3", "type": "same_root", "label": "", "evidence": "pi_inferred"},
        {"from": "P3", "to": "P2", "type": "competes", "label": "", "evidence": "confirmed"},
    ]


def test_cluster_root_is_the_node_with_most_outgoing_causes_or_blocks():
    a, b, c, d = (problem(n) for n in (1, 2, 3, 4))
    built = mb.build_map([a, b, c, d], [link(b, a), link(b, c, "blocks"), link(a, c)])
    [cluster] = built["clusters"]
    assert cluster["root"] == "P2" and cluster["node_ids"] == ["P1", "P2", "P3"]
    assert cluster["title"] == mb.label_of(b)
    # a symptom_of link points at its cause: the cause is the root
    sym = mb.build_map([a, b], [link(a, b, "symptom_of")])["clusters"][0]
    assert sym["root"] == "P2"
    assert mb.build_map([a, b], [])["clusters"] == []


def test_is_new_is_against_the_previous_version():
    a, b = problem(1), problem(2)
    first = mb.build_map([a], [], version=1)
    assert first["nodes"][0]["is_new"] is False  # nothing before it to be new against
    second = mb.build_map([a, b], [], version=2, previous=first)
    assert [n["is_new"] for n in second["nodes"]] == [False, True]


def test_the_hash_ignores_version_and_new_tags_but_not_what_the_owner_sees():
    a, b = problem(1), problem(2)
    v1 = mb.build_map([a, b], [], version=1)
    v2 = mb.build_map([a, b], [], version=2, previous=mb.build_map([a], [], version=1))
    assert v1["hash"] == v2["hash"]
    assert mb.build_map([a, b], [link(a, b)])["hash"] != v1["hash"]
    renamed = problem(2)
    renamed.id, renamed.title_local = b.id, "naya naam"
    assert mb.build_map([a, renamed], [])["hash"] != v1["hash"]


def test_the_map_can_be_drawn():
    a, b = problem(1, local="maal ruka hai"), problem(2, local="paisa phansa")
    built = mb.build_map([a, b], [link(a, b)], version=3, previous=mb.build_map([a], []))
    drawn = map_render.render_map(built, "roman_ur")
    assert drawn.images and drawn.drawable


def facts(**kw):
    return mb.ShareFacts(**kw)


def test_first_map_needs_three_problems_or_two_with_a_link():
    assert mb.share_due(facts(nodes=3)) == (True, "first")
    assert mb.share_due(facts(nodes=2, links=1)) == (True, "first")
    assert mb.share_due(facts(nodes=2)) == (False, "not_enough")
    assert mb.share_due(facts(nodes=1, links=0)) == (False, "not_enough")
    assert mb.share_due(facts()) == (False, "empty")


def test_first_map_waits_for_openness_and_a_calm_owner():
    assert mb.share_due(facts(nodes=4, openness=0)) == (False, "closed")
    assert mb.share_due(facts(nodes=4, hurried=True)) == (False, "hurried")


def test_hurried_owner_gets_it_when_asked_or_at_the_offer():
    assert mb.share_due(facts(nodes=1, hurried=True, asked=True)) == (True, "asked")
    assert mb.share_due(facts(nodes=4, hurried=True, at_offer=True)) == (True, "offer")


def test_update_needs_a_linked_new_problem_or_two_new_problems():
    base = {"nodes": 5, "ever_shared": True, "pi_messages_since_share": 6}
    assert mb.share_due(facts(**base, new_nodes=1, new_node_linked=True)) == (True, "update")
    assert mb.share_due(facts(**base, new_nodes=2)) == (True, "update")
    assert mb.share_due(facts(**base, new_nodes=1)) == (False, "no_change")
    assert mb.share_due(facts(**base)) == (False, "no_change")


def test_at_most_one_share_per_six_pi_messages_unless_asked():
    base = {"nodes": 5, "ever_shared": True, "new_nodes": 3, "pi_messages_since_share": 5}
    assert mb.share_due(facts(**base)) == (False, "limit")
    assert mb.share_due(facts(**{**base, "pi_messages_since_share": 6})) == (True, "update")
    assert mb.share_due(facts(**base, asked=True)) == (True, "asked")


def test_new_since_counts_new_problems_and_their_links():
    a, b, c = problem(1), problem(2), problem(3)
    shared = mb.build_map([a], [])
    latest = mb.build_map([a, b, c], [link(a, b)])
    assert mb.new_since(shared, latest) == (2, True)
    assert mb.new_since(shared, mb.build_map([a, c], [])) == (1, False)
    assert mb.new_since(None, latest) == (3, True)
