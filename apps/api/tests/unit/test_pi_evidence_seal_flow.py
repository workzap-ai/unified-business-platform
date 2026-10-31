"""A stored or rebuilt Evidence proves nothing until verify_option runs against the owner's
messages (L2-3 private seal, PS-flow)."""

import dataclasses
import json

from app.modules.pi import blueprint_models as bm
from app.modules.pi import blueprint_rules as br

MSGS = {"m1": "we lose customers after three days"}


def option(ev):
    return bm.Option(
        id="O1",
        kind="workzap_build",
        what="x",
        addresses=("P1",),
        benefit="b",
        effort="small",
        reversibility="reversible",
        catalogue_key="k",
        evidence=(ev,),
    )


def test_rebuilt_evidence_counts_for_nothing_until_verified():
    sealed = bm.mark_verified(bm.Evidence("m1", ("lose", "customers")))
    opt = option(sealed)
    assert opt.evidence_strength == 1
    data = opt.to_dict()
    assert "seal" not in data["evidence"][0]
    for rebuilt in (
        bm.Evidence(**data["evidence"][0]),
        bm.Evidence(**json.loads(json.dumps(data["evidence"][0]))),
        bm.Evidence(**{**data["evidence"][0], "verified": True}),
        dataclasses.replace(sealed, seal=object()),
    ):
        assert option(rebuilt).evidence_strength == 0
        assert not br.recommendable(option(rebuilt))
        assert br.recommendable(option(rebuilt), MSGS)  # verified against the owner's message
    assert (
        br.verify_option(option(bm.Evidence("m1", ("lose", "customers"))), MSGS).evidence_strength
        == 1
    )
    wrong = {"m1": "something else entirely"}
    assert (
        br.verify_option(option(bm.Evidence("m1", ("lose", "customers"))), wrong).evidence_strength
        == 0
    )
