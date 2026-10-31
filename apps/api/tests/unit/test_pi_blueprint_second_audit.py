"""L2-3 second audit: wordings the first patterns missed, a non-mapping owner record, hand-built
verified flags, speaker ids, ranking ties and four mutants that had survived. Each test fails
against the previous commit (5ec43a6)."""

import pytest

from app.modules.pi import blueprint_models as bm
from app.modules.pi import blueprint_rules as br
from app.modules.pi import blueprint_text as bt
from app.modules.pi.constitution import PROMISE

P = {"P1", "P2"}
OWNER = "Honestly we never count stock at night"


def sealed(msg="m1", words=("count", "stock")):
    return bm.Evidence(msg, tuple(words), verified=True, seal=bm.SEAL)


def option(**over) -> bm.Option:
    base = {
        "id": "O1",
        "kind": "process_change",
        "what": "A short checklist would be agreed for the evening count",
        "addresses": ("P1",),
        "benefit": "The owner would see the same numbers every morning",
        "effort": "small",
        "reversibility": "reversible",
        "evidence": (sealed(),),
    }
    base.update(over)
    return bm.Option(**base)


def codes(issues) -> list[str]:
    return [i.code for i in issues]


# --- promises --------------------------------------------------------------------------------

PROMISES = [
    # English
    "We promise it works",
    "It never fails",
    "cannot fail",
    "won't fail",
    "you can't lose",
    "zero risk",
    "no chance of failure",
    "bound to work",
    "sure thing",
    "sure bet",
    "without a doubt",
    "undoubtedly",
    "absolutely works",
    "a certainty",
    "trust me",
    "I swear",
    "proven to work",
    "it's going to boost sales",
    "this ensures",
    "expect to double",
    "one hundred percent safe",
    # Roman Urdu
    "lazmi",
    "yaqeenan",
    "kabhi fail nahi",
    "hamesha kaam karta",
    "bina shak",
    "sau percent",
    "sau fisad",
    "jarur hoga",
    # Urdu
    "کوئی خطرہ نہیں",
    "سو فیصد",
    "یقیناً",
    "کبھی ناکام نہیں",
    "ہمیشہ",
    "شرطیہ",
    # Hindi
    "बिना जोखिम",
    "सौ प्रतिशत",
    "कभी फेल नहीं",
    "हमेशा",
    "शर्तिया",
    "अवश्य",
    # Arabic
    "لا مخاطرة",
    "مئة بالمئة",
    "لن يفشل أبدا",
    "دائما ينجح",
    "بلا شك",
    "بكل تأكيد",
    "سيزيد مبيعاتك",
    # invented savings and outcomes
    "saves two hours a day",
    "cuts your costs in half",
    "saves you 20 percent",
    "cut wait times by half",
    "reduce missed orders by 30%",
    "double your sales",
    "triple your sales",
    "10x your revenue",
    "gets you 20% more orders",
    "owners typically save five hours a week",
    "ROI within a month",
    "pays for itself",
    # obfuscation
    "g u a r a n t e e d",
    "guaran-\nteed",
    "guar\tanteed",
    "gu​aranteed",
    "1 0 0 %",
    "100٪",
    "100％",
    "100﹪",
]

DENIED_OR_CLEAN = [
    "I can't guarantee anything",
    "not guaranteed",
    "guarantee nahi de sakta",
    "no guarantee",
    "We cannot promise anything",
    "ضمانت نہیں دے سکتا",
    "गारंटी नहीं दे सकता",
    "لا أضمن النتيجة",
    "It would help the morning check",
    "It will not replace the till",
    "It affects a certain shelf",
    "The count would be checked every time it is skipped",
    "reduce the risk of one error",
    "double check the count",
    "two options",
]


@pytest.mark.parametrize("text", PROMISES)
def test_a_promise_or_an_invented_outcome_is_caught_in_what(text):
    assert bt.promise_in(text, PROMISE, bt.WILL), text
    assert "OPT-PROMISE" in codes(br.option_issues(option(what=text), P)), text


@pytest.mark.parametrize("text", PROMISES[:12])
def test_the_same_wordings_are_caught_in_a_risk_and_a_dependency(text):
    risky = option(risks=(bm.Risk(text, "low"),))
    assert "OPT-PROMISE" in codes(br.option_issues(risky, P)), text
    dep = option(dependencies=(bm.Dependency("data", text),))
    assert "OPT-PROMISE" in codes(br.option_issues(dep, P)), text


@pytest.mark.parametrize("text", DENIED_OR_CLEAN)
def test_a_denied_guarantee_and_plain_text_are_not_promises(text):
    assert not bt.promise_in(text, PROMISE, bt.WILL), text


def test_a_denied_guarantee_does_not_hide_a_promise_next_to_it():
    assert bt.promise_in("I can't guarantee anything but it never fails", PROMISE, bt.WILL)


@pytest.mark.parametrize("sign", ["٪", "﹪", "％"])
def test_every_percent_sign_folds_to_a_percent(sign):
    assert bt.fold(f"30{sign}") == "30%"
    assert bt.fold(f"٣٠{sign}") == "30%"


# --- money and cost claims -------------------------------------------------------------------

MONEY = [
    "free of charge",
    "at no cost",
    "zero cost",
    "kam kharcha",
    "bilkul muft",
    "مفت",
    "मुफ़्त",
    "r s 5 0 0 0",
    "p k r 5000",
    "5OOOO",
    "5 lak",
    "5 laakh",
    "five grand",
    "two hundred",
    "do sau",
    "dus hazaar",
    "3000/-",
    "خمسة آلاف",
    "ألف ريال",
]

NOT_MONEY = [
    "+92 300 1234567",
    "0300-1234567",
    "call 0300 1234567",
    "order #12345",
    "in 2024",
    "two options",
    "12 people",
    "30 percent",
]


@pytest.mark.parametrize("text", MONEY)
def test_an_obfuscated_amount_or_a_cost_claim_is_money(text):
    assert bt.money_in(text), text
    assert "OPT-MONEY" in codes(br.option_issues(option(benefit=text), P)), text


@pytest.mark.parametrize("text", NOT_MONEY)
def test_a_phone_number_a_reference_a_year_and_a_count_are_not_money(text):
    assert not bt.money_in(text), text


def test_the_owners_expected_outcome_may_still_name_money():
    issues = br.option_issues(option(expected_outcome="I want it free of charge"), P)
    assert "OPT-MONEY" not in codes(issues)


def test_a_nine_digit_run_with_a_leading_zero_is_not_money_but_eight_digits_are():
    assert not bt.money_in("012345678")
    assert bt.money_in("12345678")


def test_a_figure_before_a_percent_sign_is_not_money_even_with_a_space():
    for text in ("50000%", "50000 %", "50000 percent", "50000 per cent"):
        assert not bt.money_in(text), text


# --- an owner record that is not a mapping never makes anything raise ------------------------

BAD_RECORDS = [0, 1.5, "x", (1,), [1], object()]


@pytest.mark.parametrize("record", BAD_RECORDS)
def test_a_non_mapping_owner_record_proves_nothing_and_never_raises(record):
    thing = option()
    assert br.rank_options([thing, option(id="O2")], record)
    assert br.recommendable(thing, record) is False
    assert br.evidence_thin([thing], record) is True
    assert br.strength(thing, record) == 0
    assert br.verify_option(thing, record).evidence_strength == 0
    assert "MALFORMED" in codes(br.option_issues(thing, P, owner_messages=record))


def test_non_string_arguments_never_raise():
    for cause, text in ((None, "x"), ("a b", None), (5, 6), (["a"], {"b"})):
        assert bt.states_as_fact(cause, text) is False
    assert br.strength(None) == 0
    assert br.recommendable(None) is False
    assert br.rank_options(None, 0) == ()


# --- a hand-built verified flag counts for nothing --------------------------------------------


def test_a_verified_flag_set_by_hand_is_not_evidence():
    forged = option(evidence=(bm.Evidence("m1", ("count",), verified=True),))
    assert br.strength(forged) == 0
    assert forged.evidence_strength == 0
    assert br.recommendable(forged) is False
    assert br.evidence_thin([forged]) is True
    assert "OPT-EVIDENCE" in codes(br.option_issues(forged, P))


def test_verify_option_is_what_makes_a_ref_count():
    claimed = option(evidence=(bm.Evidence("m1", ("count",)),))
    owner = {"m1": "we never count stock at night"}
    assert br.strength(claimed) == 0
    proven = br.verify_option(claimed, owner)
    assert proven.evidence_strength == 1
    assert br.recommendable(proven) is True
    assert br.option_issues(proven, P) == []


def test_an_option_with_no_evidence_has_nothing_to_flag_and_the_seal_is_not_serialised():
    assert br.option_issues(option(evidence=()), P) == []
    ref = option().to_dict()["evidence"][0]
    assert "seal" not in ref and ref["verified"] is True


# --- the speaker in a message id ---------------------------------------------------------------


@pytest.mark.parametrize(
    "msg", ["ai-1", "llm-1", "workzap-pi-1", "assistant5", "Assistant_5", "pi3", "bot:9"]
)
def test_an_id_that_names_another_speaker_is_not_the_owners(msg):
    ref = bm.Evidence(msg, ("count", "stock"))
    issues = br.option_issues(option(evidence=(ref,)), P, owner_text=OWNER)
    assert "OPT-EVIDENCE" in codes(issues), msg


@pytest.mark.parametrize("msg", ["m1", "m12", "msg-77", "3f2a9c1e-07b4", "42"])
def test_an_ordinary_owner_id_is_accepted_against_the_owners_text(msg):
    ref = bm.Evidence(msg, ("count", "stock"))
    issues = br.option_issues(option(evidence=(ref,)), P, owner_text=OWNER)
    assert "OPT-EVIDENCE" not in codes(issues), msg


# --- ties ---------------------------------------------------------------------------------------


def test_options_equal_in_id_what_and_benefit_rank_the_same_whatever_the_input_order():
    a = option(risks=(bm.Risk("a first risk"),))
    b = option(risks=(bm.Risk("a second risk"),))
    c = option(dependencies=(bm.Dependency("data", "the till export"),))
    d = option(trade_offs=("one more daily step",))
    forward = br.rank_options([a, b, c, d])
    for order in ([d, c, b, a], [b, d, a, c], [c, a, d, b]):
        assert br.rank_options(order) == forward


# --- survivors ------------------------------------------------------------------------------------


def test_a_rejected_option_with_no_reason_was_not_compared():
    live = option(id="A")
    unexplained = option(id="B", status="rejected", rejected_because="")
    issues = br.set_issues(bm.OptionSet((live, unexplained)), P)
    assert "SET-COUNT" in codes(issues)
    single = bm.OptionSet((live, unexplained), single_option=True, single_reason="only one fits")
    assert "SET-SINGLE" not in codes(br.set_issues(single, P))


def test_a_rejected_option_does_not_make_the_evidence_thick():
    rejected = option(id="A", status="rejected", rejected_because="too slow")
    bare = option(id="B", evidence=())
    assert br.evidence_thin([rejected, bare]) is True
    assert br.evidence_thin([option(id="C"), bare]) is False


def test_a_rule_that_raises_is_reported_as_malformed(monkeypatch):
    def boom(option, ctx):
        raise RuntimeError("unreadable")

    monkeypatch.setattr(br, "_rule_addr", boom)
    issues = br.option_issues(option(), P)
    assert "MALFORMED" in codes(issues)
    assert any("_rule_addr" in i.detail for i in issues)


def test_a_seal_without_the_verified_flag_counts_for_nothing():
    unmarked = bm.Evidence("m1", ("count",), verified=False, seal=bm.SEAL)
    assert option(evidence=(unmarked,)).evidence_strength == 0


def test_a_cause_check_on_non_text_never_raises():
    for text in (None, 5, ["staff count stock"], {"staff count stock"}):
        assert bt.states_as_fact("staff count stock", text) is False
