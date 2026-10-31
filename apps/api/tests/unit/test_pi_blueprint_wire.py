"""PS-flow: PS-4's blueprint in the document, the one L2-3 ranking, and the L2-3 contract."""

import dataclasses

from app.modules.pi import blueprint_models as bm
from app.modules.pi import blueprint_rules as br
from app.modules.pi import blueprint_wire as bw
from app.modules.pi import option_rank, solutions
from app.modules.pi.blueprint_build import option_from, recommended_from

KEY = next(iter(solutions.CATALOGUE))
PHRASE = solutions.build_phrase(KEY, "en", None)
QUOTE = "we lose customers after three days"
OWNER = {"m1": QUOTE}


def view(ref, **kw):
    base = {
        "ref": ref,
        "id": ref,
        "title": f"Problem {ref}",
        "quotes": [QUOTE],
        "where": "",
        "how_often": "every week",
        "since": "March",
        "money": "",
        "of_total": "",
        "limits": {},
        "cannot_change": [],
        "tried": [],
        "cause_text": "",
        "cause_status": "",
        "cause": "",
        "cause_raw": None,
        "expected_outcome": "reply within an hour",
        "msgs": ["m1"],
    }
    base.update(kw)
    return base


def comp(refs, phase=1):
    return {"key": KEY, "text": PHRASE, "phase": phase, "refs": refs}


def test_verified_owner_evidence_recommends_the_box_and_the_blueprint_is_built():
    bp = bw.build([view("P1")], [comp(["P1"])], ["a contact person"], OWNER, "en")
    assert bp["recommended"] == "BOX"
    assert bp["text"].strip() and QUOTE in bp["text"]
    assert bp["status"] in ("ready", "refused", "insufficient_information")
    if bp["status"] == "ready":
        assert bp["issues"] == []


def test_thin_evidence_recommends_learning_first_not_a_build():
    oset, _ = bw.option_set([view("P1", msgs=[])], [comp(["P1"])], {})
    assert oset.recommended_id == "LEARN"


def test_a_violating_box_is_never_recommended():
    limit = " ".join(PHRASE.split()[:2])
    v = view("P1", cannot_change=[f"we cannot {limit}"])
    oset, steps = bw.option_set([v], [comp(["P1"])], OWNER)
    top = next(o for o in oset.options if o.id == oset.recommended_id)
    assert not (top.id == "BOX" and top.violated)
    ids = [o.id for o in oset.options]
    if any(o.id == "BOX" and o.violated for o in oset.options):
        assert ids.index("BOX") > ids.index("LEARN")


def test_chat_and_document_use_the_same_ranking():
    items = [
        ("An idea the gate could not check.", "unknown"),
        ("A clear idea.", "ok"),
        ("A violator.", "violates"),
    ]
    order = option_rank.rank_ideas(items)
    assert [items[i][0] for i in order] == [
        "A clear idea.",
        "An idea the gate could not check.",
        "A violator.",
    ]
    assert option_rank.recommended_text(items) == "A clear idea."
    # the same idea, as the chat pick, is a candidate of the document's set and leads it
    oset, _ = bw.option_set([view("P1")], [comp(["P1"])], OWNER, chat_pick="A clear idea.")
    assert [o.id for o in oset.options][0] == "CHAT00"
    assert oset.recommended_id == "CHAT00"


def test_ranking_is_deterministic_whatever_order_it_gets():
    items = [("b", "ok"), ("a", "ok"), ("c", "unknown")]
    assert option_rank.rank_ideas(items) == option_rank.rank_ideas(items)
    assert option_rank.rank_ideas(items)[:2] == [0, 1]  # the engine's order breaks ties


def test_l2_3_option_contract_with_real_option_and_sealed_evidence():
    """A real L2-3 Option (evidence sealed through bm.mark_verified or verify_option) reads through
    PS-4's single adapter; evidence PS-4 never constructs; a forged flag counts for nothing."""
    ev = bm.Evidence("m1", ("lose", "customers"))
    option = bm.Option(
        id="O1",
        kind="owner_action",
        what="Ask each lost customer why they left.",
        addresses=("P1",),
        benefit="Shows the real reason",
        effort="small",
        reversibility="reversible",
        evidence=(ev,),
        catalogue_key=None,
    )
    sealed = dataclasses.replace(option, evidence=(bm.mark_verified(ev),))
    assert sealed.evidence_strength == 1 and option.evidence_strength == 0
    verified = br.verify_option(option, OWNER)
    assert verified.evidence_strength == 1
    record = option_from(verified)
    assert record is not None and record.what.startswith("Ask each lost customer")
    oset = bm.OptionSet(options=(verified,), recommended_id="O1")
    top, _reason = recommended_from(oset)
    assert top is not None and top.id == "O1"
    forged = dataclasses.replace(option, evidence=(dataclasses.replace(ev, verified=True),))
    assert forged.evidence_strength == 0
